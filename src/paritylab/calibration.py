"""Reproduce decoder risk calibration without a network or third-party runtime."""

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import platform
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .controller import AdaptiveController, wilson_interval
from .fec import Protection, encode, failure_probability, markov_failure_probability, recover


@dataclass(frozen=True)
class CalibrationCase:
    name: str
    protection: Protection
    size: int
    model: str
    loss: float
    good_to_bad: float = 0.0
    bad_to_good: float = 0.0
    previous_loss: bool | None = None

    @property
    def prediction(self) -> float:
        if self.model == "independent":
            return failure_probability(self.protection, self.loss, size=self.size)
        initial = (1 - self.bad_to_good if self.previous_loss else self.good_to_bad
                   ) if self.previous_loss is not None else self.loss
        return markov_failure_probability(self.protection, self.good_to_bad, self.bad_to_good,
                                           initial_loss=initial, size=self.size)


def calibration_cases() -> list[CalibrationCase]:
    protections = [(Protection("none", 16), 16), (Protection("xor", 16), 16),
                   (Protection("xor", 8), 8), (Protection("xor", 2), 2),
                   (Protection("grid", 9, 3, 3), 9), (Protection("grid", 6, 2, 3), 6),
                   (Protection("grid", 4, 2, 2), 4), (Protection("grid", 9, 3, 3), 5),
                   (Protection("grid", 4, 2, 2), 1)]
    cases = []
    for loss in (0.0, 0.01, 0.03, 0.1, 0.2, 0.5, 1.0):
        for protection, size in protections:
            cases.append(CalibrationCase(f"iid-p{loss:g}-{protection.label}-n{size}",
                                         protection, size, "independent", loss))
    burst_protections = [protections[i] for i in (2, 3, 4, 6, 7)]
    for loss in (0.03, 0.1, 0.2):
        for b in (0.2, 0.5):
            a = loss * b / (1 - loss)
            for previous in (None, False, True):
                initial = "stationary" if previous is None else "after-lost" if previous else "after-received"
                for protection, size in burst_protections:
                    name = f"markov-p{loss:g}-b{b:g}-{initial}-{protection.label}-n{size}"
                    cases.append(CalibrationCase(name, protection, size, "binary_markov", loss, a, b, previous))
    return cases


def _sequence(rng: random.Random, count: int, model: str, loss: float, a: float = 0.0,
              b: float = 0.0, previous: bool | None = None) -> list[bool]:
    if model == "independent":
        return [rng.random() < loss for _ in range(count)]
    initial = (1 - b if previous else a) if previous is not None else loss
    state = rng.random() < initial
    outcomes = [state]
    for _ in range(count - 1):
        state = rng.random() < (1 - b if state else a)
        outcomes.append(state)
    return outcomes


def _decode_trial(packets, repairs, losses) -> bool:
    size = len(packets)
    known = {i: packet for i, packet in enumerate(packets) if not losses[i]}
    recover(known, [repair for i, repair in enumerate(repairs) if not losses[size + i]])
    if any(packets[i] != payload for i, payload in known.items()):
        raise AssertionError("The byte decoder produced an incorrect packet")
    return len(known) != size


