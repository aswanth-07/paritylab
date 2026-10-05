import base64
import hashlib
import json
import random
import socket
import threading
import time

from .controller import AdaptiveController
from .fec import Protection, Repair, encode, recover


def udp_transfer(data: bytes, loss: float = 0.1, seed: int = 7, packet_size: int = 512,
                 scheme: str = "adaptive", max_rounds: int = 100) -> tuple[bytes, dict]:
    """Run a block-at-a-time codec demonstration through two real loopback sockets."""
    if not data or not 0 <= loss <= 1 or not 1 <= packet_size <= 1200 or max_rounds < 1:
        raise ValueError("Invalid UDP data, loss, packet size, or retry budget")
    if scheme not in {"sr", "fixed", "adaptive"}:
        raise ValueError("The UDP codec demo supports sr, fixed, and adaptive")
    rng = random.Random(seed)
    received = bytearray()
    errors = []
    stop = threading.Event()
    stats = {"scheme": scheme, "seed": seed, "injected_loss": loss, "data_transmissions": 0,
             "parity_packets": 0, "retransmissions": 0, "dropped_datagrams": 0, "fec_recovered": 0,
             "controller_trace": [], "scope": "block-at-a-time loopback demo; control messages exempt from injected loss"}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
        sender.bind(("127.0.0.1", 0))
        receiver.bind(("127.0.0.1", 0))
        sender.settimeout(0.25)
        receiver.settimeout(0.1)

        def transmit(message, impaired=True):
            if impaired and rng.random() < loss:
                stats["dropped_datagrams"] += 1
                return
            sender.sendto(json.dumps(message).encode(), receiver.getsockname())

        def receive_loop():
            block_id = -1
            known, repairs, raw = {}, [], set()
            appended = False
            size = length = 0
            recovered_count = 0
            try:
                while not stop.is_set():
                    try:
                        wire, address = receiver.recvfrom(65535)
                    except socket.timeout:
                        continue
                    message = json.loads(wire)
                    kind = message["kind"]
                    if kind == "begin":
                        if message["block"] != block_id:
                            block_id = message["block"]
                            size, length = message["size"], message["length"]
                            known, repairs, raw = {}, [], set()
                            appended, recovered_count = False, 0
                        receiver.sendto(json.dumps({"ready": block_id}).encode(), address)
                    elif message["block"] != block_id:
                        continue
                    elif kind == "data":
                        known[message["index"]] = base64.b64decode(message["payload"])
                        if message["original"]:
                            raw.add(message["index"])
                    elif kind == "repair":
                        repairs.append(Repair(tuple(message["members"]), base64.b64decode(message["payload"])))
                    elif kind == "report":
                        recovered_count += len(recover(known, repairs))
                        missing = [i for i in range(size) if i not in known]
                        if not missing and not appended:
                            received.extend(b"".join(known[i] for i in range(size))[:length])
                            appended = True
                        receiver.sendto(json.dumps({"block": block_id, "missing": missing,
                                                    "original_lost": size - len(raw), "fec_recovered": recovered_count}).encode(), address)
            except Exception as error:
                errors.append(error)
                stop.set()

        def exchange_control(message, expected):
            for _ in range(8):
                transmit(message, impaired=False)
                try:
                    while True:
                        response = json.loads(sender.recvfrom(65535)[0])
                        if response.get(expected) == message["block"]:
                            return response
                except socket.timeout:
                    if errors:
                        raise RuntimeError("UDP receiver failed") from errors[0]
            raise TimeoutError("UDP control exchange timed out")

        thread = threading.Thread(target=receive_loop, name="parity-lab-receiver", daemon=True)
        thread.start()
        controller = AdaptiveController()
        offset = block_id = 0
        started = time.perf_counter()
        try:
            while offset < len(data):
                if scheme == "adaptive":
                    choice = controller.choose()
                    protection = choice.protection
                    stats["controller_trace"].append({"block": block_id, "mode": protection.label,
                                                      "estimated_loss": choice.estimated_loss, "target_met": choice.target_met})
                else:
                    protection = Protection("xor", 8) if scheme == "fixed" else Protection("none", 16)
                chunk = data[offset:offset + protection.k * packet_size]
                packets = [chunk[i:i + packet_size].ljust(packet_size, b"\0") for i in range(0, len(chunk), packet_size)]
                exchange_control({"kind": "begin", "block": block_id, "size": len(packets), "length": len(chunk)}, "ready")
                missing = list(range(len(packets)))
                for round_number in range(max_rounds):
                    for index in missing:
                        stats["data_transmissions"] += 1
                        stats["retransmissions"] += int(round_number > 0)
                        transmit({"kind": "data", "block": block_id, "index": index,
                                  "original": round_number == 0, "payload": base64.b64encode(packets[index]).decode()})
                    if round_number == 0:
                        for repair in encode(packets, protection):
                            stats["parity_packets"] += 1
                            transmit({"kind": "repair", "block": block_id, "members": repair.members,
                                      "payload": base64.b64encode(repair.payload).decode()})
                    report = exchange_control({"kind": "report", "block": block_id}, "block")
                    if round_number == 0:
                        controller.observe(report["original_lost"], len(packets))
                    missing = report["missing"]
                    if not missing:
                        stats["fec_recovered"] += report["fec_recovered"]
                        break
                else:
                    raise TimeoutError(f"UDP block {block_id} exceeded its retry budget")
                offset += len(chunk)
                block_id += 1
        finally:
            stop.set()
            thread.join(timeout=2)
        if thread.is_alive():
            raise RuntimeError("UDP receiver did not stop")
        if errors:
            raise RuntimeError("UDP receiver failed") from errors[0]
        result = bytes(received)
        stats.update({"elapsed_s": time.perf_counter() - started, "bytes_delivered": len(result),
                      "sha256": hashlib.sha256(result).hexdigest(), "verified": result == data,
                      "sender_address": sender.getsockname(), "receiver_address": receiver.getsockname()})
        if result != data:
            raise AssertionError("UDP output differs from input")
        return result, stats

