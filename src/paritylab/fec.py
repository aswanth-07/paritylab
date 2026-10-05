from dataclasses import dataclass
from functools import lru_cache
import math
from typing import Iterable


@dataclass(frozen=True)
class Protection:
    mode: str
    k: int
    rows: int = 0
    columns: int = 0

    def __post_init__(self):
        if self.mode not in {"none", "xor", "grid"} or self.k < 1:
            raise ValueError("Invalid protection mode or block size")
        if self.mode == "grid" and (self.rows < 1 or self.columns < 1 or self.rows * self.columns != self.k):
            raise ValueError("Grid dimensions must match block size")

    @property
    def label(self) -> str:
        return f"grid-{self.rows}x{self.columns}" if self.mode == "grid" else f"{self.mode}-{self.k}"

    @property
    def overhead(self) -> float:
        return len(equations(self)) / self.k


@dataclass(frozen=True)
class Repair:
    members: tuple[int, ...]
    payload: bytes


def xor_bytes(packets: Iterable[bytes]) -> bytes:
    packets = list(packets)
    if not packets:
        return b""
    width = len(packets[0])
    if any(len(packet) != width for packet in packets):
        raise ValueError("Pad packets to equal lengths before encoding")
    value = 0
    for packet in packets:
        value ^= int.from_bytes(packet, "big")
    return value.to_bytes(width, "big")


def equations(protection: Protection, size: int | None = None) -> list[tuple[int, ...]]:
    size = protection.k if size is None else size
    if not 0 <= size <= protection.k:
        raise ValueError("Block exceeds protection size")
    if protection.mode == "none" or size == 0:
        return []
    if protection.mode == "xor":
        return [tuple(range(size))]
    groups = [tuple(range(r * protection.columns, (r + 1) * protection.columns)) for r in range(protection.rows)]
    groups += [tuple(range(c, protection.k, protection.columns)) for c in range(protection.columns)]
    return [group for original in groups if (group := tuple(i for i in original if i < size))]


def encode(packets: list[bytes], protection: Protection) -> list[Repair]:
    return [Repair(group, xor_bytes(packets[i] for i in group)) for group in equations(protection, len(packets))]


def recover(known: dict[int, bytes], repairs: Iterable[Repair]) -> dict[int, bytes]:
    """Peel equations with one missing packet until no further repair is possible."""
    repairs = list(repairs)
    recovered = {}
    while True:
        progress = False
        for repair in repairs:
            missing = [i for i in repair.members if i not in known]
            if len(missing) == 1:
                index = missing[0]
                known[index] = xor_bytes([repair.payload] + [known[i] for i in repair.members if i != index])
                recovered[index] = known[index]
                progress = True
        if not progress:
            return recovered


def _size(protection: Protection, size: int | None) -> int:
    size = protection.k if size is None else size
    if not isinstance(size, int) or isinstance(size, bool) or not 0 <= size <= protection.k:
        raise ValueError("Block size must be an integer within the protection size")
    return size


def _peeling_fails(missing: int, active: list[int]) -> bool:
    while missing:
        before = missing
        for group in active:
            unknown = missing & group
            if unknown and unknown & (unknown - 1) == 0:
                missing &= ~unknown
        if before == missing:
            break
    return bool(missing)


@lru_cache(maxsize=128)
def failure_counts(protection: Protection, size: int | None = None) -> tuple[int, ...]:
    """Count failing erasure patterns, including repair erasures, for small grids."""
    size = _size(protection, size)
    groups = [sum(1 << i for i in group) for group in equations(protection, size)]
    total = size + len(groups)
    if total > 16:
        raise ValueError("Exact risk enumeration is limited to 16 transmitted symbols")
    counts = [0] * (total + 1)
    data_mask = (1 << size) - 1
    for erased in range(1 << total):
        missing = erased & data_mask
        active = [group for j, group in enumerate(groups) if not erased & (1 << (size + j))]
        if _peeling_fails(missing, active):
            counts[erased.bit_count()] += 1
    return tuple(counts)