def _write_csv(path: Path, rows: list[dict]):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _policy_study(output: Path, seeds: int, trials: int) -> list[dict]:
    """Train on supplied raw outcomes; test on independent fresh block draws."""
    rows = []
    for model, loss, b in (("independent", 0.03, 0.0), ("independent", 0.1, 0.0),
                            ("binary_markov", 0.1, 0.2), ("binary_markov", 0.2, 0.5),
                            ("fixed_runs", 0.1, 0.1)):
        a = loss * b / (1 - loss) if b else 0.0
        for history in (64, 512, 4096):
            for seed in range(seeds):
                rng = random.Random(8_000_003 + seed * 100_003 + history)
                if model == "fixed_runs":
                    phase = rng.randrange(100)
                    losses = [(i + phase) % 100 >= 90 for i in range(history)]
                else:
                    losses = _sequence(rng, history, model, loss, a, b)
                for policy in ("legacy", "uncertainty", "burst"):
                    controller = AdaptiveController(policy=policy, alpha=1, history_size=max(2, history))
                    controller.observe_sequence(losses)
                    choice = controller.choose()
                    protection = choice.protection
                    packets = [bytes((i, 0, 255, i ^ 170)) for i in range(protection.k)]
                    repairs = encode(packets, protection)
                    symbol_count = len(packets) + len(repairs)
                    test_rng = random.Random(19_000_003 + seed * 100_003 + history)
                    failures = 0
                    for _ in range(trials):
                        if model == "fixed_runs":
                            phase = test_rng.randrange(100)
                            test_losses = [(i + phase) % 100 >= 90 for i in range(symbol_count)]
                        else:
                            test_losses = _sequence(test_rng, symbol_count, model, loss, a, b)
                        failures += _decode_trial(packets, repairs, test_losses)
                    lo, hi = wilson_interval(failures, trials)
                    exact_risk = (failure_probability(protection, loss) if model == "independent"
                                  else markov_failure_probability(protection, a, b) if model == "binary_markov"
                                  else None)
                    statistics = controller.burst_statistics()
                    a_lo, a_hi = statistics["good_to_bad_bounds"]
                    b_lo, b_hi = statistics["bad_to_good_bounds"]
                    row = {"model": model, "loss": loss, "true_good_to_bad": a if b else None,
                           "true_bad_to_good": b if b else None, "history": history, "seed": seed,
                           "policy": policy, "chosen": protection.label, "parity_ratio": protection.overhead,
                           "target_met": choice.target_met, "predicted_failure": choice.predicted_failure,
                           "estimated_failure": choice.estimated_failure, "true_model_failure": exact_risk,
                           "trials": trials, "failures": failures, "empirical_failure": failures / trials,
                           "ci95_low": lo, "ci95_high": hi, "risk_model": choice.risk_model,
                           "estimated_loss": choice.estimated_loss, "loss_low": choice.loss_lower,
                           "loss_high": choice.loss_upper, "estimated_good_to_bad": choice.good_to_bad,
                           "estimated_bad_to_good": choice.bad_to_good,
                           "transition_rectangle_contains_truth": a_lo <= a <= a_hi and b_lo <= b <= b_hi if b and model != "fixed_runs" else None,
                           "upper_below_true_model_failure": choice.predicted_failure + 1e-12 < exact_risk if exact_risk is not None else None,
                           "training_erasure_hex": format(sum(int(v) << i for i, v in enumerate(losses)), "x"),
                           "transition_counts": json.dumps(statistics["counts"], sort_keys=True)}
                    rows.append(row)
    _write_csv(output / "policy-validation.csv", rows)
    return rows


