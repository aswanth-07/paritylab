"""Separate localhost sender, receiver and impairment-proxy processes.

All protocol messages traverse the proxy, including manifests, feedback and final
digest confirmation. This experimental transport is bounded and local by design.
"""
import argparse
import hashlib
import heapq
import json
import math
import os
import select
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .channel import Channel, ChannelConfig
from .controller import AdaptiveController, POLICIES
from .fec import Protection, Repair, encode, recover
from .simulation import SCHEMES
from .wire import integer, pack, unpack


@dataclass(frozen=True)
class SocketConfig:
    scheme: str = "adaptive"
    packet_size: int = 512
    window: int = 32
    fixed_k: int = 8
    seed: int = 7
    channel: ChannelConfig = field(default_factory=lambda: ChannelConfig(delay_ms=5))
    metadata_loss: float | None = None
    duplicate_probability: float = 0.0
    corruption_probability: float = 0.0
    timeout_ms: float | None = None
    max_seconds: float = 20.0
    max_attempts: int = 150
    controller_policy: str = "legacy"
    recovery_feedback: bool = False

    def __post_init__(self):
        if any(isinstance(value, bool) or not isinstance(value, int) for value in
               (self.packet_size, self.window, self.fixed_k, self.seed, self.max_attempts)):
            raise ValueError("Packet, window, block, seed and retry settings must be integers")
        if self.scheme not in SCHEMES or not 1 <= self.packet_size <= 1200 or not 1 <= self.window <= 256:
            raise ValueError("Invalid socket scheme, packet size or window")
        if not 1 <= self.fixed_k <= 256 or self.max_attempts < 1:
            raise ValueError("Invalid block size or retry bound")
        for probability in (self.duplicate_probability, self.corruption_probability, self.metadata_loss):
            if probability is not None and (not math.isfinite(probability) or not 0 <= probability <= 1):
                raise ValueError("Impairment probabilities must be finite and in [0,1]")
        if isinstance(self.max_seconds, bool) or not isinstance(self.max_seconds, (int, float)) or not math.isfinite(self.max_seconds) or not 0 < self.max_seconds <= 300:
            raise ValueError("Socket runtime must be finite and in (0,300] seconds")
        if self.timeout_ms is not None and (not math.isfinite(self.timeout_ms) or self.timeout_ms <= 0):
            raise ValueError("Timeout must be finite and positive")
        if self.controller_policy not in POLICIES:
            raise ValueError("Invalid controller policy")
        if not isinstance(self.recovery_feedback, bool) or (self.recovery_feedback and self.scheme != "adaptive"):
            raise ValueError("Recovery feedback requires an adaptive transfer and a boolean setting")


def _write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def _socket():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.setblocking(False)
    return sock


def _read(sock):
    try:
        return sock.recvfrom(65535)
    except (ConnectionResetError, BlockingIOError):
        # Windows reports late ICMP for a closed UDP peer via recvfrom. Treat it
        # as no datagram; actual transfer failure is decided by bounded timers.
        return None


def _descriptor(message, count, width):
    start = integer(message, "block", 0, count - 1)
    size = integer(message, "size", 1, min(256, count - start))
    p = message.get("protection")
    if not isinstance(p, dict):
        raise ValueError("Missing block descriptor")
    protection = Protection(p.get("mode"), integer(p, "k", 1, 256), p.get("rows", 0), p.get("columns", 0))
    if size > protection.k or len(message["payload"]) not in {0, width}:
        raise ValueError("Invalid block size or payload width")
    return start, size, protection


