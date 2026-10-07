"""Run the predeclared controller comparison without overwriting prior runs."""
import argparse
import csv
import gzip
import hashlib
import json
import math
import statistics
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

from paritylab.channel import ChannelConfig
from paritylab.experiments import sample_data
from paritylab.simulation import SimulationConfig, simulate

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ("src/paritylab/controller.py", "src/paritylab/fec.py", "src/paritylab/simulation.py",
           "src/paritylab/channel.py", "src/paritylab/experiments.py", "scripts/compare_controllers.py",
           "docs/controller-cost-contract.md")
METHODS = {"cost": ("adaptive", "cost", True), "legacy": ("adaptive", "legacy", False),
           "fixed": ("fixed", "legacy", False), "sr": ("sr", "legacy", False),
           "cost-only": ("adaptive", "cost", False), "legacy-feedback": ("adaptive", "legacy", True)}
METRICS = ("goodput_mbps", "completion_time_s", "sender_completion_time_s", "retransmissions",
           "parity_overhead_ratio", "total_forward_overhead_ratio", "application_p95_delay_ms")


def conditions():
    base = ChannelConfig(loss=.1)
    return [("clean", replace(base, loss=0)),
            *[(f"random-{p}", replace(base, loss=p / 100)) for p in (2, 5, 10, 20)],
            ("slow-link", replace(base, bandwidth_mbps=1)),
            ("fast-link", replace(base, bandwidth_mbps=20)),
            ("short-delay", replace(base, delay_ms=5)),
            ("long-delay", replace(base, delay_ms=150)),
            ("burst", replace(base, model="gilbert-elliott")),
            ("changing", replace(base, loss=0, phases=((.25, .1), (.75, .02), (1.2, .1)))),
            ("ack-loss", replace(base, ack_loss=.05))]


def fingerprints():
    return {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in SOURCES}


def run(output, split):
    if output.exists():
        raise ValueError("Use a new output directory; previous runs are immutable")
    source = fingerprints()
    seeds = list(range(5)) if split == "development" else list(range(100, 120))
    payload = sample_data(65536)
    digest = hashlib.sha256(payload).hexdigest()
    records, summary = [], []
    for name, channel in conditions():
        for method, (scheme, policy, feedback) in METHODS.items():
            rows = []
            for seed in seeds:
                config = SimulationConfig(scheme=scheme, controller_policy=policy, channel=channel,
                                          seed=seed, max_events=80000, recovery_feedback=feedback)
                result = simulate(payload, config).to_dict()
                valid = (result["completed"] and result["sha256"] == digest
                         and result["application_sha256"] == digest
                         and result["bytes_delivered"] == len(payload))
                if not valid:
                    result["goodput_mbps"] = 0.0
                row = {"condition": name, "method": method, "config": asdict(config),
                       "integrity_verified": valid, **result}
                rows.append(row)
                records.append(row)
            item = {"condition": name, "method": method, "seeds": len(seeds),
                    "failures": sum(not row["integrity_verified"] for row in rows)}
            for metric in METRICS:
                values = [row[metric] for row in rows]
                item[metric + "_mean"] = statistics.mean(values)
                item[metric + "_std"] = statistics.stdev(values)
            summary.append(item)
        means = {row["method"]: row["goodput_mbps_mean"] for row in summary if row["condition"] == name}
        print(f"{name}: " + ", ".join(f"{method}={value:.3f}" for method, value in means.items()), flush=True)
    if source != fingerprints():
        raise RuntimeError("Measured source changed during evaluation")
    comparisons = []
    for name, _ in conditions():
        rows = {row["method"]: row for row in summary if row["condition"] == name}
        comparisons.append({"condition": name, "goodput_ratio_to_legacy": rows["cost"]["goodput_mbps_mean"] / rows["legacy"]["goodput_mbps_mean"],
                            "goodput_ratio_to_fixed": rows["cost"]["goodput_mbps_mean"] / rows["fixed"]["goodput_mbps_mean"]})
    geometric = math.exp(statistics.mean(math.log(row["goodput_ratio_to_legacy"]) for row in comparisons if row["condition"] != "clean"))
    verified = all(row["integrity_verified"] for row in records)
    manifest = {"recorded_at_utc": datetime.now(timezone.utc).isoformat(), "split": split,
                "seeds": seeds, "runs": len(records), "payload_sha256": digest, "size_bytes": len(payload),
                "all_verified": verified, "source_sha256": source, "comparisons": comparisons,
                "geometric_goodput_ratio_to_legacy_nonclean": geometric,
                "adoption_threshold_met": verified and comparisons[0]["goodput_ratio_to_legacy"] >= .98 and geometric >= 1.05,
                "uncertainty": "Sample SD over seeds; no significance test; same seeds are not identical erasure masks."}
    output.mkdir(parents=True)
    raw = json.dumps(records, separators=(",", ":"), allow_nan=False).encode()
    (output / "runs.json.gz").write_bytes(gzip.compress(raw, mtime=0))
    with (output / "summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    (output / "summary.json").write_text(json.dumps({"manifest": manifest, "summary": summary}, indent=2), encoding="utf-8")
    manifest["artifacts_sha256"] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in output.iterdir()}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Nonclean geometric goodput ratio to legacy: {geometric:.4f}; threshold met: {manifest['adoption_threshold_met']}")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("development", "held-out"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.output, args.split)
