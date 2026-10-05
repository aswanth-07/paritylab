import hashlib
import heapq
import math
from dataclasses import asdict, dataclass, field

from .channel import Channel, ChannelConfig
from .controller import AdaptiveController
from .fec import Protection, Repair, encode, recover

SCHEMES = ("gbn", "sr", "fixed", "adaptive")
HEADER_BYTES = 40
ACK_BYTES = 48
METADATA_BYTES = 96


@dataclass(frozen=True)
class SimulationConfig:
    scheme: str = "adaptive"
    packet_size: int = 1024
    window: int = 32
    fixed_k: int = 8
    timeout_ms: float | None = None
    seed: int = 7
    max_events: int = 500_000
    channel: ChannelConfig = field(default_factory=ChannelConfig)
    metadata_mode: str = "idealized"
    metadata_loss: float | None = None
    controller_policy: str = "legacy"

    def __post_init__(self):
        positive_integers = (self.packet_size, self.window, self.fixed_k, self.max_events)
        if (self.scheme not in SCHEMES or any(not isinstance(value, int) or isinstance(value, bool) or value < 1 for value in positive_integers)
                or not isinstance(self.seed, int) or isinstance(self.seed, bool)):
            raise ValueError("Invalid scheme, packet size, window, block size, or event budget")
        if self.timeout_ms is not None and (not math.isfinite(self.timeout_ms) or self.timeout_ms <= 0):
            raise ValueError("Timeout must be finite and positive")
        if self.metadata_mode not in {"idealized", "reliable"}:
            raise ValueError("Metadata mode must be idealized or reliable")
        if self.metadata_loss is not None and (not math.isfinite(self.metadata_loss) or not 0 <= self.metadata_loss <= 1):
            raise ValueError("Metadata loss must be finite and in [0, 1]")
        if self.controller_policy not in {"legacy", "uncertainty", "burst"}:
            raise ValueError("Invalid controller policy")


@dataclass
class Block:
    start: int
    size: int
    protection: Protection
    packets: list[bytes]
    known: dict[int, bytes] = field(default_factory=dict)
    repairs: list[Repair] = field(default_factory=list)
    first_arrivals: set[int] = field(default_factory=set)
    first_outcomes: list[bool] = field(default_factory=list)


@dataclass
class Result:
    scheme: str
    seed: int
    completed: bool
    bytes_delivered: int
    sha256: str
    completion_time_s: float
    sender_completion_time_s: float
    goodput_mbps: float
    retransmissions: int
    data_transmissions: int
    parity_packets: int
    ack_packets: int
    forward_wire_bytes: int
    reverse_wire_bytes: int
    parity_overhead_ratio: float
    total_forward_overhead_ratio: float
    mean_delay_ms: float
    p95_delay_ms: float
    original_data_losses: int
    fec_recovered: int
    fec_recovery_ratio: float
    packet_delays_ms: list[float]
    controller_trace: list[dict]
    transmissions: list[dict] = field(default_factory=list)
    application_bytes_delivered: int = 0
    application_sha256: str = ""
    application_completion_time_s: float = 0.0
    application_mean_delay_ms: float = 0.0
    application_p95_delay_ms: float = 0.0
    application_packet_delays_ms: list[float] = field(default_factory=list)
    head_of_line_mean_ms: float = 0.0
    head_of_line_p95_ms: float = 0.0
    metadata_transmissions: int = 0
    metadata_retransmissions: int = 0
    metadata_acks: int = 0

    def to_dict(self):
        return asdict(self)