def receiver_worker(output: Path, ready: Path, receipt: Path, stop: Path, max_seconds: float):
    with _socket() as sock:
        _write(ready, {"address": sock.getsockname(), "pid": os.getpid()})
        deadline = time.monotonic() + max_seconds
        session = address = manifest = None
        known, blocks, first_sent, received_at, released_at = {}, {}, {}, {}, {}
        reports, raw_seen = {}, {}
        receiver_base = released = 0
        invalid = fec_recovered = 0
        finished = False

        def respond(fields):
            sock.sendto(pack({"session": session, **fields}), address)

        def release():
            nonlocal released
            while released in known:
                released_at.setdefault(released, time.monotonic())
                released += 1

        def accept(sequence, payload, reconstructed=False):
            nonlocal fec_recovered
            if sequence not in known:
                known[sequence] = payload
                received_at[sequence] = time.monotonic()
                if reconstructed:
                    fec_recovered += 1
            release()

        while time.monotonic() < deadline and not stop.exists():
            now = time.monotonic()
            for block_id, due in list(reports.items()):
                if now >= due:
                    block = blocks[block_id]
                    pattern = [i in raw_seen.get(block_id, set()) for i in range(block["size"])]
                    respond({"kind": "feedback", "block": block_id, "lost": pattern.count(False),
                             "transmitted": len(pattern), "arrivals": pattern,
                             "received": [i in block["known"] for i in range(block["size"])],
                             "repair_arrivals": [repair.members in block["repairs"] for repair in
                                                 encode([bytes(manifest["packet_size"])] * block["size"], block["descriptor"][1])]})
                    del reports[block_id]
            if not select.select([sock], [], [], 0.002)[0]:
                continue
            incoming = _read(sock)
            if incoming is None:
                continue
            wire, source = incoming
            now = time.monotonic()
            try:
                message = unpack(wire)
                if message["kind"] == "syn":
                    if manifest is None:
                        candidate = message.get("manifest")
                        if not isinstance(candidate, dict):
                            raise ValueError("Missing transfer manifest")
                        length = integer(candidate, "length", 1, 64 * 1024 * 1024)
                        width = integer(candidate, "packet_size", 1, 1200)
                        count = integer(candidate, "count", 1, 131072)
                        if count != math.ceil(length / width) or candidate.get("scheme") not in SCHEMES:
                            raise ValueError("Inconsistent transfer manifest")
                        if not isinstance(message.get("session"), str) or len(message["session"]) != 32:
                            raise ValueError("Invalid session identifier")
                        manifest, session, address = candidate, message["session"], source
                    if message.get("session") == session and source == address:
                        respond({"kind": "ready"})
                    continue
                if manifest is None or message.get("session") != session or source != address:
                    continue
                count, width = manifest["count"], manifest["packet_size"]
                kind = message["kind"]
                if kind in {"data", "repair", "report"}:
                    start, size, protection = _descriptor(message, count, width)
                    descriptor = (size, protection)
                    if start in blocks and blocks[start]["descriptor"] != descriptor:
                        raise ValueError("Conflicting block descriptor")
                    blocks.setdefault(start, {"size": size, "descriptor": descriptor, "known": {}, "repairs": {}})
                    block = blocks[start]
                    if kind == "report":
                        grace = manifest.get("report_grace_ms", 0) / 1000
                        reports.setdefault(start, now + grace)
                        continue
                    if len(message["payload"]) != width:
                        raise ValueError("A transmitted symbol must have the declared width")
                    if kind == "data":
                        sequence = integer(message, "sequence", start, start + size - 1)
                        attempt = integer(message, "attempt", 1, 100000)
                        sent = message.get("first_sent")
                        if not isinstance(sent, (int, float)) or not math.isfinite(sent) or sent > now:
                            raise ValueError("Invalid send timestamp")
                        first_sent.setdefault(sequence, sent)
                        if attempt == 1:
                            raw_seen.setdefault(start, set()).add(sequence - start)
                        if manifest["scheme"] == "gbn":
                            if sequence == receiver_base:
                                accept(sequence, message["payload"])
                                receiver_base += 1
                            respond({"kind": "ack", "cumulative": receiver_base - 1})
                            continue
                        block["known"][sequence - start] = message["payload"]
                        accept(sequence, message["payload"])
                        acknowledged = [sequence]
                    else:
                        timestamps = message.get("first_sends", [])
                        if not isinstance(timestamps, list) or len(timestamps) != size or any(
                            isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) or t > now for t in timestamps
                        ):
                            raise ValueError("Invalid parity send timestamps")
                        for i, sent in enumerate(timestamps):
                            first_sent.setdefault(start + i, sent)
                        members = message.get("members")
                        if not isinstance(members, list) or not members or len(set(members)) != len(members):
                            raise ValueError("Invalid parity members")
                        if any(isinstance(i, bool) or not isinstance(i, int) or not 0 <= i < size for i in members):
                            raise ValueError("Invalid parity index")
                        allowed = {repair.members for repair in encode([bytes(width)] * size, protection)}
                        if tuple(members) not in allowed:
                            raise ValueError("Parity equation does not match descriptor")
                        block["repairs"][tuple(members)] = Repair(tuple(members), message["payload"])
                        acknowledged = []
                    rebuilt = recover(block["known"], block["repairs"].values())
                    for index, payload in rebuilt.items():
                        accept(start + index, payload, True)
                    acknowledged += [start + index for index in rebuilt]
                    if acknowledged:
                        respond({"kind": "ack", "sequences": acknowledged})
                elif kind == "fin":
                    if len(known) == count:
                        data = b"".join(known[i] for i in range(count))[:manifest["length"]]
                        digest = hashlib.sha256(data).hexdigest()
                        if digest != manifest.get("sha256"):
                            raise ValueError("Received file digest mismatch")
                        if not finished:
                            output.write_bytes(data)
                            packet_delays = [(received_at[i] - first_sent[i]) * 1000 for i in first_sent]
                            application_delays = [(released_at[i] - first_sent[i]) * 1000 for i in first_sent]
                            _write(receipt, {"verified": True, "bytes_delivered": len(data), "sha256": digest,
                                   "fec_recovered": fec_recovered, "invalid_datagrams": invalid,
                                   "packet_delays_ms": packet_delays, "application_delays_ms": application_delays,
                                   "application_release_count": released, "pid": os.getpid(),
                                   "packet_timestamps": [{"sequence": i, "first_sent_s": first_sent[i],
                                         "received_s": received_at[i], "application_release_s": released_at[i]} for i in range(count)],
                                   "address": sock.getsockname()})
                            finished = True
                        respond({"kind": "finished", "sha256": digest, "bytes": len(data)})
            except (ValueError, TypeError, KeyError, UnicodeDecodeError, OverflowError):
                invalid += 1
        if not finished:
            raise TimeoutError("Receiver did not confirm a complete file")


