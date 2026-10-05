"""Finite-buffer competing flows on one event-driven serialized bottleneck.

This is a transport teaching model, not TCP or an Internet fairness guarantee.
Every data attempt and repair consumes one congestion-window slot. ACKs release
wire slots; timeouts halve AIMD windows. Receivers use the same byte codecs as
the single-flow emulator, with block descriptors known out of band here.
"""

import hashlib
import heapq
import math
import random
from collections import deque
from dataclasses import asdict, dataclass, field

from .channel import Channel, ChannelConfig
from .controller import AdaptiveController
from .fec import Protection, encode, recover
from .simulation import ACK_BYTES, HEADER_BYTES, SCHEMES


@dataclass(frozen=True)
class FlowConfig:
    name: str
    scheme: str = "sr"
    window: int = 64
    fixed_k: int = 8
    congestion_control: str = "aimd"
    initial_cwnd: float = 4.0
    start_s: float = 0.0
    controller_policy: str = "legacy"

    def __post_init__(self):
        if (not isinstance(self.name, str) or not self.name.strip() or self.scheme not in SCHEMES
                or any(not isinstance(value, int) or isinstance(value, bool) or value < 1 for value in (self.window, self.fixed_k))):
            raise ValueError("Flows need a name, supported scheme, and positive window/block size")
        if self.congestion_control not in {"aimd", "none"}:
            raise ValueError("Congestion control must be aimd or none")
        if not math.isfinite(self.initial_cwnd) or self.initial_cwnd < 1:
            raise ValueError("Initial congestion window must be finite and at least one")
        if not math.isfinite(self.start_s) or self.start_s < 0:
            raise ValueError("Flow start time must be finite and nonnegative")
        if self.controller_policy not in {"legacy", "uncertainty", "burst"}:
            raise ValueError("Unsupported controller policy")


@dataclass(frozen=True)
class CongestionConfig:
    channel: ChannelConfig = field(default_factory=lambda: ChannelConfig(loss=0, delay_ms=20, bandwidth_mbps=2))
    packet_size: int = 1024
    queue_packets: int = 16
    seed: int = 7
    timeout_ms: float | None = None
    max_events: int = 2_000_000
    measurement_bin_s: float = 0.1

    def __post_init__(self):
        if (any(not isinstance(value, int) or isinstance(value, bool) or value < 1
                for value in (self.packet_size, self.queue_packets, self.max_events))
                or not isinstance(self.seed, int) or isinstance(self.seed, bool)):
            raise ValueError("Packet size, queue capacity, and event budget must be positive")
        for value in (self.measurement_bin_s, self.timeout_ms):
            if value is not None and (not math.isfinite(value) or value <= 0):
                raise ValueError("Measurement interval and timeout must be finite and positive")


class SharedBottleneck:
    """Tail-drop FIFO capacity includes the packet currently in service.

    Rejected packets consume no serialization service. Accepted erasures do.
    Reverse controls share one separate serializer; its capacity is the same
    bandwidth and it has no finite-buffer limit in this explicit model.
    """

    def __init__(self, config: CongestionConfig):
        self.config = config
        self.channel = Channel(config.channel, config.seed)
        self.departures = deque()
        self.queue_drops = 0
        self.random_drops = 0
        self.accepted_bytes = 0
        self.offered_bytes = 0
        self.high_water_packets = 0

    def transmit(self, time, size, *, reverse=False):
        if not isinstance(size, int) or isinstance(size, bool) or size < 1 or not math.isfinite(time) or time < 0:
            raise ValueError("Transmission needs positive integer wire bytes and nonnegative finite time")
        if reverse:
            arrival, dropped, end = self.channel.transmit(time, size, reverse=True)
            return arrival, dropped, end, "ack_erasure" if dropped else None
        self.offered_bytes += size
        while self.departures and self.departures[0] <= time + 1e-12:
            self.departures.popleft()
        if len(self.departures) >= self.config.queue_packets:
            self.queue_drops += 1
            return time, True, time, "queue_overflow"
        arrival, dropped, end = self.channel.transmit(time, size)
        self.departures.append(end)
        self.high_water_packets = max(self.high_water_packets, len(self.departures))
        self.accepted_bytes += size
        self.random_drops += int(dropped)
        return arrival, dropped, end, "channel_erasure" if dropped else None


