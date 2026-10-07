"""Recompute the final controller comparison from its immutable raw runs."""
import csv
import gzip
import hashlib
import json
import math
import statistics
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def audit(root=ROOT):
    directory = root / "output/studies/controller-cost/held-out"
    manifest = json.loads((directory / "manifest.json").read_text())
    for name, expected in manifest["artifacts_sha256"].items():
        if Path(name).name != name or hashlib.sha256((directory / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Controller comparison artifact changed")
    current = all((root / name).is_file() and hashlib.sha256((root / name).read_bytes()).hexdigest() == expected
                  for name, expected in manifest["source_sha256"].items())
    if not current:
        with zipfile.ZipFile(directory / "source.zip") as archive:
            if not all(hashlib.sha256(archive.read(name)).hexdigest() == expected
                       for name, expected in manifest["source_sha256"].items()):
                raise ValueError("Controller comparison source archive mismatch")
    records = json.loads(gzip.decompress((directory / "runs.json.gz").read_bytes()))
    from paritylab.experiments import sample_data
    if manifest["payload_sha256"] != hashlib.sha256(sample_data(65536)).hexdigest():
        raise ValueError("Controller comparison payload changed")
    for name, original in (("controller-study.json", "summary.json"), ("controller-study.csv", "summary.csv")):
        asset = root / "web/assets" / name
        if asset.is_file() and asset.read_bytes() != (directory / original).read_bytes():
            raise ValueError("Demo evaluation differs from the measured study")
    methods = {"cost": ("cost", True), "legacy": ("legacy", False), "fixed": ("legacy", False),
               "sr": ("legacy", False), "cost-only": ("cost", False), "legacy-feedback": ("legacy", True)}
    seeds = list(range(100, 120))
    if manifest["seeds"] != seeds or manifest["runs"] != 1440 or len(records) != 1440:
        raise ValueError("Controller comparison seed or trial count changed")
    groups, identities = {}, set()
    for row in records:
        identity = (row["condition"], row["method"], row["seed"])
        if identity in identities or row["seed"] not in seeds or row["method"] not in methods:
            raise ValueError("Duplicate or undeclared controller trial")
        identities.add(identity)
        config = row["config"]
        if (config["controller_policy"], config["recovery_feedback"]) != methods[row["method"]] or config["seed"] != row["seed"]:
            raise ValueError("Controller trial method or seed mismatch")
        if not (row["completed"] and row["integrity_verified"] and row["bytes_delivered"] == 65536
                and row["application_bytes_delivered"] == 65536
                and row["sha256"] == row["application_sha256"] == manifest["payload_sha256"]):
            raise ValueError("Controller comparison byte integrity failed")
        if not math.isclose(row["goodput_mbps"], 65536 * 8 / row["completion_time_s"] / 1e6, rel_tol=1e-12):
            raise ValueError("Controller comparison goodput mismatch")
        groups.setdefault(identity[:2], []).append(row)
    with (directory / "summary.csv").open(newline="") as stream:
        summaries = list(csv.DictReader(stream))
    metrics = ("goodput_mbps", "completion_time_s", "sender_completion_time_s", "retransmissions",
               "parity_overhead_ratio", "total_forward_overhead_ratio", "application_p95_delay_ms")
    if len(groups) != 72 or len(summaries) != 72:
        raise ValueError("Controller comparison condition count changed")
    means = {}
    for summary in summaries:
        rows = groups[(summary["condition"], summary["method"])]
        if len(rows) != 20 or int(summary["failures"]) != 0:
            raise ValueError("Controller comparison group is incomplete")
        # Every method receives the identical declared channel/window/timer.
        controls = {json.dumps({key: row["config"][key] for key in
                    ("channel", "packet_size", "window", "timeout_ms")}, sort_keys=True) for row in rows}
        if len(controls) != 1:
            raise ValueError("Controller comparison controls differ inside a condition")
        means[(summary["condition"], summary["method"])] = statistics.mean(row["goodput_mbps"] for row in rows)
        for metric in metrics:
            for suffix, expected in (("mean", statistics.mean(row[metric] for row in rows)),
                                     ("std", statistics.stdev(row[metric] for row in rows))):
                if not math.isclose(float(summary[metric + "_" + suffix]), expected, abs_tol=1e-12, rel_tol=1e-12):
                    raise ValueError("Controller comparison summary mismatch")
    for condition in {key[0] for key in groups}:
        configs = [groups[(condition, method)][0]["config"] for method in methods]
        controls = {json.dumps({key: config[key] for key in ("channel", "packet_size", "window", "timeout_ms")}, sort_keys=True) for config in configs}
        if len(controls) != 1:
            raise ValueError("Controller comparison controls differ across methods")
    ratios = []
    for comparison in manifest["comparisons"]:
        name = comparison["condition"]
        ratio = means[(name, "cost")] / means[(name, "legacy")]
        if not math.isclose(ratio, comparison["goodput_ratio_to_legacy"], rel_tol=1e-12):
            raise ValueError("Controller improvement ratio mismatch")
        if name != "clean":
            ratios.append(ratio)
    geometric = math.exp(statistics.mean(math.log(ratio) for ratio in ratios))
    if not math.isclose(geometric, manifest["geometric_goodput_ratio_to_legacy_nonclean"], rel_tol=1e-12):
        raise ValueError("Controller comparison aggregate mismatch")
    if not manifest["all_verified"]:
        raise ValueError("Controller comparison verification flag is false")
    passed = means[("clean", "cost")] / means[("clean", "legacy")] >= .98 and geometric >= 1.05
    if manifest["adoption_threshold_met"] != passed:
        raise ValueError("Controller adoption flag disagrees with measured result")
    return {"records_checked": len(records), "all_verified": True, "source_current": current,
            "source_verified": True, "geometric_goodput_ratio_to_legacy_nonclean": geometric}


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2))