def proxy_worker(config: SocketConfig, receiver_address, ready: Path, receipt: Path, stop: Path):
    import random
    rng = random.Random(config.seed + 3000017)
    with _socket() as ingress, _socket() as egress:
        _write(ready, {"address": ingress.getsockname(), "egress_address": egress.getsockname(), "pid": os.getpid()})
        channel = Channel(config.channel, config.seed)
        queue, serial = [], 0
        sender_address = None
        started = time.monotonic()
        stats = {"forward_datagrams": 0, "reverse_datagrams": 0, "forward_wire_bytes": 0,
                 "reverse_wire_bytes": 0, "dropped_forward": 0, "dropped_reverse": 0,
                 "dropped_metadata": 0, "duplicates": 0, "corrupted": 0, "events": []}
        while not stop.exists() and time.monotonic() - started < config.max_seconds:
            now = time.monotonic() - started
            while queue and queue[0][0] <= now:
                _, _, target, address, wire = heapq.heappop(queue)
                target.sendto(wire, address)
            readable = select.select([ingress, egress], [], [], 0.001)[0]
            for source_socket in readable:
                incoming = _read(source_socket)
                if incoming is None:
                    continue
                wire, address = incoming
                reverse = source_socket is egress
                if reverse and address != tuple(receiver_address):
                    continue
                if not reverse:
                    if sender_address is None:
                        sender_address = address
                    if address != sender_address:
                        continue
                if sender_address is None:
                    continue
                kind = "invalid"
                try:
                    kind = unpack(wire)["kind"]
                except (ValueError, UnicodeDecodeError):
                    kind = "invalid"  # The proxy still impairs malformed datagrams.
                prefix = "reverse" if reverse else "forward"
                stats[prefix + "_datagrams"] += 1
                stats[prefix + "_wire_bytes"] += len(wire)
                metadata_override = config.metadata_loss if not reverse and kind in {"syn", "report", "fin"} else None
                arrival, dropped, end = channel.transmit(now, len(wire), reverse=reverse, loss_override=metadata_override)
                if dropped:
                    stats["dropped_" + prefix] += 1
                    if kind in {"syn", "report", "fin"}:
                        stats["dropped_metadata"] += 1
                stats["events"].append({"kind": kind, "reverse": reverse, "bytes": len(wire),
                                        "send_s": now, "serialization_end_s": end,
                                        "arrival_s": arrival, "lost": dropped})
                if dropped:
                    continue
                if rng.random() < config.corruption_probability:
                    wire = wire[:-1] + bytes([wire[-1] ^ 1])
                    stats["corrupted"] += 1
                target, destination = (ingress, sender_address) if reverse else (egress, tuple(receiver_address))
                serial += 1
                heapq.heappush(queue, (arrival, serial, target, destination, wire))
                if rng.random() < config.duplicate_probability:
                    serial += 1
                    heapq.heappush(queue, (arrival + 0.001, serial, target, destination, wire))
                    stats["duplicates"] += 1
        stats.update({"pid": os.getpid(), "elapsed_s": time.monotonic() - started,
                      "scope": "Actual CRC-protected UDP datagrams; all control, data and parity impaired; localhost only"})
        _write(receipt, stats)


