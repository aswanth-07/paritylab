import math
from collections import deque
from dataclasses import dataclass
from statistics import NormalDist
from typing import Iterable

from .fec import (Protection, equations, failure_probability, markov_failure_probability,
                  markov_failure_upper_bound)

POLICIES = ("legacy", "uncertainty", "burst", "cost")


def wilson_interval(successes: int, total: int, confidence: float = 0.95) -> tuple[float, float]:
    """Approximate two-sided binomial interval; no samples yields [0, 1]."""
    if (not isinstance(successes, int) or not isinstance(total, int)
            or isinstance(successes, bool) or isinstance(total, bool)
            or not 0 <= successes <= total):
        raise ValueError("Interval counts must be valid nonnegative integers")
    if not math.isfinite(confidence) or not 0 < confidence < 1:
        raise ValueError("Confidence must be finite and between zero and one")
    if total == 0:
        return 0.0, 1.0
    z = NormalDist().inv_cdf((1 + confidence) / 2)
    p, z2 = successes / total, z * z
    center = (p + z2 / (2 * total)) / (1 + z2 / total)
    half = z * math.sqrt(p * (1 - p) / total + z2 / (4 * total ** 2)) / (1 + z2 / total)
    return max(0.0, center - half), min(1.0, center + half)


@dataclass(frozen=True)
class Choice:
    protection: Protection
    predicted_failure: float
    target_met: bool
    estimated_loss: float
    risk_model: str = "independent point estimate"
    loss_lower: float = 0.0
    loss_upper: float = 0.0
    observed_symbols: int = 0
    estimated_failure: float = 0.0
    uncertainty_applied: bool = False
    assumptions: str = "independent identical data and parity erasures; model target, not a guarantee"
    transition_samples: int = 0
    good_to_bad: float | None = None
    bad_to_good: float | None = None
    objective: str = "block failure target"
    estimated_cost_per_packet_s: float | None = None
    unprotected_cost_per_packet_s: float | None = None
    candidate_costs: tuple[dict, ...] = ()