@dataclass
class _Block:
    start: int
    packets: list[bytes]
    protection: Protection
    known: dict = field(default_factory=dict)
    repairs: list = field(default_factory=list)
    first_arrivals: set = field(default_factory=set)
    outcomes: list = field(default_factory=list)
    remaining_first: int = 0
    last_arrival: float = 0.0


class _Flow:
    def __init__(self, data, config, packet_size):
        self.data, self.config = data, config
        self.packets = [data[i:i + packet_size].ljust(packet_size, b"\0") for i in range(0, len(data), packet_size)]
        self.base = self.next_sequence = self.receiver_base = self.application_base = 0
        self.acked, self.received, self.delivery_time = set(), {}, {}
        self.application_time, self.first_sent, self.attempts = {}, {}, {}
        self.blocks, self.block_for = {}, {}
        self.pending = deque()
        self.retry_queued = set()
        self.inflight = {}
        self.cwnd = min(float(config.window), config.initial_cwnd) if config.congestion_control == "aimd" else float(config.window)
        self.ssthresh = float(config.window)
        self.last_reduction = -math.inf
        self.peak_inflight = 0
        self.peak_cwnd = self.cwnd
        self.sender_completion = None
        self.stats = {"data_transmissions": 0, "retransmissions": 0, "parity_packets": 0,
                      "forward_wire_bytes": 0, "accepted_wire_bytes": 0, "ack_packets": 0,
                      "reverse_wire_bytes": 0, "queue_drops": 0, "channel_drops": 0,
                      "congestion_reductions": 0, "timeouts": 0, "fec_recovered": 0}
        self.controller_trace = []
        self.cwnd_trace = [{"time_s": config.start_s, "cwnd": self.cwnd, "inflight": 0, "event": "start"}]
        self.controller = (AdaptiveController(config.window) if config.controller_policy == "legacy"
                           else AdaptiveController(config.window, policy=config.controller_policy))


def jain_fairness(rates):
    """Jain index for actual per-flow rates; undefined for an all-zero sample."""
    if not rates or any(not math.isfinite(rate) or rate < 0 for rate in rates):
        raise ValueError("Fairness requires finite nonnegative rates")
    denominator = len(rates) * sum(rate * rate for rate in rates)
    return sum(rates) ** 2 / denominator if denominator else None