def simulate(data: bytes, config: SimulationConfig | None = None, *, capture_transmissions: bool = False) -> Result:
    if config is None:
        config = SimulationConfig()
    if not data:
        raise ValueError("Transfer must contain at least one byte")
    width = config.packet_size
    packets = [data[i:i + width].ljust(width, b"\0") for i in range(0, len(data), width)]
    count = len(packets)
    channel = Channel(config.channel, config.seed)
    controller = AdaptiveController(config.window) if config.controller_policy == "legacy" else AdaptiveController(config.window, policy=config.controller_policy)
    queue = []
    counter = 0
    now = 0.0
    base = next_sequence = receiver_base = 0
    acked, delivered = set(), {}
    first_sent, delivery_time, latest, block_for = {}, {}, {}, {}
    application_time = {}
    application_base = 0
    blocks = {}
    originals_lost = set()
    fec_indices = set()
    stats = {"retransmissions": 0, "data_transmissions": 0, "parity_packets": 0, "ack_packets": 0,
             "forward_wire_bytes": 0, "reverse_wire_bytes": 0}
    trace = []
    transmissions = []
    metadata_available, metadata_acked = set(), set()
    metadata_attempts, pending_arrivals = {}, {}
    pending_reports = set()
    metadata_stats = {"metadata_transmissions": 0, "metadata_retransmissions": 0, "metadata_acks": 0}
    serial = (width + HEADER_BYTES) * 8 / (config.channel.bandwidth_mbps * 1_000_000)
    impairment_bound = (config.channel.jitter_ms + config.channel.reorder_delay_ms) / 1000
    timeout = config.timeout_ms / 1000 if config.timeout_ms is not None else max(0.02, 2 * config.channel.delay_ms / 1000 + 2 * impairment_bound + serial * (config.window + 16) + 0.005)

    def schedule(time, kind, payload):
        nonlocal counter
        counter += 1
        heapq.heappush(queue, (time, counter, kind, payload))

    def acknowledge(sequences):
        if not sequences:
            return
        stats["ack_packets"] += 1
        stats["reverse_wire_bytes"] += ACK_BYTES
        arrival, dropped, end = channel.transmit(now, ACK_BYTES, reverse=True)
        if capture_transmissions:
            transmissions.append({"kind": "ack", "start_s": end - ACK_BYTES * 8 / (config.channel.bandwidth_mbps * 1_000_000),
                                  "arrival_s": arrival, "lost": dropped, "sequences": list(sequences)})
        if not dropped:
            schedule(arrival, "ack", tuple(sequences))

    def deliver(sequence, payload, fec=False):
        nonlocal application_base
        if sequence not in delivered:
            delivered[sequence] = payload
            delivery_time[sequence] = now
            if fec and latest[sequence][0] == 1:
                fec_indices.add(sequence)
            while application_base in delivered:
                application_time[application_base] = now
                application_base += 1

    def send_metadata(block_id):
        attempt = metadata_attempts.get(block_id, 0) + 1
        metadata_attempts[block_id] = attempt
        metadata_stats["metadata_transmissions"] += 1
        metadata_stats["metadata_retransmissions"] += int(attempt > 1)
        stats["forward_wire_bytes"] += METADATA_BYTES
        arrival, dropped, end = channel.transmit(now, METADATA_BYTES, loss_override=config.metadata_loss)
        if capture_transmissions:
            transmissions.append({"kind": "metadata", "start_s": end - METADATA_BYTES * 8 / (config.channel.bandwidth_mbps * 1_000_000),
                                  "arrival_s": arrival, "lost": dropped, "block_start": block_id, "attempt": attempt})
        if not dropped:
            schedule(arrival, "metadata", block_id)
        schedule(end + timeout, "metadata_timeout", (block_id, attempt))

    def feedback(block_id):
        block = blocks[block_id]
        lost = block.size - len(block.first_arrivals)
        # Feedback reports raw first-attempt erasures before FEC, not residual loss.
        total = block.size + len(encode(block.packets, block.protection))
        stats["ack_packets"] += 1
        stats["reverse_wire_bytes"] += ACK_BYTES
        arrival, dropped, _ = channel.transmit(now, ACK_BYTES, reverse=True)
        if not dropped:
            schedule(arrival, "feedback", (lost, block.size, total, tuple(block.first_outcomes)))

    def send_data(sequence):
        previous = latest.get(sequence)
        attempt = 1 if previous is None else previous[0] + 1
        if previous is not None:
            stats["retransmissions"] += 1
        stats["data_transmissions"] += 1
        stats["forward_wire_bytes"] += width + HEADER_BYTES
        arrival, dropped, end = channel.transmit(now, width + HEADER_BYTES)
        if capture_transmissions:
            transmissions.append({"kind": "data", "start_s": end - serial, "arrival_s": arrival,
                                  "lost": dropped, "sequence": sequence, "attempt": attempt})
        first_sent.setdefault(sequence, end - serial)
        latest[sequence] = (attempt, end)
        if dropped and attempt == 1:
            originals_lost.add(sequence)
        if attempt == 1:
            blocks[block_for[sequence]].first_outcomes.append(dropped)
        if not dropped:
            schedule(arrival, "data", (sequence, attempt))
        schedule(end + timeout, "timeout", (sequence, attempt))
        return arrival

    def fill_window():
        nonlocal next_sequence
        while next_sequence < count and next_sequence < base + config.window:
            available = min(count - next_sequence, base + config.window - next_sequence)
            if config.scheme in {"gbn", "sr"}:
                protection = Protection("none", 1)
            elif config.scheme == "fixed":
                protection = Protection("xor", min(config.fixed_k, config.window))
            else:
                choice = controller.choose() if config.controller_policy == "legacy" else controller.choose(size=count - next_sequence)
                protection = choice.protection
            # Parity needs a full block; unprotected data can use every free slot.
            desired = min(protection.k, count - next_sequence)
            if protection.mode == "none":
                desired = min(desired, available)
            if available < desired:
                break
            if config.scheme == "adaptive":
                entry = {"time_s": now, "start_packet": next_sequence, "data_packets": desired,
                              "mode": protection.label, "estimated_loss": choice.estimated_loss,
                              "predicted_failure": choice.predicted_failure, "target_met": choice.target_met,
                              "assumption": "independent identical data and parity erasures"}
                if config.controller_policy != "legacy":
                    entry.update({key: value for key, value in asdict(choice).items()
                                  if key not in {"protection", "predicted_failure", "target_met", "estimated_loss"}})
                    entry["assumption"] = choice.assumptions
                trace.append(entry)
            start, size = next_sequence, desired
            block = Block(start, size, protection, packets[start:start + size])
            blocks[start] = block
            if config.metadata_mode == "reliable":
                send_metadata(start)
            last_arrival = now
            for sequence in range(start, start + size):
                block_for[sequence] = start
                last_arrival = max(last_arrival, send_data(sequence))
            for repair in encode(block.packets, protection):
                stats["parity_packets"] += 1
                stats["forward_wire_bytes"] += width + HEADER_BYTES
                arrival, dropped, end = channel.transmit(now, width + HEADER_BYTES)
                block.first_outcomes.append(dropped)
                if capture_transmissions:
                    transmissions.append({"kind": "parity", "start_s": end - serial,
                                          "arrival_s": arrival, "lost": dropped, "block_start": start, "members": list(repair.members)})
                last_arrival = max(last_arrival, arrival)
                if not dropped:
                    schedule(arrival, "repair", (start, repair))
            schedule(last_arrival + 1e-9, "block_report", start)
            next_sequence += size

    fill_window()
    events = 0
    while len(acked) < count and queue:
        now, _, kind, payload = heapq.heappop(queue)
        events += 1
        if events > config.max_events:
            break
        if kind in {"data", "repair"} and config.metadata_mode == "reliable":
            block_id = block_for[payload[0]] if kind == "data" else payload[0]
            if block_id not in metadata_available:
                pending_arrivals.setdefault(block_id, []).append((kind, payload))
                continue
        if kind == "metadata":
            block_id = payload
            if block_id not in metadata_available:
                metadata_available.add(block_id)
                for pending_kind, pending_payload in pending_arrivals.pop(block_id, []):
                    schedule(now, pending_kind, pending_payload)
                if block_id in pending_reports:
                    pending_reports.remove(block_id)
                    # Replay buffered first arrivals before forming the report.
                    schedule(now + 1e-9, "block_report", block_id)
            metadata_stats["metadata_acks"] += 1
            stats["reverse_wire_bytes"] += ACK_BYTES
            arrival, dropped, end = channel.transmit(now, ACK_BYTES, reverse=True)
            if capture_transmissions:
                transmissions.append({"kind": "metadata_ack", "start_s": end - ACK_BYTES * 8 / (config.channel.bandwidth_mbps * 1_000_000),
                                      "arrival_s": arrival, "lost": dropped, "block_start": block_id})
            if not dropped:
                schedule(arrival, "metadata_ack", block_id)
        elif kind == "metadata_ack":
            metadata_acked.add(payload)
        elif kind == "metadata_timeout":
            block_id, attempt = payload
            if block_id not in metadata_acked and metadata_attempts[block_id] == attempt:
                send_metadata(block_id)
        elif kind == "data":
            sequence, attempt = payload
            block = blocks[block_for[sequence]]
            if attempt == 1:
                block.first_arrivals.add(sequence - block.start)
            if config.scheme == "gbn":
                if sequence == receiver_base:
                    deliver(sequence, packets[sequence])
                    receiver_base += 1
                acknowledge([receiver_base - 1] if receiver_base else [])
            else:
                block.known[sequence - block.start] = packets[sequence]
                deliver(sequence, packets[sequence])
                rebuilt = recover(block.known, block.repairs)
                for index, value in rebuilt.items():
                    deliver(block.start + index, value, fec=True)
                acknowledge([sequence] + [block.start + index for index in rebuilt])
        elif kind == "repair":
            block_id, repair = payload
            block = blocks[block_id]
            block.repairs.append(repair)
            rebuilt = recover(block.known, block.repairs)
            for index, value in rebuilt.items():
                deliver(block.start + index, value, fec=True)
            acknowledge([block.start + index for index in rebuilt])
        elif kind == "block_report":
            if config.scheme == "adaptive":
                if config.metadata_mode == "reliable" and payload not in metadata_available:
                    pending_reports.add(payload)
                else:
                    feedback(payload)
        elif kind == "feedback":
            lost, original_count, _, first_outcomes = payload
            if config.controller_policy == "legacy":
                controller.observe(lost, original_count)
            else:
                # A first-pass block is contiguous on the forward serializer.
                # Do not infer transitions across omitted retransmissions/metadata.
                controller.observe_sequence(first_outcomes, contiguous=False)
        elif kind == "ack":
            if config.scheme == "gbn":
                acked.update(range(max(payload) + 1))
            else:
                acked.update(payload)
            while base in acked:
                base += 1
            fill_window()
        elif kind == "timeout":
            sequence, attempt = payload
            if sequence in acked or latest[sequence][0] != attempt:
                continue
            if config.scheme == "gbn":
                if sequence == base:
                    for pending in range(base, next_sequence):
                        send_data(pending)
            else:
                send_data(sequence)

    complete = len(acked) == count and len(delivered) == count
    output = b"".join(delivered[i][:min(width, len(data) - i * width)] for i in range(count) if i in delivered)
    if complete and output != data:
        raise AssertionError("Recovered transfer differs from input")
    completion = max(delivery_time.values(), default=0.0)
    delays = sorted((delivery_time[i] - first_sent[i]) * 1000 for i in delivered)
    application_output = b"".join(delivered[i][:min(width, len(data) - i * width)] for i in range(application_base))
    application_delays = sorted((application_time[i] - first_sent[i]) * 1000 for i in application_time)
    head_of_line = sorted((application_time[i] - delivery_time[i]) * 1000 for i in application_time)
    def percentile(values):
        return values[max(0, math.ceil(0.95 * len(values)) - 1)] if values else 0.0
    return Result(config.scheme, config.seed, complete, len(output), hashlib.sha256(output).hexdigest(),
                  completion, now, len(output) * 8 / completion / 1_000_000 if completion else 0.0,
                  **stats, parity_overhead_ratio=stats["parity_packets"] * width / len(data),
                  total_forward_overhead_ratio=(stats["forward_wire_bytes"] - len(data)) / len(data),
                  mean_delay_ms=sum(delays) / len(delays) if delays else 0.0,
                  p95_delay_ms=delays[max(0, math.ceil(0.95 * len(delays)) - 1)] if delays else 0.0,
                  original_data_losses=len(originals_lost), fec_recovered=len(fec_indices),
                  fec_recovery_ratio=len(fec_indices) / len(originals_lost) if originals_lost else 0.0,
                  packet_delays_ms=delays, controller_trace=trace, transmissions=transmissions,
                  application_bytes_delivered=len(application_output), application_sha256=hashlib.sha256(application_output).hexdigest(),
                  application_completion_time_s=max(application_time.values(), default=0.0),
                  application_mean_delay_ms=sum(application_delays) / len(application_delays) if application_delays else 0.0,
                  application_p95_delay_ms=percentile(application_delays), application_packet_delays_ms=application_delays,
                  head_of_line_mean_ms=sum(head_of_line) / len(head_of_line) if head_of_line else 0.0,
                  head_of_line_p95_ms=percentile(head_of_line), **metadata_stats)