class AdaptiveController:
    def __init__(self, window: int = 32, alpha: float = 0.25, target: float = 0.01, *,
                 policy: str = "legacy", confidence: float = 0.95, history_size: int = 512,
                 packet_serial_s: float | None = None, retry_wait_s: float | None = None):
        if (not isinstance(window, int) or isinstance(window, bool) or window < 1
                or not math.isfinite(alpha) or not 0 < alpha <= 1
                or not math.isfinite(target) or not 0 < target < 1
                or policy not in POLICIES or not math.isfinite(confidence) or not 0 < confidence < 1
                or not isinstance(history_size, int) or isinstance(history_size, bool) or history_size < 2):
            raise ValueError("Invalid controller window, smoothing factor, target, policy, or history")
        self.alpha, self.target, self.estimate = alpha, target, 0.0
        self.policy, self.confidence, self.history_size = policy, confidence, history_size
        if policy == "cost" and any(value is None or not math.isfinite(value) or value <= 0
                                     for value in (packet_serial_s, retry_wait_s)):
            raise ValueError("Cost policy requires positive finite serialization and retry times")
        self.packet_serial_s, self.retry_wait_s = packet_serial_s, retry_wait_s
        self.candidates = [Protection("none", min(16, window))]
        self.candidates += [Protection("xor", k) for k in (16, 8, 4, 2) if k <= window]
        self.candidates += [Protection("grid", r * c, r, c) for r, c in ((3, 3), (2, 3), (2, 2)) if r * c <= window]
        self._batches = deque()
        self._lost = self._samples = 0
        self._pairs = deque(maxlen=history_size - 1)
        self._previous = None

    def _observe_counts(self, lost: int, transmitted: int):
        if (not isinstance(lost, int) or not isinstance(transmitted, int)
                or isinstance(lost, bool) or isinstance(transmitted, bool)
                or not 0 <= lost <= transmitted or transmitted < 1):
            raise ValueError("Feedback must contain valid original transmission counts")
        # Sixteen symbols retain the incumbent update weight. Short reports
        # carry proportionally less evidence; long reports carry more.
        weight = 1 - (1 - self.alpha) ** (transmitted / 16) if self.policy == "cost" else self.alpha
        self.estimate = (1 - weight) * self.estimate + weight * lost / transmitted
        self._batches.append((lost, transmitted))
        self._lost += lost
        self._samples += transmitted
        # Keep complete batches; a single batch larger than history_size is kept.
        while len(self._batches) > 1 and self._samples > self.history_size:
            old_lost, old_total = self._batches.popleft()
            self._lost -= old_lost
            self._samples -= old_total

    def observe(self, lost: int, transmitted: int):
        self._observe_counts(lost, transmitted)
        # Aggregate feedback has no usable packet ordering.
        self._previous = None

    def observe_sequence(self, losses: Iterable[bool], *, contiguous: bool = True):
        """Observe ordered raw erasures before repair, including parity losses.

        Set contiguous=False across gaps such as omitted retries or repairs.
        Only adjacent supplied outcomes contribute a transition. Do not infer
        these outcomes from losses remaining after forward error correction.
        """
        losses = tuple(losses)
        if not losses or any(not isinstance(lost, bool) for lost in losses):
            raise ValueError("Raw loss sequence must contain one or more booleans")
        if not isinstance(contiguous, bool):
            raise ValueError("Sequence continuity must be explicit")
        self._observe_counts(sum(losses), len(losses))
        if not contiguous:
            self._previous = None
        for lost in losses:
            if self._previous is not None:
                self._pairs.append((self._previous, lost))
            self._previous = lost

    def loss_interval(self) -> tuple[float, float]:
        """Binomial interval valid only under a stationary independent model."""
        return wilson_interval(self._lost, self._samples, self.confidence)

    def burst_statistics(self) -> dict:
        counts = [0, 0, 0, 0]
        for previous, current in self._pairs:
            counts[2 * int(previous) + int(current)] += 1
        n00, n01, n10, n11 = counts
        # Bonferroni adjustment for two approximate transition intervals.
        confidence = 1 - (1 - self.confidence) / 2
        a_bounds = wilson_interval(n01, n00 + n01, confidence)
        b_bounds = wilson_interval(n10, n10 + n11, confidence)
        a = n01 / (n00 + n01) if n00 + n01 else None
        b = n10 / (n10 + n11) if n10 + n11 else None
        return {"good_to_bad": a, "bad_to_good": b, "good_to_bad_bounds": a_bounds,
                "bad_to_good_bounds": b_bounds, "transition_samples": sum(counts),
                "counts": {"00": n00, "01": n01, "10": n10, "11": n11}}

    def choose(self, *, size: int | None = None) -> Choice:
        if size is not None and (not isinstance(size, int) or isinstance(size, bool) or size < 1):
            raise ValueError("Remaining block size must be a positive integer")
        candidates = [(p, min(size, p.k) if size is not None else p.k) for p in self.candidates]
        if self.policy == "cost":
            rows = []
            for protection, actual in candidates:
                parity = len(equations(protection, actual))
                risk = failure_probability(protection, self.estimate, size=actual)
                # One timeout per unresolved block is a cost proxy, not a
                # prediction of transfer duration or a reliability guarantee.
                cost = ((actual + parity) * self.packet_serial_s + risk * self.retry_wait_s) / actual
                rows.append((cost, parity / actual, -actual, protection, risk))
            cost, _, _, protection, risk = min(rows, key=lambda row: row[:3])
            return Choice(protection, risk, risk <= self.target, self.estimate,
                          risk_model="independent transfer cost", loss_lower=self.estimate,
                          loss_upper=self.estimate, observed_symbols=self._samples,
                          estimated_failure=risk, objective="serialization plus residual timeout cost",
                          assumptions="independent identical erasures; one timeout per unresolved block; cost proxy, not a duration prediction",
                          estimated_cost_per_packet_s=cost, unprotected_cost_per_packet_s=rows[0][0],
                          candidate_costs=tuple({"mode": row[3].label, "cost_per_packet_s": row[0],
                                                 "predicted_failure": row[4]} for row in rows))
        lower, upper = self.loss_interval()
        mean = self._lost / self._samples if self._samples else 0.0
        statistics = self.burst_statistics()
        a, b = statistics["good_to_bad"], statistics["bad_to_good"]
        burst_ready = (self.policy == "burst" and a is not None and b is not None and a + b > 0
                       and statistics["transition_samples"] >= 16)
        risks = []
        if self.policy == "legacy":
            model = "independent point estimate"
            assumptions = "independent identical data and parity erasures; model target, not a guarantee"
            for p, actual in candidates:
                risk = failure_probability(p, self.estimate, size=actual)
                risks.append((p, actual, risk, risk))
            lower = upper = self.estimate
        elif burst_ready:
            model = "binary Markov parameter envelope"
            assumptions = ("stationary binary first-order Markov erasures; data then repairs; "
                           "raw adjacent outcomes; approximate transition intervals; no guarantee under model mismatch")
            a_bounds, b_bounds = statistics["good_to_bad_bounds"], statistics["bad_to_good_bounds"]
            lower = a_bounds[0] / (a_bounds[0] + b_bounds[1]) if a_bounds[0] + b_bounds[1] else 0.0
            upper = a_bounds[1] / (a_bounds[1] + b_bounds[0]) if a_bounds[1] + b_bounds[0] else 1.0
            for p, actual in candidates:
                point = markov_failure_probability(p, a, b, size=actual)
                bound = markov_failure_upper_bound(p, a_bounds, b_bounds,
                                                   initial_loss_bounds=(lower, upper), size=actual)
                risks.append((p, actual, bound, point))
            mean = a / (a + b)
        else:
            model = "independent Wilson upper estimate"
            assumptions = ("stationary independent identical erasures; approximate binomial interval; "
                           "model target, not a guarantee")
            if self.policy == "burst":
                assumptions += "; insufficient ordered transition feedback, independent fallback"
            for p, actual in candidates:
                risks.append((p, actual, failure_probability(p, upper, size=actual),
                              failure_probability(p, mean, size=actual)))
        feasible = [row for row in risks if row[2] <= self.target]
        if feasible:
            chosen = min(feasible, key=lambda row: (len(equations(row[0], row[1])) / row[1], -row[1]))
        else:
            chosen = min(risks, key=lambda row: (row[2], len(equations(row[0], row[1])) / row[1]))
        protection, _, risk, point = chosen
        return Choice(protection, risk, bool(feasible), self.estimate if self.policy == "legacy" else mean,
                      model, lower, upper, self._samples, point, self.policy != "legacy", assumptions,
                      statistics["transition_samples"], a, b)