def run_calibration(output: Path, *, seeds: int = 5, trials_per_seed: int = 4000,
                    plots: bool = True) -> dict:
    """Write raw erasures, decoder outcomes, interval summaries and model tests."""
    if (not isinstance(seeds, int) or isinstance(seeds, bool) or seeds < 1
            or not isinstance(trials_per_seed, int) or isinstance(trials_per_seed, bool) or trials_per_seed < 1):
        raise ValueError("Calibration seeds and trials must be positive integers")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    cases = calibration_cases()
    summaries, seed_rows = [], []
    raw_path = output / "raw-trials.csv.gz"
    # Fixed gzip time keeps identical raw data identical across reruns.
    with raw_path.open("wb") as binary, gzip.GzipFile(fileobj=binary, mode="wb", mtime=0) as compressed:
        with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as raw:
            writer = csv.writer(raw)
            writer.writerow(("case", "seed", "trial", "erased_mask", "decoder_failed"))
            for case_index, case in enumerate(cases):
                packets = [bytes((i, 0, 255, i ^ 170)) for i in range(case.size)]
                repairs = encode(packets, case.protection)
                total = len(packets) + len(repairs)
                failures = 0
                for seed in range(seeds):
                    rng_seed = 1_000_003 + case_index * 100_003 + seed
                    rng = random.Random(rng_seed)
                    seed_failures = 0
                    for trial in range(trials_per_seed):
                        losses = _sequence(rng, total, case.model, case.loss, case.good_to_bad,
                                           case.bad_to_good, case.previous_loss)
                        failed = _decode_trial(packets, repairs, losses)
                        erased = sum(int(value) << i for i, value in enumerate(losses))
                        writer.writerow((case_index, seed, trial, erased, int(failed)))
                        seed_failures += failed
                    seed_rows.append({"case": case_index, "name": case.name, "model": case.model,
                                      "seed": seed, "rng_seed": rng_seed, "trials": trials_per_seed,
                                      "failures": seed_failures, "failure_rate": seed_failures / trials_per_seed})
                    failures += seed_failures
                n = seeds * trials_per_seed
                empirical = failures / n
                lo, hi = wilson_interval(failures, n)
                # Union bound across the registered cases, not individual 95% intervals.
                tolerance = math.sqrt(math.log(2 * len(cases) / 0.01) / (2 * n))
                prediction = case.prediction
                iid_prediction = failure_probability(case.protection, case.loss, size=case.size)
                summaries.append({"case": case_index, "name": case.name, "model": case.model,
                                  "protection": case.protection.label, "data_symbols": case.size,
                                  "repair_symbols": len(repairs), "loss": case.loss,
                                  "good_to_bad": case.good_to_bad, "bad_to_good": case.bad_to_good,
                                  "previous_loss": case.previous_loss, "prediction": prediction,
                                  "iid_prediction": iid_prediction, "trials": n, "failures": failures,
                                  "empirical_failure": empirical, "ci95_low": lo, "ci95_high": hi,
                                  "point_in_ci95": lo - 1e-12 <= prediction <= hi + 1e-12,
                                  "absolute_error": abs(empirical - prediction),
                                  "simultaneous_error_bound99": tolerance,
                                  "within_simultaneous_bound99": abs(empirical - prediction) <= tolerance,
                                  "iid_absolute_error": abs(empirical - iid_prediction)})
                if (case_index + 1) % 15 == 0:
                    print(f"Calibrated {case_index + 1}/{len(cases)} decoder conditions", flush=True)
    _write_csv(output / "seed-counts.csv", seed_rows)
    _write_csv(output / "summary.csv", summaries)
    policy_rows = _policy_study(output, max(5, seeds), min(trials_per_seed, 1000))
    source_paths = [Path(__file__), Path(__file__).with_name("fec.py"), Path(__file__).with_name("controller.py")]
    manifest = {"created_utc": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
                "seeds": list(range(seeds)), "trials_per_seed": trials_per_seed, "cases": len(cases),
                "decoder_trials": len(cases) * seeds * trials_per_seed,
                "seed_formula": "1000003 + case_index * 100003 + seed",
                "byte_decoder_wrong_recoveries": 0, "raw_format": "data bits first, then encode() repair order; little-endian bit positions",
                "confidence_intervals": "two-sided 95% Wilson per condition, approximate binomial sampling intervals",
                "simultaneous_check": "99% Hoeffding union bound across all registered conditions; blocks sampled independently",
                "all_exact_predictions_within_simultaneous_bound99": all(row["within_simultaneous_bound99"] for row in summaries),
                "predictions_outside_ci95": sum(not row["point_in_ci95"] for row in summaries),
                "maximum_exact_absolute_error": max(row["absolute_error"] for row in summaries),
                "maximum_wrong_iid_burst_error": max(row["iid_absolute_error"] for row in summaries if row["model"] == "binary_markov"),
                "maximum_wrong_iid_stationary_burst_error": max(row["iid_absolute_error"] for row in summaries
                                                                 if row["model"] == "binary_markov" and row["previous_loss"] is None),
                "policy_validation_rows": len(policy_rows), "policy_test_trials": sum(row["trials"] for row in policy_rows),
                "plots_generated": plots,
                "model_scope": "stationary independent losses or binary first-order Markov erasures; known case parameters; byte peeling decoder; block failure before retransmission",
                "limits": ["No confidence guarantee for changing or non-Markov loss", "General hidden-state emissions and unequal data/parity loss probabilities are not modeled",
                           "Independent blocks validate a block model; this is not an end-to-end transport or congestion result",
                           "Transition Wilson intervals are approximate and evaluated empirically; parameter coverage is not guaranteed",
                           "The burst risk envelope is conservative only when its parameter rectangle contains the true Markov model"],
                "source_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths},
                "artifacts_sha256": {name: hashlib.sha256((output / name).read_bytes()).hexdigest()
                                     for name in ("raw-trials.csv.gz", "seed-counts.csv", "summary.csv", "policy-validation.csv")}}
    if plots:
        _plot(output, summaries)
        manifest["artifacts_sha256"]["calibration.png"] = hashlib.sha256((output / "calibration.png").read_bytes()).hexdigest()
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    _write_report(output, summaries, policy_rows, manifest, include_plot=plots)
    return {"manifest": manifest, "summary": summaries, "policy_validation": policy_rows}


