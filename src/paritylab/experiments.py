import csv
import hashlib
import json
import platform
import random
import statistics
from dataclasses import asdict
from pathlib import Path

from .channel import ChannelConfig
from .simulation import SCHEMES, SimulationConfig, simulate


def sample_data(size: int) -> bytes:
    return random.Random(12345).randbytes(size)


def run_experiments(output: Path, size: int = 131072, seeds: int = 3, plots: bool = True):
    if size < 1 or seeds < 1:
        raise ValueError("Experiment size and number of seeds must be positive")
    output.mkdir(parents=True, exist_ok=True)
    data = sample_data(size)
    records = []
    for loss_percent in range(0, 21, 2):
        for scheme in SCHEMES:
            for seed in range(seeds):
                config = SimulationConfig(scheme=scheme, seed=seed, channel=ChannelConfig(loss=loss_percent / 100))
                result = simulate(data, config)
                if not result.completed:
                    raise RuntimeError(f"Incomplete sweep transfer: {scheme}, {loss_percent}%, seed {seed}")
                records.append({"scenario": "sweep", "loss_percent": loss_percent, "config": asdict(config), **result.to_dict()})
        print(f"Completed loss={loss_percent}% ({seeds} seeds per scheme)", flush=True)
    for scenario, channel in [
        ("burst", ChannelConfig(loss=0.1, model="gilbert-elliott")),
        ("changing", ChannelConfig(loss=0.0, phases=((0.4, 0.15), (1.2, 0.02), (2.0, 0.10)))),
    ]:
        for scheme in SCHEMES:
            for seed in range(seeds):
                config = SimulationConfig(scheme=scheme, seed=seed, channel=channel)
                result = simulate(data if scenario == "burst" else sample_data(max(size, 524288)), config)
                if not result.completed:
                    raise RuntimeError(f"Incomplete {scenario} transfer: {scheme}, seed {seed}")
                records.append({"scenario": scenario, "loss_percent": 10 if scenario == "burst" else None,
                                "config": asdict(config), **result.to_dict()})
    (output / "runs.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    columns = ["scenario", "loss_percent", "scheme", "seed", "completed", "bytes_delivered", "sha256",
               "goodput_mbps", "completion_time_s", "sender_completion_time_s", "retransmissions",
               "data_transmissions", "parity_packets", "ack_packets", "parity_overhead_ratio", "total_forward_overhead_ratio",
               "mean_delay_ms", "p95_delay_ms", "original_data_losses", "fec_recovered", "fec_recovery_ratio"]
    with (output / "metrics.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    groups = {}
    for row in records:
        groups.setdefault((row["scenario"], row["loss_percent"], row["scheme"]), []).append(row)
    summary = []
    metrics = ["goodput_mbps", "completion_time_s", "retransmissions", "parity_overhead_ratio", "mean_delay_ms", "p95_delay_ms", "fec_recovery_ratio"]
    for (scenario, loss, scheme), rows in groups.items():
        aggregate = {"scenario": scenario, "loss_percent": loss, "scheme": scheme, "seeds": len(rows)}
        for metric in metrics:
            values = [row[metric] for row in rows]
            aggregate[metric + "_mean"] = statistics.mean(values)
            aggregate[metric + "_std"] = statistics.stdev(values) if len(values) > 1 else 0
        summary.append(aggregate)
    with (output / "summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    (output / "manifest.json").write_text(json.dumps({"python": platform.python_version(), "bytes": size,
        "changing_bytes": max(size, 524288), "seeds": list(range(seeds)), "runs": len(records),
        "payload_seed": 12345, "loss_sweep_percent": list(range(0, 21, 2)), "all_completed": True,
        "uncertainty": "sample standard deviation across seeds; not a confidence interval",
        "risk_model": "legacy independent identical erasures for data and parity; separate calibration validates specified Markov conditions",
        "source_sha256": {"src/paritylab/" + p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in sorted(Path(__file__).parent.glob("*.py"))}}, indent=2), encoding="utf-8")
    report = ["# Prototype experiment results", "",
              f"{len(records)} completed transfers across {seeds} seeds. Every completed output was checked byte for byte.", "",
              "The sweep/burst link uses 5 Mbps bandwidth, 50 ms one-way delay, 1024-byte symbols, and a 32-packet window. Values are means +/- sample standard deviations across seeds.", "",
              "| Scenario | Loss % | Scheme | Goodput Mbps | Retransmissions | Parity bytes / file bytes |",
              "| --- | --- | --- | --- | --- | --- |"]
    for row in summary:
        if row["scenario"] == "sweep" and row["loss_percent"] not in {0, 10, 20}:
            continue
        report.append(f"| {row['scenario']} | {row['loss_percent'] if row['loss_percent'] is not None else 'changes'} | {row['scheme']} | "
                      f"{row['goodput_mbps_mean']:.3f} +/- {row['goodput_mbps_std']:.3f} | "
                      f"{row['retransmissions_mean']:.1f} +/- {row['retransmissions_std']:.1f} | "
                      f"{row['parity_overhead_ratio_mean']:.3f} +/- {row['parity_overhead_ratio_std']:.3f} |")
    report += ["", "Adaptive protection does not improve every condition. Its independent-loss risk model is not calibrated for burst loss. Fixed parity can outperform the adaptive risk-target policy because that policy minimizes parity cost subject to modeled block risk rather than directly maximizing goodput.", "",
               "The uncertainty shown is sample standard deviation, not a confidence interval. The same seed set is used for every scheme; different transmission schedules consume different random draws. These measurements do not establish congestion fairness or Internet performance.", "",
               "![Loss sweep](loss-sweep.png)", "", "![Packet recovery delay CDF](delivery-cdf.png)", "", "![Controller timeline](controller-timeline.png)"]
    (output / "results.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    if plots:
        plot_results(output, records, summary)
    return records


def plot_results(output, records, summary):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = {"gbn": "#7d8791", "sr": "#217ca3", "fixed": "#c77929", "adaptive": "#27805c"}
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 140})
    fig, axes = plt.subplots(2, 3, figsize=(14, 8), constrained_layout=True)
    for ax, (metric, label) in zip(axes.flat, [("goodput_mbps", "Goodput (Mbps)"), ("retransmissions", "Retransmitted packets"),
                ("parity_overhead_ratio", "Parity bytes / file bytes"), ("completion_time_s", "Transfer time (s)"),
                ("p95_delay_ms", "95th percentile packet delay (ms)"), ("fec_recovery_ratio", "FEC recovery ratio")], strict=True):
        for scheme in SCHEMES:
            rows = sorted((r for r in summary if r["scenario"] == "sweep" and r["scheme"] == scheme), key=lambda r: r["loss_percent"])
            x = [r["loss_percent"] for r in rows]
            y = [r[metric + "_mean"] for r in rows]
            std = [r[metric + "_std"] for r in rows]
            ax.plot(x, y, marker="o", markersize=3, color=colors[scheme], label=scheme)
            ax.fill_between(x, [max(0, a-b) for a, b in zip(y, std, strict=True)], [a+b for a, b in zip(y, std, strict=True)], color=colors[scheme], alpha=0.1)
        ax.set(xlabel="Independent packet loss (%)", ylabel=label)
        if metric == "fec_recovery_ratio":
            ax.set_ylim(0, 1)
        ax.grid(alpha=0.15)
    axes[0, 0].legend()
    fig.suptitle("Packet parity lab: mean and sample standard deviation across seeds")
    fig.savefig(output / "loss-sweep.png")
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(8, 5), constrained_layout=True)
    for scheme in SCHEMES:
        row = next(r for r in records if r["scenario"] == "sweep" and r["loss_percent"] == 10 and r["scheme"] == scheme and r["seed"] == 0)
        delays = row["packet_delays_ms"]
        ax.step(delays, [(i+1)/len(delays) for i in range(len(delays))], where="post", label=scheme, color=colors[scheme])
    ax.set(xlabel="Packet recovery delay (ms)", ylabel="Cumulative probability", title="10% independent loss: seed 0")
    ax.legend()
    ax.grid(alpha=0.15)
    fig.savefig(output / "delivery-cdf.png")
    plt.close(fig)
    row = next(r for r in records if r["scenario"] == "changing" and r["scheme"] == "adaptive" and r["seed"] == 0)
    trace = row["controller_trace"]
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), constrained_layout=True, sharex=True)
    times = [t["time_s"] for t in trace]
    axes[0].step(times, [t["estimated_loss"] * 100 for t in trace], where="post", label="EWMA from receiver feedback")
    phase_times = [0, 0.4, 1.2, 2.0, max(times[-1], 2.1)]
    axes[0].step(phase_times, [0, 15, 2, 10, 10], where="post", label="Configured channel loss", linestyle="--")
    axes[0].set(ylabel="Loss (%)", title="Adaptive controller under changing independent loss: seed 0")
    axes[0].legend()
    modes = list(dict.fromkeys(t["mode"] for t in trace))
    axes[1].step(times, [modes.index(t["mode"]) for t in trace], where="post", color=colors["adaptive"])
    bad = [t for t in trace if not t["target_met"]]
    axes[1].scatter([t["time_s"] for t in bad], [modes.index(t["mode"]) for t in bad], s=12, c="#bf423e", label="1% model target infeasible")
    axes[1].set(yticks=range(len(modes)), yticklabels=modes, xlabel="Simulation time (s)", ylabel="Selected protection")
    axes[1].legend()
    fig.savefig(output / "controller-timeline.png")
    plt.close(fig)

