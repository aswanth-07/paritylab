import math
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class ChannelConfig:
    loss: float = 0.05
    delay_ms: float = 50.0
    bandwidth_mbps: float = 5.0
    ack_loss: float = 0.0
    model: str = "bernoulli"
    phases: tuple[tuple[float, float], ...] = ()
    bad_to_good: float = 0.2
    jitter_ms: float = 0.0
    reorder_probability: float = 0.0
    reorder_delay_ms: float = 0.0

    def __post_init__(self):
        values = [self.loss, self.ack_loss, self.reorder_probability] + [p for _, p in self.phases]
        if any(not math.isfinite(p) or not 0 <= p <= 1 for p in values):
            raise ValueError("Loss probabilities must be finite and in [0, 1]")
        if not math.isfinite(self.delay_ms) or self.delay_ms < 0 or not math.isfinite(self.bandwidth_mbps) or self.bandwidth_mbps <= 0:
            raise ValueError("Delay must be nonnegative and bandwidth positive")
        if self.model not in {"bernoulli", "gilbert-elliott"} or not 0 < self.bad_to_good <= 1:
            raise ValueError("Invalid loss model or burst transition rate")
        if any(not math.isfinite(value) or value < 0 for value in (self.jitter_ms, self.reorder_delay_ms)):
            raise ValueError("Jitter and extra reordering delay must be finite and nonnegative")
        times = [t for t, _ in self.phases]
        if any(not math.isfinite(t) or t < 0 for t in times) or times != sorted(set(times)):
            raise ValueError("Phase start times must be unique, increasing, and nonnegative")


class Channel:
    def __init__(self, config: ChannelConfig, seed: int):
        self.config = config
        self.forward_rng = random.Random(seed)
        self.reverse_rng = random.Random(seed + 1_000_003)
        self.impairment_rng = random.Random(seed + 2_000_003)
        self.metadata_rng = random.Random(seed + 3_000_017)
        self.next_forward = self.next_reverse = 0.0
        self.bad = self.forward_rng.random() < config.loss

    def loss_at(self, time: float) -> float:
        probability = self.config.loss
        for start, loss in self.config.phases:
            if time >= start:
                probability = loss
        return probability

    def transmit(self, time: float, size: int, reverse: bool = False, *, loss_override: float | None = None) -> tuple[float, bool, float]:
        """Serialize one packet, then add nonnegative propagation impairment.

        The optional override is a separately seeded independent metadata erasure
        stream. Zero impairment makes the original seeded channel unchanged.
        """
        if not isinstance(size, int) or isinstance(size, bool) or size < 1 or not math.isfinite(time) or time < 0:
            raise ValueError("Transmission time must be nonnegative and size positive")
        if loss_override is not None and (not math.isfinite(loss_override) or not 0 <= loss_override <= 1):
            raise ValueError("Loss override must be finite and in [0, 1]")
        bandwidth = self.config.bandwidth_mbps * 1_000_000
        start = max(time, self.next_reverse if reverse else self.next_forward)
        end = start + size * 8 / bandwidth
        if reverse:
            self.next_reverse = end
            dropped = self.reverse_rng.random() < self.config.ack_loss
        else:
            self.next_forward = end
            probability = self.loss_at(end)
            if loss_override is not None:
                dropped = self.metadata_rng.random() < loss_override
            elif self.config.model == "gilbert-elliott":
                # Good state emits no erasures; bad state erases every packet.
                # The transition ratio gives stationary erasure probability p.
                leave_bad = min(self.config.bad_to_good, (1 - probability) / probability) if probability > 0 else 1.0
                enter_bad = probability * leave_bad / (1 - probability) if probability < 1 else 1.0
                if self.bad:
                    self.bad = not (self.forward_rng.random() < leave_bad)
                else:
                    self.bad = self.forward_rng.random() < enter_bad
                dropped = self.bad
            else:
                dropped = self.forward_rng.random() < probability
        extra = self.impairment_rng.uniform(0, self.config.jitter_ms) if self.config.jitter_ms else 0.0
        if self.config.reorder_probability and self.impairment_rng.random() < self.config.reorder_probability:
            extra += self.config.reorder_delay_ms
        return end + (self.config.delay_ms + extra) / 1000, dropped, end