def sender_worker(data: bytes, config: SocketConfig, proxy_address, receipt: Path):
    width = config.packet_size
    packets = [data[i:i + width].ljust(width, b"\0") for i in range(0, len(data), width)]
    count = len(packets)
    session = uuid.uuid4().hex
    started = time.monotonic()
    deadline = started + config.max_seconds
    extra_ms = getattr(config.channel, "jitter_ms", 0) + getattr(config.channel, "reorder_delay_ms", 0)
    timeout = config.timeout_ms / 1000 if config.timeout_ms else max(0.04, 2 * (config.channel.delay_ms + extra_ms) / 1000 +
              (width + 800) * 8 * (config.window + 16) / (config.channel.bandwidth_mbps * 1e6) + 0.01)
    # JSON descriptors vary in size; use the same conservative wire-size
    # allowance as the transport timer. Simulator costs use its binary header.
    controller = AdaptiveController(config.window, policy=config.controller_policy,
                                    packet_serial_s=(width + 800) * 8 / (config.channel.bandwidth_mbps * 1e6),
                                    retry_wait_s=timeout)
    manifest = {"length": len(data), "packet_size": width, "count": count, "scheme": config.scheme,
                "sha256": hashlib.sha256(data).hexdigest(), "report_grace_ms": extra_ms + 10}
    stats = {"scheme": config.scheme, "retransmissions": 0, "data_transmissions": 0, "parity_packets": 0,
             "control_transmissions": 0, "controller_trace": [], "peak_outstanding": 0,
             "metadata_retries": 0, "feedback_reports": 0, "feedback_retries": 0, "pid": os.getpid()}
    with _socket() as sock:
        destination = tuple(proxy_address)

        def send(fields):
            sock.sendto(pack({"session": session, **fields}), destination)

        def receive(wait):
            if select.select([sock], [], [], max(0, wait))[0]:
                incoming = _read(sock)
                if incoming is None:
                    return None
                wire, address = incoming
                if address != destination:
                    return None
                try:
                    message = unpack(wire)
                    if message.get("session") == session:
                        return message
                except (ValueError, UnicodeDecodeError):
                    return None  # Corrupt frames cannot acknowledge data.
            return None

        def exchange(fields, expected):
            for attempt in range(config.max_attempts):
                if time.monotonic() >= deadline:
                    break
                send(fields)
                stats["control_transmissions"] += 1
                stats["metadata_retries"] += int(attempt > 0)
                until = min(deadline, time.monotonic() + timeout)
                while time.monotonic() < until:
                    message = receive(min(0.005, until - time.monotonic()))
                    if message and message["kind"] == expected:
                        return message
            raise TimeoutError(f"{fields['kind']} confirmation exceeded bounded retry/runtime budget")

        exchange({"kind": "syn", "manifest": manifest}, "ready")
        base = next_sequence = 0
        acknowledged, blocks, block_for, pending_reports = set(), {}, {}, {}
        latest, first_sent, attempts, observed = {}, {}, {}, set()

        def send_data(sequence):
            attempts[sequence] = attempts.get(sequence, 0) + 1
            if attempts[sequence] > config.max_attempts:
                raise TimeoutError("Data sequence exceeded retry budget")
            first_sent.setdefault(sequence, time.monotonic())
            stats["retransmissions"] += int(attempts[sequence] > 1)
            stats["data_transmissions"] += 1
            send({"kind": "data", **blocks[block_for[sequence]], "sequence": sequence,
                  "attempt": attempts[sequence], "first_sent": first_sent[sequence], "payload": packets[sequence]})
            latest[sequence] = time.monotonic()

        def fill():
            nonlocal next_sequence
            while next_sequence < count and next_sequence < base + config.window:
                available = min(count - next_sequence, base + config.window - next_sequence)
                choice = None
                if config.scheme == "adaptive":
                    choice = controller.choose() if config.controller_policy == "legacy" else controller.choose(size=count-next_sequence)
                    protection = choice.protection
                else:
                    protection = Protection("xor", min(config.fixed_k, config.window)) if config.scheme == "fixed" else Protection("none", 1)
                size = min(protection.k, count - next_sequence)
                if protection.mode == "none":
                    size = min(size, available)
                if size > available:
                    break
                start = next_sequence
                descriptor = {"block": start, "size": size, "protection": asdict(protection)}
                blocks[start] = descriptor
                if choice:
                    stats["controller_trace"].append({"time_s": time.monotonic() - started, "start_packet": start,
                          "data_packets": size, "mode": protection.label, "estimated_loss": choice.estimated_loss,
                          "predicted_failure": choice.predicted_failure, "target_met": choice.target_met,
                          "risk_model": choice.risk_model, "loss_lower": choice.loss_lower,
                          "loss_upper": choice.loss_upper, "observed_symbols": choice.observed_symbols,
                          "objective": choice.objective, "estimated_cost_per_packet_s": choice.estimated_cost_per_packet_s,
                          "unprotected_cost_per_packet_s": choice.unprotected_cost_per_packet_s,
                          "assumptions": choice.assumptions})
                for sequence in range(start, start + size):
                    block_for[sequence] = start
                    send_data(sequence)
                for repair in encode(packets[start:start + size], protection):
                    send({"kind": "repair", **descriptor, "members": list(repair.members), "payload": repair.payload,
                          "first_sends": [first_sent[i] for i in range(start, start + size)]})
                    stats["parity_packets"] += 1
                if config.scheme == "adaptive":
                    send({"kind": "report", **descriptor})
                    pending_reports[start] = time.monotonic()
                    stats["control_transmissions"] += 1
                next_sequence += size
                stats["peak_outstanding"] = max(stats["peak_outstanding"], next_sequence - base)

        fill()
        while len(acknowledged) < count:
            now = time.monotonic()
            if now >= deadline:
                raise TimeoutError("Sliding-window transfer exceeded runtime budget")
            message = receive(0.001)
            if message:
                if message["kind"] == "ack":
                    if config.scheme == "gbn":
                        sequence = message.get("cumulative", -1)
                        if isinstance(sequence, int) and -1 <= sequence < next_sequence:
                            acknowledged.update(range(sequence + 1))
                    else:
                        sequences = message.get("sequences", [])
                        if isinstance(sequences, list):
                            acknowledged.update(i for i in sequences if isinstance(i, int) and not isinstance(i, bool) and 0 <= i < next_sequence)
                    while base in acknowledged:
                        base += 1
                    fill()
                elif message["kind"] == "feedback":
                    block_id = message.get("block")
                    if block_id in blocks and block_id not in observed:
                        size = blocks[block_id]["size"]
                        lost = message.get("lost")
                        if isinstance(lost, int) and 0 <= lost <= size and message.get("transmitted") == size:
                            pattern = message.get("arrivals")
                            if config.controller_policy == "cost" and isinstance(pattern, list) and len(pattern) == size and all(isinstance(v, bool) for v in pattern):
                                repairs = message.get("repair_arrivals", [])
                                expected = len(encode([bytes(width)] * size, Protection(**blocks[block_id]["protection"])))
                                if not isinstance(repairs, list) or len(repairs) != expected or any(not isinstance(v, bool) for v in repairs):
                                    continue
                                controller.observe_sequence([not value for value in pattern + repairs], contiguous=False)
                            elif config.controller_policy != "legacy" and isinstance(pattern, list) and len(pattern) == size:
                                controller.observe_sequence([not value for value in pattern])
                            else:
                                controller.observe(lost, size)
                            observed.add(block_id)
                            pending_reports.pop(block_id, None)
                            stats["feedback_reports"] += 1
                            status = message.get("received")
                            if config.recovery_feedback and isinstance(status, list) and len(status) == size and all(isinstance(v, bool) for v in status):
                                for index, received in enumerate(status):
                                    sequence = block_id + index
                                    if received:
                                        acknowledged.add(sequence)
                                    elif sequence not in acknowledged and attempts[sequence] == 1:
                                        send_data(sequence)
                                        stats["feedback_retries"] += 1
                                while base in acknowledged:
                                    base += 1
                                fill()
            now = time.monotonic()
            if config.scheme == "gbn":
                if base < next_sequence and now - latest[base] >= timeout:
                    for sequence in range(base, next_sequence):
                        send_data(sequence)
            else:
                for sequence in range(base, next_sequence):
                    if sequence not in acknowledged and now - latest[sequence] >= timeout:
                        send_data(sequence)
            for block_id, last_report in list(pending_reports.items()):
                if now - last_report >= timeout:
                    send({"kind": "report", **blocks[block_id]})
                    pending_reports[block_id] = now
                    stats["control_transmissions"] += 1
        confirmation = exchange({"kind": "fin"}, "finished")
        if confirmation.get("sha256") != manifest["sha256"] or confirmation.get("bytes") != len(data):
            raise ValueError("Final receiver confirmation differs from input")
        stats.update({"verified": True, "sha256": manifest["sha256"], "bytes_delivered": len(data),
                      "elapsed_s": time.monotonic() - started, "timeout_s": timeout, "address": sock.getsockname()})
        _write(receipt, stats)


