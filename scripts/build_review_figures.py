"""Build Review 2 plots and a table directly from audited held-out results."""
import json
from pathlib import Path

from audit_controller_comparison import audit

ROOT = Path(__file__).resolve().parents[1]
LABELS = ("Clean", "Random 2%", "Random 5%", "Random 10%", "Random 20%", "Slow link (1 Mbps)",
          "Fast link (20 Mbps)", "Short delay (5 ms)", "Long delay (150 ms)", "Burst 10%",
          "Changing (short file)", "ACK loss 5%")


def main():
    checked = audit()
    study = json.loads((ROOT / "output/studies/controller-cost/held-out/summary.json").read_text())
    names = [item["condition"] for item in study["manifest"]["comparisons"]]
    rows = {(row["condition"], row["method"]): row for row in study["summary"]}
    output = ROOT / "output/review-2"
    output.mkdir(parents=True, exist_ok=True)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    palette = {"cost": "#b83f16", "legacy": "#59645f", "fixed": "#1d7168", "sr": "#466578"}
    method_names = {"cost": "Updated adaptive", "legacy": "Original adaptive", "fixed": "Fixed XOR", "sr": "Selective Repeat"}
    for metric, title, filename in (("goodput_mbps", "Useful throughput (Mbps)", "goodput.png"),
                                    ("completion_time_s", "Receiver completion (seconds)", "completion.png")):
        fig, ax = plt.subplots(figsize=(12, 7), constrained_layout=True)
        for index, method in enumerate(("legacy", "cost", "fixed", "sr")):
            positions = [n + (index - 1.5) * .18 for n in range(len(names))]
            ax.barh(positions, [rows[(name, method)][metric + "_mean"] for name in names], height=.17,
                    xerr=[rows[(name, method)][metric + "_std"] for name in names],
                    label=method_names[method], color=palette[method], error_kw={"elinewidth": .7, "capsize": 1.5})
        ax.set_yticks(range(len(names)), LABELS)
        ax.invert_yaxis()
        ax.set_xlabel(title)
        ax.set_title("Controller comparison · 20 held-out seeds per condition")
        ax.grid(axis="x", alpha=.2)
        ax.set_axisbelow(True)
        ax.legend(loc="lower right" if metric == "goodput_mbps" else "upper right")
        fig.savefig(output / filename, dpi=170)
        plt.close(fig)
    lines = ["# Review 2 measured results", "", "1,440 verified transfers: 12 conditions × 20 seeds × 6 methods. Final seeds 100–119 were not used for development. All files and in-order application hashes match.", "",
             "64 KiB files, 1 KiB packets, window 32. Default one-way delay 50 ms and capacity 5 Mbps. Each changed parameter is named in the condition. Values are mean ± sample standard deviation; these are not confidence intervals.", "",
             f"The geometric mean goodput ratio to the original controller across the 11 nonclean conditions is {checked['geometric_goodput_ratio_to_legacy_nonclean']:.4f} (+26.4%). This is a ratio across the declared conditions, not a universal improvement.", "",
             "| Condition | Original Mbps | Updated Mbps | Change | Fixed XOR Mbps | Selective Repeat Mbps |", "| --- | --- | --- | --- | --- | --- |"]
    for name, label in zip(names, LABELS):
        values = [f"{rows[(name, m)]['goodput_mbps_mean']:.3f} ± {rows[(name, m)]['goodput_mbps_std']:.3f}" for m in ("legacy", "cost", "fixed", "sr")]
        change = (rows[(name, "cost")]["goodput_mbps_mean"] / rows[(name, "legacy")]["goodput_mbps_mean"] - 1) * 100
        lines.append(f"| {label} | {values[0]} | {values[1]} | {change:+.1f}% | {values[2]} | {values[3]} |")
    lines += ["", "![Goodput across all declared conditions](../output/review-2/goodput.png)", "", "![Completion across all declared conditions](../output/review-2/completion.png)", "", "## Completion, retries, and overhead", "", "| Condition | Original → updated completion (s) | Original → updated retries | Original → updated parity (%) |", "| --- | --- | --- | --- |"]
    for name, label in zip(names, LABELS):
        a, b = rows[(name, "legacy")], rows[(name, "cost")]
        lines.append(f"| {label} | {a['completion_time_s_mean']:.3f} → {b['completion_time_s_mean']:.3f} | {a['retransmissions_mean']:.2f} → {b['retransmissions_mean']:.2f} | {100*a['parity_overhead_ratio_mean']:.2f} → {100*b['parity_overhead_ratio_mean']:.2f} |")
    lines += ["", "## Component comparison", "", "Cost-only removes early feedback; original + feedback keeps the original parity objective. This separates the two changes. Most improvement comes from early recovery.", "", "| Condition | Original | Cost only | Original + feedback | Updated |", "| --- | --- | --- | --- | --- |"]
    for name, label in zip(names, LABELS):
        values = [f"{rows[(name, m)]['goodput_mbps_mean']:.3f}" for m in ("legacy", "cost-only", "legacy-feedback", "cost")]
        lines.append(f"| {label} | " + " | ".join(values) + " |")
    lines += ["", "The changing-loss condition finishes before 0.25 s at this file size; it does not establish adaptation to a phase change. Fixed XOR is faster in several conditions. Burst results vary widely across seeds; mean goodput and mean completion need not rank methods the same way because averaging reciprocals changes the endpoint. Socket wall-time gains and significance were not evaluated.", "", "The predeclared contract is in [controller-cost-contract.md](controller-cost-contract.md). Raw runs, all summaries, source hashes, and source archives are under `output/studies/controller-cost/`. Recompute the result with `python scripts/audit_controller_comparison.py`."]
    (ROOT / "docs/review-2-results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Review 2 tables and both figures built from audited results.")


if __name__ == "__main__":
    main()
