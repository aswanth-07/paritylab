"""Reanalyse saved evidence and build a self-contained research manuscript.

No experiment is rerun here. Every displayed statistic comes from the archived
records. The LaTeX file embeds vector plots and its bibliography so it also opens
in a standalone editor without a companion TeX project.
"""
import argparse
import csv
import gzip
import hashlib
import json
import math
import platform
import re
import statistics as stats
import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "paper"
NAMES = {"gbn": "GBN", "sr": "SR", "fixed": "Fixed XOR", "adaptive": "Adaptive"}
COLORS = ["#444444", "#0072B2", "#D55E00", "#009E73"]


def read_json(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8-sig"))


def read_csv(path):
    with (ROOT / path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def mean_sd(values, places=3):
    return f"{stats.mean(values):.{places}f} +/- {stats.stdev(values):.{places}f}"


def md_table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
                     + ["| " + " | ".join(map(str, row)) + " |" for row in rows])


def analyse():
    # The repository's independent audit reconstructs raw counts and fingerprints.
    from audit_measurements import audit
    audit()
    baseline = read_json("output/experiments/runs.json")
    sensitivity = read_json("output/studies/sensitivity/runs.json")
    socket = read_json("output/socket-evaluation/runs.json")
    calibration = read_csv("output/calibration/summary.csv")
    policy = read_csv("output/calibration/policy-validation.csv")
    congestion = read_json("output/congestion/summary.json")
    groups = defaultdict(list)
    for row in baseline:
        groups[(row["scenario"], row["loss_percent"], row["scheme"])].append(row)
    codec_groups = defaultdict(list)
    with gzip.open(ROOT / "output/studies/equal-overhead/trials.csv.gz", "rt", encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            codec_groups[(row["model"], float(row["loss"]), float(row["parity_ratio"]), row["code"], int(row["seed"]))].append(row)
    assert len(baseline) == 260 and len(sensitivity) == 370 and len(socket) == 36
    assert len(calibration) == 153 and len(policy) == 225
    assert sum(len(rows) for rows in codec_groups.values()) == 160000
    pairs = {}
    for (model, loss, budget, code, seed), rows in codec_groups.items():
        key = (model, loss, budget, seed)
        pairs.setdefault(key, {})[code] = rows
    for codecs in pairs.values():
        a, b = codecs.values()
        assert len(a) == len(b) == 1000
        assert all(x["erase_mask"] == y["erase_mask"] and x["block"] == y["block"] for x, y in zip(a, b, strict=True))
    assert all(r["completed"] and r["sha256"] == r["application_sha256"] for r in baseline + sensitivity)
    tables = {}
    selected = []
    for scenario, loss, label in [("sweep", 0, "IID 0%"), ("sweep", 10, "IID 10%"), ("sweep", 20, "IID 20%"), ("burst", 10, "Markov 10%"), ("changing", None, "Changing")]:
        for scheme in NAMES:
            rows = groups[scenario, loss, scheme]
            selected.append([label, NAMES[scheme], mean_sd([r["goodput_mbps"] for r in rows]),
                             mean_sd([r["retransmissions"] for r in rows], 1),
                             mean_sd([r["parity_overhead_ratio"] for r in rows])])
    tables["BASELINE"] = md_table(["Condition", "Scheme", "Goodput (Mbps)", "Data retries", "Parity/file"], selected)
    counts = {"baseline_transfers": len(baseline), "sensitivity_transfers": len(sensitivity),
              "socket_transfers": len(socket), "congestion_runs": 70, "congestion_flows": 140,
              "calibration_blocks": sum(int(r["trials"]) for r in calibration),
              "policy_blocks": sum(int(r["trials"]) for r in policy),
              "codec_evaluations": 160000, "paired_codec_masks": sum(len(next(iter(v.values()))) for v in pairs.values())}
    training_groups = defaultdict(list)
    for row in policy:
        training_groups[(row["model"], row["loss"], row["history"], row["seed"])].append(row)
    assert len(training_groups) == 75
    assert all(len(rows) == 3 and len({r["training_erasure_hex"] for r in rows}) == 1 for rows in training_groups.values())
    counts["policy_training_histories"] = len(training_groups)
    tables["STUDIES"] = md_table(["Study", "Observation unit", "Count", "Replication"], [
        ["Single-flow", "File transfer", counts["baseline_transfers"], "5 seeds/condition/scheme"],
        ["Sensitivity", "File transfer", counts["sensitivity_transfers"], "5 seeds/condition/scheme"],
        ["Equal budget", "Shared mask", counts["paired_codec_masks"], "5 seeds; 1000 masks/group/seed"],
        ["Decoder calibration", "Independent block draw", counts["calibration_blocks"], "153 cases; 5 x 4000 blocks/case"],
        ["Estimated policy", "Policy decision", len(policy), "75 shared histories; 3 policies"],
        ["Policy decoding", "Fresh test block", counts["policy_blocks"], "1000 draws/training realization"],
        ["Shared FIFO", "Two-flow run", counts["congestion_runs"], "5 seeds/configuration/queue"],
        ["Loopback", "Three-process transfer", counts["socket_transfers"], "3 seeds/scenario/scheme"]])
    exact_error = max(float(r["absolute_error"]) for r in calibration)
    max_wrong_stationary = max(float(r["iid_absolute_error"]) for r in calibration if r["model"] == "binary_markov" and not r["previous_loss"])
    max_wrong = max(float(r["iid_absolute_error"]) for r in calibration if r["model"] == "binary_markov")
    assert all(r["within_simultaneous_bound99"] == "True" for r in calibration)
    ci_misses = sum(r["point_in_ci95"] != "True" for r in calibration)
    calibration_rows = []
    for model, previous, label in [("independent", "", "IID"), ("binary_markov", "", "Stationary"),
                                    ("binary_markov", "False", "After receive"), ("binary_markov", "True", "After loss")]:
        for protection, size in [("xor-8", 8), ("grid-3x3", 9), ("grid-3x3", 5)]:
            row = next(r for r in calibration if r["model"] == model and float(r["loss"]) == .1
                       and r["previous_loss"] == previous and r["protection"] == protection and int(r["data_symbols"]) == size
                       and (model == "independent" or float(r["bad_to_good"]) == .2))
            calibration_rows.append([label, protection, size, f"{float(row['prediction']):.4f}",
                                     f"{float(row['empirical_failure']):.4f}",
                                     f"[{float(row['ci95_low']):.4f}, {float(row['ci95_high']):.4f}]"])
    tables["CALIBRATION"] = md_table(["Start/model", "Code", "Data", "Exact risk", "Failure rate", "95% Wilson interval"], calibration_rows)
    policy_counts = []
    for model in ("independent", "binary_markov", "fixed_runs"):
        for name in ("legacy", "uncertainty", "burst"):
            rows = [r for r in policy if r["model"] == model and r["policy"] == name]
            under = sum(r["upper_below_true_model_failure"] == "True" for r in rows) if model != "fixed_runs" else "N/A"
            violation = sum(r["target_met"] == "True" and float(r["ci95_low"]) > .01 for r in rows)
            feasible = sum(r["target_met"] == "True" for r in rows)
            policy_counts.append({"model": model, "policy": name, "cases": len(rows), "under": under, "feasible": feasible, "violations": violation})
    tables["POLICY"] = md_table(["Training/test model", "Policy", "Cases", "Feasible choices", "Risk underestimates", "Target failures"],
                                 [[r[k] for k in ("model", "policy", "cases", "feasible", "under", "violations")] for r in policy_counts])
    codec_rows, contrasts = [], []
    for model in ("bernoulli", "gilbert-elliott"):
        for loss in (.01, .05, .1, .2):
            values = {}
            for code in ("grid-2x2", "per-packet-replication"):
                rows = [r for seed in range(5) for r in codec_groups[model, loss, 1., code, seed]]
                values[code] = sum(int(r["failed"]) for r in rows)
            diffs = [100 * (sum(int(r["failed"]) for r in codec_groups[model, loss, 1., "grid-2x2", seed])
                            - sum(int(r["failed"]) for r in codec_groups[model, loss, 1., "per-packet-replication", seed])) / 1000 for seed in range(5)]
            contrasts.append({"model": model, "loss": loss, "differences_pp": diffs, "mean_pp": stats.mean(diffs), "sd_pp": stats.stdev(diffs)})
            codec_rows.append(["IID" if model == "bernoulli" else "Markov", f"{100*loss:g}%", f"{values['grid-2x2']}/5000",
                               f"{values['per-packet-replication']}/5000", mean_sd(diffs, 2)])
    tables["CODECS"] = md_table(["Model", "Loss", "Grid failures", "Replication failures", "Grid - replication (pp)"], codec_rows)
    tables["CONGESTION"] = md_table(["Two-flow configuration", "Queue", "Goodput (Mbps)", "Jain index", "Queue drops"],
                                    [[r["condition"].replace("_", " "), r["queue_packets"],
                                      f"{r['aggregate_goodput_mean']:.3f} +/- {r['aggregate_goodput_std']:.3f}",
                                      f"{r['jain_mean']:.3f} +/- {r['jain_std']:.3f}", f"{r['queue_drops_mean']:.1f}"] for r in congestion])
    socket_rows = []
    for scenario in ("independent", "burst", "metadata_reorder"):
        for scheme in NAMES:
            rows = [r for r in socket if r["scenario"] == scenario and r["config"]["scheme"] == scheme]
            assert all(r["verified"] and r["bytes_delivered"] == 32768 for r in rows)
            socket_rows.append([scenario.replace("_", " "), NAMES[scheme], f"{len(rows)}/{len(rows)}",
                                mean_sd([r["sender"]["retransmissions"] for r in rows], 1),
                                mean_sd([r["sender"]["parity_packets"] for r in rows], 1)])
    tables["SOCKET"] = md_table(["Scenario", "Scheme", "Byte-verified", "Retries", "Repair packets"], socket_rows)
    sens = read_csv("output/studies/sensitivity/summary.csv")
    tables["SENSITIVITY"] = md_table(["Factor", "Value", "Scheme", "Goodput (Mbps)", "Data retries"],
                                    [[r["axis"].replace("_", " "), r["value"], NAMES[r["scheme"]],
                                      f"{float(r['goodput_mbps_mean']):.3f} +/- {float(r['goodput_mbps_std']):.3f}",
                                      f"{float(r['retransmissions_mean']):.1f} +/- {float(r['retransmissions_std']):.1f}"] for r in sens])
    equal_summary = read_csv("output/studies/equal-overhead/summary.csv")
    tables["BUDGET50"] = md_table(["Model", "Loss", "Pairwise XOR", "Repeated block XOR"],
                                  [["IID" if model == "bernoulli" else "Markov", f"{100*loss:g}%"] +
                                   [f"{next(r['failed'] for r in equal_summary if r['model']==model and float(r['loss'])==loss and r['code']==code)}/5000"
                                    for code in ("pairwise-xor", "repeated-block-xor")]
                                   for model in ("bernoulli", "gilbert-elliott") for loss in (.01, .05, .1, .2)])
    active = [r for r in policy if r["model"] == "binary_markov" and r["policy"] == "burst" and r["risk_model"] == "binary Markov parameter envelope"]
    metrics = {**counts, "calibration_max_error": exact_error, "calibration_wilson_misses": ci_misses,
               "simultaneous_bound99": float(calibration[0]["simultaneous_error_bound99"]),
               "wrong_iid_stationary_max_error": max_wrong_stationary, "wrong_iid_all_starts_max_error": max_wrong,
               "policy_counts": policy_counts, "paired_contrasts": contrasts,
               "active_markov_cases": len(active), "active_rectangles_miss": sum(r["transition_rectangle_contains_truth"] == "False" for r in active),
               "contained_rectangle_underestimates": sum(r["transition_rectangle_contains_truth"] == "True" and r["upper_below_true_model_failure"] == "True" for r in active)}
    specs = {}
    series = []
    for i, scheme in enumerate(NAMES):
        rows = [groups["sweep", loss, scheme] for loss in range(0, 21, 2)]
        series.append({"label": NAMES[scheme], "x": list(range(0, 21, 2)),
                       "y": [stats.mean(r["goodput_mbps"] for r in group) for group in rows],
                       "error": [stats.stdev(r["goodput_mbps"] for r in group) for group in rows], "color": COLORS[i]})
    specs["loss-sweep"] = {"xlabel": "Independent erasure probability (%)", "ylabel": "Useful goodput (Mbps)", "xlim": [0,20], "ylim": [0,3.1], "series": series}
    specs["calibration"] = {"xlabel": "Exact block-failure probability", "ylabel": "Measured block-failure rate", "xlim": [0,1], "ylim": [0,1],
                            "reference": True, "series": [{"label": label, "x": [float(r["prediction"]) for r in calibration if r["model"] == model],
                            "y": [float(r["empirical_failure"]) for r in calibration if r["model"] == model], "connect": False, "color": COLORS[i+1]}
                            for i,(model,label) in enumerate([("independent","IID (63 cases)"),("binary_markov","Markov (90 cases)")])]}
    specs["risk-mismatch"] = {"xlabel": "Starting condition (10% stationary loss)", "ylabel": "Block-failure probability", "xlim": [-.25,2.25], "ylim": [0,1],
                              "xticks": [[0,"Stationary"],[1,"After receive"],[2,"After loss"]], "series": []}
    for i, (code, size) in enumerate([("xor-8",8),("grid-3x3",9)]):
        chosen = [next(r for r in calibration if r["model"] == "binary_markov" and float(r["loss"]) == .1 and float(r["bad_to_good"]) == .2
                      and r["previous_loss"] == previous and r["protection"] == code and int(r["data_symbols"]) == size) for previous in ("","False","True")]
        specs["risk-mismatch"]["series"].append({"label": code+" exact Markov", "x": [0,1,2], "y": [float(r["prediction"]) for r in chosen], "color": COLORS[i+1]})
        specs["risk-mismatch"]["series"].append({"label": code+" IID approximation", "x": [0,1,2], "y": [float(r["iid_prediction"]) for r in chosen], "color": COLORS[i+1], "dashed": True})
    specs["paired-codecs"] = {"xlabel": "Configured erasure probability (%)", "ylabel": "Grid minus replication (percentage points)", "xlim": [0,21], "ylim": [-15,4],
                              "zero": True, "series": [{"label": label, "x": [100*r["loss"] for r in contrasts if r["model"] == model],
                               "y": [r["mean_pp"] for r in contrasts if r["model"] == model], "error": [r["sd_pp"] for r in contrasts if r["model"] == model],
                               "color": COLORS[i+1]} for i,(model,label) in enumerate([("bernoulli","IID"),("gilbert-elliott","Continuous Markov")])]}
    specs["congestion"] = {"xlabel": "FIFO capacity including packet in service", "ylabel": "Aggregate useful goodput (Mbps)", "xlim": [0,40], "ylim": [0,2.1],
                           "xticks": [[8,"8 packets"],[32,"32 packets"]], "series": []}
    for i, (condition,label) in enumerate([("sr_vs_sr","SR / SR"),("fixed_vs_sr","Fixed XOR / SR"),("adaptive_vs_sr","Adaptive / SR"),("uncontrolled_equal","Uncontrolled SR / SR")]):
        rows = [r for r in congestion if r["condition"] == condition]
        specs["congestion"]["series"].append({"label": label, "x": [r["queue_packets"] for r in rows], "y": [r["aggregate_goodput_mean"] for r in rows],
                                              "error": [r["aggregate_goodput_std"] for r in rows], "color": COLORS[i]})
    return tables, metrics, specs


def plot(spec, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["svg.hashsalt"] = "paritylab-paper"
    fig, ax = plt.subplots(figsize=(7.0, 3.65), constrained_layout=True)
    for i, series in enumerate(spec["series"]):
        ax.errorbar(series["x"], series["y"], yerr=series.get("error"), color=series["color"],
                    marker=["o","s","^","D"][i % 4], markersize=4, capsize=3,
                    linestyle="none" if not series.get("connect",True) else "--" if series.get("dashed") else "-",
                    linewidth=1.1, label=series["label"])
    if spec.get("reference"):
        ax.plot([0,1],[0,1],color="#777777",linestyle=":",linewidth=1)
    if spec.get("zero"):
        ax.axhline(0,color="#777777",linewidth=1)
    ax.set(xlabel=spec["xlabel"], ylabel=spec["ylabel"], xlim=spec["xlim"], ylim=spec["ylim"])
    if "xticks" in spec:
        ax.set_xticks([x for x,_ in spec["xticks"]], [label for _,label in spec["xticks"]])
    ax.spines[["top","right"]].set_visible(False)
    ax.grid(axis="y",alpha=.18)
    ax.legend(fontsize=8,loc="best",frameon=False)
    fig.savefig(path.with_suffix(".png"),dpi=240,metadata={"Software":"ParityLab paper analysis"})
    fig.savefig(path.with_suffix(".svg"),metadata={"Date":None})
    plt.close(fig)


def escape(text):
    replacements = {"\\":r"\textbackslash{}", "&":r"\&", "%":r"\%", "$":r"\$", "#":r"\#", "_":r"\_",
                    "{":r"\{", "}":r"\}", "~":r"\textasciitilde{}", "^":r"\textasciicircum{}"}
    return "".join(replacements.get(c,c) for c in text).replace("+/-",r"$\pm$").replace("±",r"$\pm$")


def inline(text):
    pattern = r"(`[^`]+`|\$[^$]+\$|\\cite\{[^}]+\}|\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\([^\)]+\))"
    result = []
    for part in re.split(pattern,text):
        if part.startswith("`"):
            code=escape(part[1:-1]).replace("/",r"/\allowbreak{}").replace("-",r"-\allowbreak{}").replace(r"\_",r"\_\allowbreak{}")
            result.append(r"\texttt{"+code+"}")
        elif part.startswith("$") or part.startswith(r"\cite{"): result.append(part)
        elif part.startswith("**"): result.append(r"\textbf{"+escape(part[2:-2])+"}")
        elif part.startswith("*"): result.append(r"\emph{"+escape(part[1:-1])+"}")
        elif part.startswith("["):
            match=re.fullmatch(r"\[([^\]]+)\]\(([^)]+)\)",part)
            result.append(r"\href{"+match[2]+"}{"+escape(match[1])+"}" if match else escape(part))
        else: result.append(escape(part))
    return "".join(result)


def tex_plot(spec):
    # Plain LaTeX picture primitives keep plots embedded in the standalone file.
    x0,y0,w,h=24,20,130,53
    xmin,xmax=spec["xlim"];ymin,ymax=spec["ylim"]
    tx=lambda x:x0+(x-xmin)/(xmax-xmin)*w
    ty=lambda y:y0+(y-ymin)/(ymax-ymin)*h
    lines=[r"\setlength{\unitlength}{1mm}",r"\begin{picture}(164,100)",r"\linethickness{0.15mm}"]
    def line(x1,y1,x2,y2):
        if math.hypot(x2-x1,y2-y1)<0.01:
            return
        lines.append(r"\qbezier("+f"{x1:.2f},{y1:.2f})({(x1+x2)/2:.2f},{(y1+y2)/2:.2f})({x2:.2f},{y2:.2f})")
    def label(x,y,txt,align="c"):
        lines.append(r"\put("+f"{x:.2f},{y:.2f}"+r"){\makebox(0,0)["+align+r"]{\scriptsize "+inline(txt)+"}}")
    for i in range(5):
        y=ymin+(ymax-ymin)*i/4
        lines.append(r"\color[HTML]{DDDDDD}");line(x0,ty(y),x0+w,ty(y))
        lines.append(r"\color{black}");label(x0-3,ty(y),f"{y:.2g}","r")
    ticks=spec.get("xticks",[[xmin+(xmax-xmin)*i/4,f"{xmin+(xmax-xmin)*i/4:.2g}"] for i in range(5)])
    for x,labeltext in ticks:
        line(tx(x),y0,tx(x),y0-1);label(tx(x),y0-4,labeltext)
    line(x0,y0,x0+w,y0);line(x0,y0,x0,y0+h)
    label(x0+w/2,8,spec["xlabel"])
    lines.append(r"\put(5,46){\rotatebox{90}{\makebox(0,0){\scriptsize "+escape(spec["ylabel"])+"}}}")
    if spec.get("reference"):line(tx(0),ty(0),tx(1),ty(1))
    if spec.get("zero"):line(tx(xmin),ty(0),tx(xmax),ty(0))
    for i,series in enumerate(spec["series"]):
        lines.append(r"\color[HTML]{"+series["color"][1:]+"}")
        points=list(zip(series["x"],series["y"],strict=True))
        if series.get("connect",True):
            for (xa,ya),(xb,yb) in zip(points,points[1:]):
                if series.get("dashed"):
                    for j in range(0,20,2):
                        f,g=j/20,(j+1)/20
                        line(tx(xa+(xb-xa)*f),ty(ya+(yb-ya)*f),tx(xa+(xb-xa)*g),ty(ya+(yb-ya)*g))
                else:line(tx(xa),ty(ya),tx(xb),ty(yb))
        for j,(x,y) in enumerate(points):
            px,py=tx(x),ty(y)
            if "error" in series:
                e=series["error"][j];lo,hi=ty(max(ymin,y-e)),ty(min(ymax,y+e))
                line(px,lo,px,hi);line(px-1,lo,px+1,lo);line(px-1,hi,px+1,hi)
            mark=[r"\circle*{1.2}",r"\circle{1.5}",r"\makebox(0,0){\tiny $\triangle$}",r"\makebox(0,0){\tiny $\square$}"][i%4]
            lines.append(r"\put("+f"{px:.2f},{py:.2f}"+"){"+mark+"}")
        lx,ly=25+70*(i%2),94-6*(i//2)
        if series.get("dashed"):
            line(lx,ly,lx+2,ly);line(lx+3,ly,lx+5,ly)
        else:line(lx,ly,lx+5,ly)
        label(lx+7,ly,series["label"],"l")
    lines += [r"\color{black}",r"\end{picture}"]
    return "\n".join(lines)


def to_tex(markdown,specs,references):
    output=[r"\documentclass[11pt,a4paper]{article}",r"\usepackage[margin=23mm]{geometry}",
            r"\usepackage[T1]{fontenc}",r"\usepackage{lmodern,amsmath,amssymb,booktabs,array,graphicx,xcolor,hyperref}",
            r"\hypersetup{colorlinks=true,urlcolor=blue,citecolor=blue,linkcolor=black,pdftitle={Decoder risk and finite-transfer tradeoffs in adaptive packet parity},pdfauthor={A Aswanth Raj; Ranjithkumar S}}",
            r"\setlength{\parindent}{0pt}\setlength{\parskip}{5pt}\setlength{\tabcolsep}{3pt}\renewcommand{\arraystretch}{1.17}",
            r"\emergencystretch=2em",
            r"\renewcommand{\topfraction}{0.85}\renewcommand{\textfraction}{0.08}\renewcommand{\floatpagefraction}{0.8}",
            r"\title{Decoder risk and finite-transfer tradeoffs in adaptive packet parity}",
            r"\author{A Aswanth Raj \and Dr. Ranjithkumar S}",
            r"\date{School of Computer Science and Engineering\\VIT Vellore\\October 2026}",r"\begin{document}\maketitle"]
    blocks=markdown.split("\n\n")
    skip_title=True
    table_group=False
    for block in blocks:
        block=block.strip()
        if not block:continue
        if block.startswith("# ") and skip_title:skip_title=False;continue
        if block.startswith("Authors:") or block.startswith("Affiliation:") or block.startswith("Manuscript status:"):continue
        if block.startswith("<!--"):continue
        if block.startswith("\\["):output.append(block);continue
        if block.startswith("```"):output.append("\\begin{verbatim}\n"+"\n".join(block.splitlines()[1:-1])+"\n\\end{verbatim}");continue
        if block=="## References":
            output.append(r"\begin{thebibliography}{99}\footnotesize\setlength{\itemsep}{2pt}\setlength{\parskip}{0pt}")
            for ref in references:output.append(r"\bibitem{"+ref["key"]+"} "+escape(ref["text"])+r" \url{"+ref["url"]+"}")
            output.append(r"\end{thebibliography}");continue
        if block.startswith("## "):
            title=block[3:]
            if title.startswith("Appendix A"):output.append(r"\clearpage\appendix")
            title=re.sub(r"^(?:Appendix [A-Z]|[0-9]+)\.\s*","",title)
            output.append(r"\section*{"+escape(title)+"}" if title in {"Abstract","Declarations"} else r"\section{"+escape(title)+"}");continue
        if block.startswith("### "):
            title=re.sub(r"^(?:\d+|[A-Z])\.\d+\s*","",block[4:]);output.append(r"\subsection{"+escape(title)+"}");continue
        if block.startswith("!["):
            match=re.fullmatch(r"!\[([^\]]+)\]\(figures/([^)]+)\.png\)",block)
            if not match:raise ValueError("Unknown figure: "+block[:100])
            output += [r"\begin{figure}[htbp]\centering",tex_plot(specs[match[2]]),r"\caption{"+inline(match[1])+"}",r"\end{figure}"];continue
        if block.startswith("| "):
            rows=[s.strip()[1:-1].split("|") for s in block.splitlines()]
            n=len(rows[0])
            # Allow the first column more space when the last columns are numbers.
            widths=([31,22,36,30,33] if n==5 else [29,23,12,23,25,39] if n==6 else [45,43,18,46] if n==4 else [156/n]*n)
            cols="".join(r">{\raggedright\arraybackslash}p{"+f"{v:.1f}"+"mm}" for v in widths)
            # Bounded tabular pages avoid longtable output-routine differences
            # between TeX installations. Repeat headers on appendix pages.
            data=rows[2:]
            chunk=37 if len(data)>37 else len(data)
            for start in range(0,len(data),chunk):
                if start: output.append(r"\clearpage\noindent\textit{Table continued.}")
                output += [r"\begin{center}\footnotesize\setlength{\parskip}{0pt}",r"\begin{tabular}{"+cols+"}",r"\toprule",
                           " & ".join(r"\textbf{"+inline(c.strip())+"}" for c in rows[0])+r"\\\midrule"]
                for row in data[start:start+chunk]:output.append(" & ".join(inline(c.strip()) for c in row)+r"\\")
                output += [r"\bottomrule\end{tabular}\end{center}"]
                if table_group:
                    output.append(r"\end{samepage}")
                    table_group=False
            continue
        if block.startswith("- "):
            output.append(r"\begin{itemize}")
            output.extend(r"\item "+inline(line[2:]) for line in block.splitlines());output.append(r"\end{itemize}");continue
        if block.startswith("**Table "):
            output.append(r"\begin{samepage}")
            table_group=True
        output.append(inline(" ".join(block.splitlines()))+"\n")
    output.append(r"\end{document}")
    return "\n".join(output)+"\n"


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--figure",choices=["loss-sweep","calibration","risk-mismatch","paired-codecs","congestion"])
    parser.add_argument("--text-only",action="store_true",help="Rebuild text/references while preserving figures from identical saved analysis and plot data")
    parser.add_argument("--pdf",action="store_true",help="Export with an existing pdflatex after the native-editor compile check")
    args=parser.parse_args()
    tables,metrics,specs=analyse()
    if args.text_only:
        if args.figure or metrics != read_json("paper/analysis.json") or specs != read_json("paper/plot-data.json"):
            raise ValueError("Text-only build requires unchanged analysis and plot data")
    figures=PAPER/"figures";figures.mkdir(parents=True,exist_ok=True)
    if args.text_only and any(not (figures/(name+suffix)).is_file()
                             for name in specs for suffix in (".png", ".svg")):
        raise ValueError("Text-only build requires the saved figures")
    for name,spec in specs.items():
        if not args.text_only and (args.figure is None or args.figure==name):plot(spec,figures/name)
    if args.figure is not None:return
    references=read_json("paper/references.json")
    assert all(2020<=r["year"]<=2026 and r["access"] in {"abstract","full_text"} for r in references)
    template=(PAPER/"manuscript-template.md").read_text(encoding="utf-8")
    for name,table in tables.items():template=template.replace("{{"+name+"}}",table)
    assert not re.search(r"\{\{[A-Z]+\}\}",template)
    keys=set(re.findall(r"\\cite\{([^}]+)\}",template));keys={k for group in keys for k in group.split(",")}
    assert keys=={r["key"] for r in references}, (keys,{r["key"] for r in references})
    reference_numbers={r["key"]:i+1 for i,r in enumerate(references)}
    readable=re.sub(r"\\cite\{([^}]+)\}",lambda m:"["+", ".join(str(reference_numbers[k]) for k in m[1].split(","))+"]",template)
    bibliography="\n\n".join(f"[{i+1}] {r['text']} [Source]({r['url']})." for i,r in enumerate(references))
    readable=readable.replace("## References\n","## References\n\n"+bibliography+"\n")
    (PAPER/"manuscript.md").write_text(readable,encoding="utf-8")
    (PAPER/"main.tex").write_text(to_tex(template,specs,references),encoding="utf-8")
    (PAPER/"analysis.json").write_text(json.dumps(metrics,indent=2)+"\n",encoding="utf-8")
    (PAPER/"plot-data.json").write_text(json.dumps(specs,indent=2)+"\n",encoding="utf-8")
    # Manifest excludes itself and PDF exports, whose bytes depend on the compiler.
    sources=[p for pattern in ("output/*/manifest.json","output/studies/*/manifest.json") for p in ROOT.glob(pattern)]
    sources += [ROOT/"scripts/build_paper.py",PAPER/"manuscript-template.md",PAPER/"references.json",ROOT/"docs/reference-audit.json"]
    manifest={"analysis_kind":"retrospective descriptive reconstruction; no new experimental runs", "python":platform.python_version(),
              "measured_revision":"1ee75227af7288491722a42813203a136ed37948", "reference_checked_date":read_json("docs/reference-audit.json")["verified_on"],
              "inputs_sha256":{str(p.relative_to(ROOT)).replace("\\","/"):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
              "outputs_sha256":{str(p.relative_to(ROOT)).replace("\\","/"):hashlib.sha256(p.read_bytes()).hexdigest() for p in [PAPER/"analysis.json",PAPER/"plot-data.json",PAPER/"manuscript.md",PAPER/"main.tex"]+sorted(figures.glob("*.png"))+sorted(figures.glob("*.svg"))},
              "figure_processing":"All configured points; no clipped observations; sample SD across seeds on transport and paired-contrast plots; exact risk scatter is 153 case aggregates with n=20000 each. SVG and embedded LaTeX vectors use the same plot-data.json."}
    (PAPER/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    if args.pdf:
        output=ROOT/"tmp/paper-build";output.mkdir(parents=True,exist_ok=True)
        for _ in range(2):
            run=subprocess.run(["pdflatex","--disable-installer","-interaction=nonstopmode","-halt-on-error","-output-directory="+str(output),str(PAPER/"main.tex")],cwd=ROOT,text=True,capture_output=True)
            if run.returncode:
                print(run.stdout[-6000:]);print(run.stderr);run.check_returncode()
        destination=ROOT/"output/pdf/paritylab-paper.pdf"
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_bytes((output/"main.pdf").read_bytes())
        (PAPER/"pdf-export.json").write_text(json.dumps({
            "source_sha256":hashlib.sha256((PAPER/"main.tex").read_bytes()).hexdigest(),
            "pdf_sha256":hashlib.sha256(destination.read_bytes()).hexdigest(),
            "reference_checked_date":manifest["reference_checked_date"],
            "scope":"Two-pass pdflatex export of the recorded standalone source"
        },indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"counts":{k:v for k,v in metrics.items() if isinstance(v,int)},"calibration_max_error":metrics["calibration_max_error"],"figures":len(specs),"references":len(references)},indent=2))


if __name__=="__main__":
    main()