def _write_report(output: Path, summaries: list[dict], policy_rows: list[dict], manifest: dict, *, include_plot: bool):
    report = ["# Block risk calibration", "",
              f"The byte decoder processed {manifest['decoder_trials']:,} blocks across {manifest['cases']} registered conditions and {len(manifest['seeds'])} seeds per condition. It produced no incorrect recovered bytes.", "",
              "Loss masks include erased data and repair symbols. Full and partial blocks use the exact repair list from the byte encoder. A failure means that the first data-plus-repair transmission leaves at least one original packet missing before retransmission.", "",
              "Independent predictions use the independent erasure formula. Burst predictions enumerate the same failing patterns with their binary Markov sequence probabilities. Good receives every symbol; bad erases every symbol. Each trial independently samples either a stationary starting state or the next state conditional on an explicitly received or lost preceding symbol. These conditional trials do not treat the stationary loss fraction as the next-symbol loss probability.", "",
              f"All predictions inside the simultaneous 99% sampling-error bound: **{manifest['all_exact_predictions_within_simultaneous_bound99']}**. Maximum absolute error: {manifest['maximum_exact_absolute_error']:.5f}. {manifest['predictions_outside_ci95']} point predictions lie outside their individual 95% Wilson intervals; individual intervals are approximate and a collection is expected to have misses.", "",
              f"Applying an independent prediction to stationary burst conditions gives a maximum absolute error of {manifest['maximum_wrong_iid_stationary_burst_error']:.5f}; the maximum rises to {manifest['maximum_wrong_iid_burst_error']:.5f} when it also ignores a specified preceding outcome. This demonstrates why an independent risk target cannot be read as a burst-loss guarantee.", "",
              "| Model | Protection | Actual size | Starting condition | Prediction | Measured failure | 95% interval |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    for row in summaries:
        if row["loss"] != 0.1 or row["protection"] not in {"xor-8", "grid-3x3"}:
            continue
        if row["model"] == "binary_markov" and row["bad_to_good"] != 0.2:
            continue
        start = "stationary" if row["previous_loss"] is None else "after lost" if row["previous_loss"] else "after received"
        report.append(f"| {row['model']} | {row['protection']} | {row['data_symbols']} | {start} | {row['prediction']:.4f} | {row['empirical_failure']:.4f} | [{row['ci95_low']:.4f}, {row['ci95_high']:.4f}] |")
    report += ["", "## Estimated policy checks", "",
               "The optional uncertainty policy uses the upper end of a Wilson interval from complete recent raw-loss batches. The burst policy uses adjacent raw loss outcomes to estimate good-to-bad and bad-to-good transition rates. It adds approximate, Bonferroni-adjusted transition intervals and sums each failing pattern's maximum probability over that parameter rectangle. That envelope bounds modeled risk only if the rectangle and stationary binary Markov assumptions are correct. It may be too conservative to meet the target.", "",
               "The legacy policy keeps its original smoothed point estimate and choices. The new policies are explicit options. Aggregate lost/transmitted feedback provides no ordering, so burst mode falls back to the independent uncertainty policy until at least 16 adjacent transitions and both departure states have been observed. Omitted forward packets break adjacency. Reports use raw first-attempt erasures before repair, rather than residual losses after repair.", "",
               "Training checks use histories of 64, 512 and 4096 raw outcomes, all three policies, independent and binary Markov models, and a model-mismatch challenge with a repeated 90 received / 10 erased sequence. Test blocks are new independent draws from the configured model, or independent random starting offsets for the fixed-run challenge. `policy-validation.csv` includes every training sequence as a hexadecimal bit mask, transition counts, chosen protection, predicted risk and measured failures.", "",
               "| Data model | Policy | Cases | Predictions below true modeled risk | Target claimed but measured lower interval above 1% |",
               "| --- | --- | --- | --- | --- |"]
    for model in ("independent", "binary_markov", "fixed_runs"):
        for policy in ("legacy", "uncertainty", "burst"):
            rows = [row for row in policy_rows if row["model"] == model and row["policy"] == policy]
            below = sum(bool(row["upper_below_true_model_failure"]) for row in rows) if model != "fixed_runs" else "not defined"
            misses = sum(row["target_met"] and row["ci95_low"] > 0.01 for row in rows)
            report.append(f"| {model} | {policy} | {len(rows)} | {below} | {misses} |")
    rectangle_rows = [row for row in policy_rows if row["model"] == "binary_markov" and row["policy"] == "burst"
                      and row["risk_model"] == "binary Markov parameter envelope"]
    rectangle_misses = sum(not row["transition_rectangle_contains_truth"] for row in rectangle_rows)
    envelope_violations = sum(row["transition_rectangle_contains_truth"] and row["upper_below_true_model_failure"] for row in rectangle_rows)
    fallback_rows = [row for row in policy_rows if row["model"] == "binary_markov" and row["policy"] == "burst"
                     and row["risk_model"] != "binary Markov parameter envelope"]
    report += ["", f"For fitted burst cases with an active Markov envelope, {rectangle_misses}/{len(rectangle_rows)} estimated transition rectangles excluded the true parameters. Among rectangles that included them, {envelope_violations} risk envelopes fell below the exact stationary risk. {len(fallback_rows)} burst-policy cases lacked usable transitions and used the independent fallback; a fallback does not bound burst risk. These counts are finite checks, not a coverage proof.", "",
               "Fixed-run results expose a first-order model's limits. Alternating-state or deterministic-duration bursts, abrupt changes, missing feedback and hidden-state emission processes can invalidate the estimates. Neither an estimated target nor a confidence label establishes a bound for those processes. A sender still uses retransmission and byte verification.", "",
               "## Reproduce", "", "```powershell", "python -m paritylab.calibration --output output/calibration --seeds 5 --trials-per-seed 4000", "```", "",
               "The manifest stores source and raw-data hashes, seed rules, sample counts and model limits. `raw-trials.csv.gz` stores every loss mask and byte-decoder outcome; `seed-counts.csv` stores seed totals; `summary.csv` stores full predictions and intervals. The default library needs no third-party dependencies. Add the plots extra for the calibration figure."]
    if include_plot:
        report += ["", "![Predicted and measured block failure](calibration.png)"]
    (output / "results.md").write_text("\n".join(report) + "\n", encoding="utf-8")


def _plot(output: Path, rows: list[dict]):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(11, 5), constrained_layout=True)
    for axis, model, title in zip(axes, ("independent", "binary_markov"),
                                  ("Independent data and repair erasures", "Binary Markov: stationary and conditional starts"), strict=True):
        selected = [row for row in rows if row["model"] == model]
        axis.errorbar([r["prediction"] for r in selected], [r["empirical_failure"] for r in selected],
                      yerr=([max(0.0, r["empirical_failure"] - r["ci95_low"]) for r in selected],
                            [max(0.0, r["ci95_high"] - r["empirical_failure"]) for r in selected]),
                      fmt="o", markersize=3, alpha=0.65, color="#1d7168", label="95% Wilson interval")
        axis.plot([0, 1], [0, 1], color="#a84929", linestyle="--", linewidth=1)
        axis.set(xlabel="Exact model prediction", ylabel="Byte-decoder failure fraction", title=title,
                 xlim=(-0.02, 1.02), ylim=(-0.02, 1.02))
        axis.grid(alpha=0.15)
    fig.savefig(output / "calibration.png", dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("output/calibration"))
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--trials-per-seed", type=int, default=4000)
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()
    result = run_calibration(args.output, seeds=args.seeds, trials_per_seed=args.trials_per_seed,
                             plots=not args.no_plots)
    print(json.dumps(result["manifest"], indent=2))


if __name__ == "__main__":
    main()