def socket_transfer(data: bytes, config: SocketConfig | None = None, output: Path | None = None) -> tuple[bytes, dict]:
    """Launch three distinct processes, verify their received file, and collect evidence."""
    if config is None:
        config = SocketConfig()
    if not isinstance(data, bytes) or not data or len(data) > 64 * 1024 * 1024:
        raise ValueError("Transfer size must be in [1,64 MiB]")
    if math.ceil(len(data)/config.packet_size) > 131072:
        raise ValueError("Transfer exceeds the 131072-symbol resource bound")
    processes = []
    with tempfile.TemporaryDirectory(prefix="paritylab-socket-") as temporary:
        work = Path(temporary)
        (work / "input.bin").write_bytes(data)
        _write(work / "config.json", asdict(config))
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1]) + os.pathsep + env.get("PYTHONPATH", "")

        def launch(role, *arguments):
            log = (work / f"{role}.log").open("w", encoding="utf-8")
            process = subprocess.Popen([sys.executable, "-m", "paritylab.socket_transport", role, "--work", str(work),
                                        *arguments], stdout=log, stderr=subprocess.STDOUT, env=env)
            processes.append((role, process, log))
            return process

        def wait_ready(role, process):
            until = time.monotonic() + min(10, config.max_seconds)
            path = work / f"{role}-ready.json"
            while time.monotonic() < until:
                if path.exists():
                    try:
                        return json.loads(path.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        # A readiness write can be observed before it is complete.
                        time.sleep(0.01)
                        continue
                if process.poll() is not None:
                    break
                time.sleep(0.01)
            raise RuntimeError(f"{role} failed to become ready: {(work / (role + '.log')).read_text(encoding='utf-8')}")

        try:
            receiver = launch("receiver")
            receiver_ready = wait_ready("receiver", receiver)
            _write(work / "receiver-address.json", receiver_ready["address"])
            proxy = launch("proxy")
            proxy_ready = wait_ready("proxy", proxy)
            _write(work / "proxy-address.json", proxy_ready["address"])
            sender = launch("sender")
            try:
                code = sender.wait(timeout=config.max_seconds + 5)
            except subprocess.TimeoutExpired as error:
                raise TimeoutError("Sender process exceeded orchestration deadline") from error
            if code:
                raise TimeoutError((work / "sender.log").read_text(encoding="utf-8").strip())
            (work / "stop").touch()
            for role, process, _ in processes[:2]:
                process.wait(timeout=5)
                if process.returncode:
                    raise RuntimeError((work / f"{role}.log").read_text(encoding="utf-8"))
            received = (work / "received.bin").read_bytes()
            if received != data:
                raise AssertionError("Actual socket output differs from input")
            stats = {"config": asdict(config), "expected_sha256": hashlib.sha256(data).hexdigest(),
                     "verified": True, "bytes_delivered": len(received),
                     **{role: json.loads((work / f"{role}-receipt.json").read_text(encoding="utf-8")) for role in ("sender", "receiver", "proxy")},
                     "processes": [{"role": role, "pid": process.pid, "exit_code": process.returncode} for role, process, _ in processes]}
            if output:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(received)
                _write(output.with_suffix(".json"), stats)
            return received, stats
        finally:
            (work / "stop").touch()
            for _, process, log in processes:
                if process.poll() is None:
                    try:
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        process.terminate()
                        try:
                            process.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=2)
                log.close()


def main():
    parser = argparse.ArgumentParser(description="Private worker for the localhost transport runner")
    parser.add_argument("role", choices=("sender", "receiver", "proxy"))
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    work = args.work
    fields = json.loads((work / "config.json").read_text(encoding="utf-8"))
    fields["channel"]["phases"] = tuple(tuple(x) for x in fields["channel"].get("phases", []))
    fields["channel"] = ChannelConfig(**fields["channel"])
    config = SocketConfig(**fields)
    if args.role == "receiver":
        receiver_worker(work / "received.bin", work / "receiver-ready.json", work / "receiver-receipt.json", work / "stop", config.max_seconds + 2)
    elif args.role == "proxy":
        proxy_worker(config, json.loads((work / "receiver-address.json").read_text()), work / "proxy-ready.json", work / "proxy-receipt.json", work / "stop")
    else:
        sender_worker((work / "input.bin").read_bytes(), config, json.loads((work / "proxy-address.json").read_text()), work / "sender-receipt.json")


if __name__ == "__main__":
    main()