def failure_probability(protection: Protection, loss: float, *, size: int | None = None) -> float:
    if not math.isfinite(loss) or not 0 <= loss <= 1:
        raise ValueError("Loss probability must be between zero and one")
    size = _size(protection, size)
    q = 1 - loss
    if protection.mode == "none":
        return 1 - q ** size
    if protection.mode == "xor":
        # Success: no missing data, or one missing datum and surviving parity.
        return max(0.0, 1 - q ** size - size * loss * q ** size)
    counts = failure_counts(protection, size)
    n = len(counts) - 1
    return sum(count * loss ** erased * q ** (n - erased) for erased, count in enumerate(counts))


@lru_cache(maxsize=128)
def _markov_terms(protection: Protection, size: int) -> tuple[tuple[int, ...], ...]:
    """Group failing patterns by first outcome and transition counts."""
    groups = [sum(1 << i for i in group) for group in equations(protection, size)]
    total = size + len(groups)
    if total > 20:
        raise ValueError("Exact Markov risk is limited to 20 transmitted symbols")
    if total == 0:
        return ()
    data_mask = (1 << size) - 1
    terms = {}
    for erased in range(1 << total):
        active = [group for j, group in enumerate(groups) if not erased & (1 << (size + j))]
        if not _peeling_fails(erased & data_mask, active):
            continue
        counts = [0, 0, 0, 0]
        previous = erased & 1
        for j in range(1, total):
            current = (erased >> j) & 1
            counts[2 * previous + current] += 1
            previous = current
        key = (erased & 1, *counts)
        terms[key] = terms.get(key, 0) + 1
    return tuple((*key, count) for key, count in terms.items())


def _probability(value: float) -> float:
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("Transition and initial probabilities must be finite and in [0, 1]")
    return value


def markov_failure_probability(protection: Protection, good_to_bad: float, bad_to_good: float,
                               *, initial_loss: float | None = None, size: int | None = None) -> float:
    """Exact risk for binary Markov erasures in data-then-repair wire order.

    Good emits a received symbol; bad emits an erased symbol. initial_loss is
    the probability that the FIRST transmitted symbol is erased. Its default
    is the stationary probability, which requires a nonzero transition sum.
    General hidden-state Gilbert-Elliott emissions are outside this model.
    """
    size = _size(protection, size)
    a, b = _probability(good_to_bad), _probability(bad_to_good)
    if size == 0:
        return 0.0
    if initial_loss is None:
        if a + b == 0:
            raise ValueError("An absorbing chain needs an explicit initial loss probability")
        initial_loss = a / (a + b)
    initial_loss = _probability(initial_loss)
    risk = sum(count * (initial_loss if first else 1 - initial_loss)
               * (1 - a) ** n00 * a ** n01 * b ** n10 * (1 - b) ** n11
               for first, n00, n01, n10, n11, count in _markov_terms(protection, size))
    return min(1.0, max(0.0, risk))


def _kernel_max(successes: int, failures: int, bounds: tuple[float, float]) -> float:
    lo, hi = bounds
    total = successes + failures
    probability = min(hi, max(lo, successes / total)) if total else lo
    return probability ** successes * (1 - probability) ** failures


def markov_failure_upper_bound(protection: Protection, good_to_bad_bounds: tuple[float, float],
                               bad_to_good_bounds: tuple[float, float], *,
                               initial_loss_bounds: tuple[float, float] = (0.0, 1.0),
                               size: int | None = None) -> float:
    """Conservative risk over the supplied parameter rectangle.

    Sum the separate maximum probability of each failing pattern class. This
    may be loose, but bounds every binary Markov chain inside the rectangle.
    It is NOT a confidence guarantee that an estimated rectangle contains the
    true process, and does not bound non-Markov or changing loss processes.
    """
    size = _size(protection, size)
    bounds = (good_to_bad_bounds, bad_to_good_bounds, initial_loss_bounds)
    for lo, hi in bounds:
        _probability(lo)
        _probability(hi)
        if lo > hi:
            raise ValueError("Probability interval endpoints are reversed")
    initial_lo, initial_hi = initial_loss_bounds
    risk = sum(count * (initial_hi if first else 1 - initial_lo)
               * _kernel_max(n01, n00, good_to_bad_bounds)
               * _kernel_max(n10, n11, bad_to_good_bounds)
               for first, n00, n01, n10, n11, count in _markov_terms(protection, size))
    return min(1.0, max(0.0, risk))