def simulate_competing_flows(payloads: list[bytes], flows: list[FlowConfig],
                             config: CongestionConfig | None = None, *, capture_transmissions: bool = False) -> dict:
    """Run all flow state machines concurrently against one shared link.

    Fairness uses the interval when every configured flow has started and none
    has yet completed application delivery. Rates count actual released bytes
    during that common interval; finished-flow idle tails do not inflate it.
    """
    if config is None:
        config = CongestionConfig()
    if not payloads or len(payloads) != len(flows) or any(not payload for payload in payloads):
        raise ValueError("Provide one nonempty payload per flow")
    if len({flow.name for flow in flows}) != len(flows):
        raise ValueError("Flow names must be unique")
    states = [_Flow(payload, flow, config.packet_size) for payload, flow in zip(payloads, flows, strict=True)]
    link = SharedBottleneck(config)
    queue, transmissions = [], []
    counter = token_counter = events = 0
    now = 0.0
    serial = (config.packet_size + HEADER_BYTES) * 8 / (config.channel.bandwidth_mbps * 1_000_000)
    impairment_bound = (config.channel.jitter_ms + config.channel.reorder_delay_ms) / 1000
    timeout = config.timeout_ms / 1000 if config.timeout_ms is not None else max(0.03,
        2 * config.channel.delay_ms / 1000 + 2 * impairment_bound + serial * (config.queue_packets + 4) + 0.005)

    def schedule(time, kind, flow_index, payload):
        nonlocal counter
        counter += 1
        heapq.heappush(queue, (time, counter, kind, flow_index, payload))

    def cwnd_record(flow, event):
        flow.peak_cwnd = max(flow.peak_cwnd, flow.cwnd)
        flow.cwnd_trace.append({"time_s": now, "cwnd": flow.cwnd, "inflight": len(flow.inflight), "event": event})

    def admit(flow):
        while flow.next_sequence < len(flow.packets) and flow.next_sequence < flow.base + flow.config.window:
            available = min(len(flow.packets) - flow.next_sequence, flow.base + flow.config.window - flow.next_sequence)
            if flow.config.scheme in {"gbn", "sr"}:
                protection = Protection("none", 1)
            elif flow.config.scheme == "fixed":
                protection = Protection("xor", min(flow.config.fixed_k, flow.config.window))
            else:
                choice = (flow.controller.choose() if flow.config.controller_policy == "legacy"
                          else flow.controller.choose(size=len(flow.packets) - flow.next_sequence))
                protection = choice.protection
            desired = min(protection.k, len(flow.packets) - flow.next_sequence)
            if protection.mode == "none":
                desired = min(desired, available)
            if desired > available:
                return
            start = flow.next_sequence
            block = _Block(start, flow.packets[start:start + desired], protection)
            repairs = encode(block.packets, protection)
            block.remaining_first = desired + len(repairs)
            flow.blocks[start] = block
            if flow.config.scheme == "adaptive":
                entry = {"time_s": now, "start_packet": start, "data_packets": desired,
                                              "mode": protection.label, "estimated_loss": choice.estimated_loss,
                                              "predicted_failure": choice.predicted_failure, "target_met": choice.target_met}
                if flow.config.controller_policy != "legacy":
                    entry.update({key: value for key, value in asdict(choice).items()
                                  if key not in {"protection", "predicted_failure", "target_met", "estimated_loss"}})
                flow.controller_trace.append(entry)
            for sequence in range(start, start + desired):
                flow.block_for[sequence] = start
                flow.pending.append(("data", sequence, False))
            for repair in repairs:
                flow.pending.append(("parity", (start, repair), False))
            flow.next_sequence += desired

    def pump(index):
        nonlocal token_counter
        flow = states[index]
        if now < flow.config.start_s or flow.sender_completion is not None:
            return
        admit(flow)
        budget = max(1, math.floor(flow.cwnd))
        while flow.pending and len(flow.inflight) < budget:
            kind, value, retry = flow.pending.popleft()
            if kind == "data":
                sequence = value
                flow.retry_queued.discard(sequence)
                if sequence in flow.acked:
                    continue
                attempt = flow.attempts.get(sequence, 0) + 1
                flow.attempts[sequence] = attempt
                flow.stats["data_transmissions"] += 1
                flow.stats["retransmissions"] += int(attempt > 1)
                block_id = flow.block_for[sequence]
                wire_payload = (sequence, attempt)
            else:
                block_id, repair = value
                flow.stats["parity_packets"] += 1
                wire_payload = (block_id, repair)
                attempt = 1
            token_counter += 1
            token = token_counter
            size = config.packet_size + HEADER_BYTES
            arrival, dropped, end, reason = link.transmit(now, size)
            flow.stats["forward_wire_bytes"] += size
            flow.stats["accepted_wire_bytes"] += size if reason != "queue_overflow" else 0
            flow.stats["queue_drops"] += int(reason == "queue_overflow")
            flow.stats["channel_drops"] += int(reason == "channel_erasure")
            flow.inflight[token] = (kind, wire_payload, now)
            flow.peak_inflight = max(flow.peak_inflight, len(flow.inflight))
            if kind == "data":
                flow.first_sent.setdefault(sequence, now)
            # Only first-pass symbols form the modeled block loss report.
            if not retry and attempt == 1:
                block = flow.blocks[block_id]
                block.outcomes.append(dropped)
                block.remaining_first -= 1
                block.last_arrival = max(block.last_arrival, arrival)
                if block.remaining_first == 0:
                    schedule(block.last_arrival + 1e-9, "report", index, block_id)
            if capture_transmissions:
                item = {"flow": flow.config.name, "kind": kind, "token": token, "submitted_s": now,
                        "start_s": end - serial if reason != "queue_overflow" else None,
                        "end_s": end, "arrival_s": arrival, "lost": dropped, "loss_reason": reason,
                        "cwnd": flow.cwnd, "inflight": len(flow.inflight), "wire_bytes": size}
                if kind == "data":
                    item.update(sequence=sequence, attempt=attempt)
                else:
                    item.update(block_start=block_id, members=list(repair.members))
                transmissions.append(item)
            if not dropped:
                schedule(arrival, kind, index, (token, wire_payload))
            schedule(end + timeout, "timeout", index, token)
            if kind == "data":
                # A wire ACK can release congestion budget even when GBN has
                # discarded an out-of-order datum. Reliability still needs its
                # own timer until the sequence is cumulatively acknowledged.
                schedule(end + timeout, "data_timeout", index, (sequence, attempt, now))

    def acknowledge(index, token, sequences):
        flow = states[index]
        flow.stats["ack_packets"] += 1
        flow.stats["reverse_wire_bytes"] += ACK_BYTES
        arrival, dropped, _, _ = link.transmit(now, ACK_BYTES, reverse=True)
        if not dropped:
            schedule(arrival, "ack", index, (token, tuple(sequences)))

    def deliver(flow, sequence, payload, *, fec=False):
        if sequence in flow.received:
            return
        flow.received[sequence] = payload
        flow.delivery_time[sequence] = now
        flow.stats["fec_recovered"] += int(fec and flow.attempts.get(sequence) == 1)
        while flow.application_base in flow.received:
            flow.application_time[flow.application_base] = now
            flow.application_base += 1

    def queue_retry(flow, sequence):
        if sequence not in flow.acked and sequence not in flow.retry_queued:
            flow.pending.appendleft(("data", sequence, True))
            flow.retry_queued.add(sequence)

    def reduce_window(flow, submitted):
        if flow.config.congestion_control == "aimd" and submitted >= flow.last_reduction:
            flow.cwnd = max(1.0, flow.cwnd / 2)
            flow.ssthresh = max(2.0, flow.cwnd)
            flow.last_reduction = now
            flow.stats["congestion_reductions"] += 1
            cwnd_record(flow, "timeout")

    order = list(range(len(states)))
    random.Random(config.seed + 7_000_001).shuffle(order)
    for index in order:
        schedule(states[index].config.start_s, "start", index, None)
    while queue:
        if all(flow.sender_completion is not None for flow in states):
            break
        now, _, kind, index, payload = heapq.heappop(queue)
        events += 1
        if events > config.max_events:
            break
        flow = states[index]
        if kind == "start":
            pump(index)
        elif kind == "data":
            token, (sequence, attempt) = payload
            block = flow.blocks[flow.block_for[sequence]]
            if attempt == 1:
                block.first_arrivals.add(sequence - block.start)
            if flow.config.scheme == "gbn":
                if sequence == flow.receiver_base:
                    deliver(flow, sequence, flow.packets[sequence])
                    flow.receiver_base += 1
                sequences = range(flow.receiver_base)
            else:
                block.known[sequence - block.start] = flow.packets[sequence]
                deliver(flow, sequence, flow.packets[sequence])
                rebuilt = recover(block.known, block.repairs)
                for offset, packet in rebuilt.items():
                    deliver(flow, block.start + offset, packet, fec=True)
                sequences = [sequence] + [block.start + offset for offset in rebuilt]
            acknowledge(index, token, sequences)
        elif kind == "parity":
            token, (block_id, repair) = payload
            block = flow.blocks[block_id]
            block.repairs.append(repair)
            rebuilt = recover(block.known, block.repairs)
            for offset, packet in rebuilt.items():
                deliver(flow, block.start + offset, packet, fec=True)
            acknowledge(index, token, [block.start + offset for offset in rebuilt])
        elif kind == "ack":
            token, sequences = payload
            acknowledged_wire = flow.inflight.pop(token, None)
            if acknowledged_wire is not None and flow.config.congestion_control == "aimd":
                flow.cwnd = min(float(flow.config.window), flow.cwnd + (1 if flow.cwnd < flow.ssthresh else 1 / flow.cwnd))
                cwnd_record(flow, "ack")
            flow.acked.update(sequences)
            while flow.base in flow.acked:
                flow.base += 1
            if len(flow.acked) == len(flow.packets) and not flow.pending and not flow.inflight:
                flow.sender_completion = now
            else:
                pump(index)
                if len(flow.acked) == len(flow.packets) and not flow.pending and not flow.inflight:
                    flow.sender_completion = now
        elif kind == "timeout":
            packet = flow.inflight.pop(payload, None)
            if packet is None:
                continue
            packet_kind, value, submitted = packet
            flow.stats["timeouts"] += 1
            reduce_window(flow, submitted)
            pump(index)
            if len(flow.acked) == len(flow.packets) and not flow.pending and not flow.inflight:
                flow.sender_completion = now
        elif kind == "data_timeout":
            sequence, attempt, submitted = payload
            if sequence in flow.acked or flow.attempts.get(sequence) != attempt:
                continue
            reduce_window(flow, submitted)
            if flow.config.scheme == "gbn":
                if sequence == flow.base:
                    # Prepend in reverse so the cumulative base goes first.
                    for pending in reversed(range(flow.base, flow.next_sequence)):
                        queue_retry(flow, pending)
            else:
                queue_retry(flow, sequence)
            pump(index)
        elif kind == "report" and flow.config.scheme == "adaptive":
            block = flow.blocks[payload]
            flow.stats["reverse_wire_bytes"] += ACK_BYTES
            arrival, dropped, _, _ = link.transmit(now, ACK_BYTES, reverse=True)
            if not dropped:
                schedule(arrival, "feedback", index, payload)
        elif kind == "feedback":
            block = flow.blocks[payload]
            # This flow's first-pass symbols can be separated by other-flow
            # packets and retries. Counts are valid; adjacency is not. Burst
            # policy therefore uses its count-only uncertainty fallback rather
            # than learning invented neighboring-channel transitions.
            flow.controller.observe(len(block.packets) - len(block.first_arrivals), len(block.packets))

    def percentile(values):
        return values[max(0, math.ceil(0.95 * len(values)) - 1)] if values else 0.0

    flow_results = []
    for flow in states:
        output = b"".join(flow.received[i][:min(config.packet_size, len(flow.data) - i * config.packet_size)]
                          for i in range(flow.application_base))
        completed = flow.sender_completion is not None and len(flow.acked) == len(flow.packets) and len(output) == len(flow.data)
        if completed and output != flow.data:
            raise AssertionError("Shared-link recovered transfer differs from input")
        completion = max(flow.application_time.values(), default=flow.config.start_s)
        delays = sorted((flow.application_time[i] - flow.first_sent[i]) * 1000 for i in flow.application_time)
        hol = sorted((flow.application_time[i] - flow.delivery_time[i]) * 1000 for i in flow.application_time)
        flow_results.append({"name": flow.config.name, "scheme": flow.config.scheme, "config": asdict(flow.config),
                             "completed": completed, "bytes_delivered": len(output), "sha256": hashlib.sha256(output).hexdigest(),
                             "expected_sha256": hashlib.sha256(flow.data).hexdigest(), "completion_time_s": completion,
                             "duration_s": completion - flow.config.start_s, "sender_completion_time_s": flow.sender_completion,
                             "goodput_mbps": len(output) * 8 / (completion - flow.config.start_s) / 1_000_000 if completion > flow.config.start_s else 0,
                             "application_mean_delay_ms": sum(delays) / len(delays) if delays else 0,
                             "application_p95_delay_ms": percentile(delays), "head_of_line_p95_ms": percentile(hol),
                             "application_delivery": [{"sequence": sequence, "time_s": time,
                                                       "bytes": min(config.packet_size, len(flow.data) - sequence * config.packet_size),
                                                       "first_transmission_s": flow.first_sent[sequence],
                                                       "first_submission_s": flow.first_sent[sequence],
                                                       "availability_s": flow.delivery_time[sequence]}
                                                      for sequence, time in sorted(flow.application_time.items())],
                             "parity_overhead_ratio": flow.stats["parity_packets"] * config.packet_size / len(flow.data),
                             "peak_inflight_packets": flow.peak_inflight, "peak_cwnd": flow.peak_cwnd,
                             "controller_trace": flow.controller_trace, "cwnd_trace": flow.cwnd_trace, **flow.stats})
    common_start = max(flow.config.start_s for flow in states)
    common_end = min(max(flow.application_time.values(), default=flow.config.start_s) for flow in states)
    all_completed = all(row["completed"] for row in flow_results)
    common_valid = all_completed and common_end > common_start
    rates, bins = [], []
    if common_valid:
        for flow in states:
            released = sum(min(config.packet_size, len(flow.data) - sequence * config.packet_size)
                           for sequence, time in flow.application_time.items() if common_start < time <= common_end)
            rates.append(released * 8 / (common_end - common_start) / 1_000_000)
        bin_start = common_start
        while bin_start < common_end - 1e-12:
            bin_end = min(bin_start + config.measurement_bin_s, common_end)
            row = {"start_s": bin_start, "end_s": bin_end, "rates_mbps": {}}
            for flow in states:
                released = sum(min(config.packet_size, len(flow.data) - sequence * config.packet_size)
                               for sequence, time in flow.application_time.items() if bin_start < time <= bin_end)
                row["rates_mbps"][flow.config.name] = released * 8 / (bin_end - bin_start) / 1_000_000
            row["jain_fairness"] = jain_fairness(list(row["rates_mbps"].values()))
            bins.append(row)
            bin_start = bin_end
    first_start = min(flow.config.start_s for flow in states)
    final_completion = max(row["completion_time_s"] for row in flow_results)
    span = final_completion - first_start
    return {"completed": all_completed, "config": asdict(config), "events": events,
            "event_budget_exhausted": events > config.max_events, "flows": flow_results,
            "aggregate_goodput_mbps": sum(row["bytes_delivered"] for row in flow_results) * 8 / span / 1_000_000 if span else 0,
            "queue_capacity_packets": config.queue_packets, "queue_high_water_packets": link.high_water_packets,
            "queue_drops": link.queue_drops, "channel_drops": link.random_drops,
            "offered_forward_wire_bytes": link.offered_bytes, "serialized_forward_wire_bytes": link.accepted_bytes,
            "common_interval": {"valid": common_valid, "start_s": common_start, "end_s": common_end,
                                "definition": "all flows started and no flow has completed in-order application delivery",
                                "rates_mbps": {flow.config.name: rate for flow, rate in zip(states, rates, strict=True)} if common_valid else {},
                                "jain_fairness": jain_fairness(rates) if rates else None},
            "measurement_bins": bins, "transmissions": transmissions,
            "model": {"forward_link": "one shared finite-buffer FIFO serializer; capacity includes in-service packet",
                      "reverse_link": "one separate shared serializer with ACK erasures and unlimited queue",
                      "congestion_control": "ACK-clocked slow start followed by additive increase; timeout halves window once per flight epoch",
                      "congestion_budget": "every data attempt and parity packet occupies one wire slot until ACK or timeout",
                      "metadata": "receiver block descriptors known out of band; impairment metadata tests use single-flow reliable mode or socket transport",
                      "controller_feedback": "raw first-attempt data erasure counts; no adjacency inferred across interleaved flows; burst policy uses count-only fallback",
                      "application_delay_origin": "first sender submission to shared bottleneck, including forward queue wait and in-order release wait",
                      "scope": "deterministic event-driven teaching model, not TCP compatibility or Internet deployment evidence"}}
