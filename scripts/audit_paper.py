"""Audit the manuscript against saved measurements and inspect the exported PDF.

This checks reconstruction and reporting, not historical priority, external peer
review, or author approval. Rendering produces local inspection files in tmp/.
"""
import argparse
import hashlib
import json
import math
import re
import statistics
from pathlib import Path

from build_paper import ROOT, PAPER, analyse, read_json, read_csv, to_tex


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def audit(render=False):
    tables, metrics, specs = analyse()  # Includes raw-record/source audit.
    require(metrics == read_json("paper/analysis.json"), "Rebuild analysis.json")
    require(specs == read_json("paper/plot-data.json"), "Rebuild plot-data.json")
    template = (PAPER / "manuscript-template.md").read_text(encoding="utf-8")
    manuscript = (PAPER / "manuscript.md").read_text(encoding="utf-8")
    tex = (PAPER / "main.tex").read_text(encoding="utf-8")
    references = read_json("paper/references.json")
    require(len(references) == len({r["key"] for r in references}) == 10,
            "Duplicate or missing references")
    for ref in references:
        require(2020 <= ref["year"] <= 2026, "Reference outside requested range")
        require(ref["access"] == "full_text" and ref["locator"] and ref["status"],
                "Missing reading/status record")
    bibliography = (PAPER / "references.bib").read_text(encoding="utf-8")
    bib_records = re.split(r"(?=@(?:article|misc|techreport)\{)", bibliography)[1:]
    require(len(bib_records) == 10, "BibTeX record count")
    for ref in references:
        record = next((r for r in bib_records if r.split("\n", 1)[0].endswith(ref["key"] + ",")), "")
        require(record and f"year = {{{ref['year']}}}" in record and ref["url"] in record,
                "BibTeX key/year/URL mismatch: " + ref["key"])
    reconstructed = template
    for name, table in tables.items():
        require(reconstructed.count("{{" + name + "}}") == 1, "Missing table token")
        reconstructed = reconstructed.replace("{{" + name + "}}", table)
    numbers = {r["key"]: i + 1 for i, r in enumerate(references)}
    cited = {key for group in re.findall(r"\\cite\{([^}]+)\}", reconstructed) for key in group.split(",")}
    require(cited == set(numbers), "Unmatched or unused citation")
    readable = re.sub(r"\\cite\{([^}]+)\}",
                      lambda m: "[" + ", ".join(str(numbers[k]) for k in m[1].split(",")) + "]",
                      reconstructed)
    bibliography_md = "\n\n".join(f"[{i+1}] {r['text']} [Source]({r['url']})."
                                 for i, r in enumerate(references))
    readable = readable.replace("## References\n", "## References\n\n" + bibliography_md + "\n")
    require(readable == manuscript, "Markdown has drifted from measured tables/template")
    require(to_tex(reconstructed, specs, references) == tex, "LaTeX has drifted")
    require(len(tables) == 9 and len(specs) == 5, "Table/figure count")
    for text in (manuscript, tex):
        require(not re.search(r"\{\{[A-Z]+\}\}|\[UNSUPPORTED\]|\[PENDING:", text),
                "Unresolved technical marker")
        require(not re.search(r"\b\d{2}[A-Z]{3}\d{4}\b", text), "College register number")
    # Independently rederive the numeric prose from the saved observation units.
    baseline = read_json("output/experiments/runs.json")
    verified_numbers = {}
    for loss in (10, 20):
        for scheme in ("fixed", "adaptive"):
            rows = [r for r in baseline if r["scenario"] == "sweep" and r["loss_percent"] == loss
                    and r["scheme"] == scheme]
            require(len(rows) == 5, "Baseline replication count")
            for field, places in (("goodput_mbps", 3), ("retransmissions", 1), ("parity_overhead_ratio", 3)):
                values = [r[field] for r in rows]
                value = f"{statistics.mean(values):.{places}f} +/- {statistics.stdev(values):.{places}f}"
                require(value in manuscript, f"Prose/table statistic missing: {loss}/{scheme}/{field}")
                verified_numbers[f"{loss}/{scheme}/{field}"] = value
    calibration = read_csv("output/calibration/summary.csv")
    empirical_max = max(abs(float(r["prediction"]) - int(r["failures"]) / int(r["trials"]))
                        for r in calibration)
    bound = math.sqrt(math.log(2 * len(calibration) / 0.01) / (2 * 20000))
    require(math.isclose(empirical_max, metrics["calibration_max_error"], abs_tol=1e-12),
            "Calibration maximum")
    require(math.isclose(bound, metrics["simultaneous_bound99"], abs_tol=1e-12), "Hoeffding expression")
    require(f"{empirical_max:.8f}" in manuscript and f"{bound:.8f}" in manuscript, "Abstract calibration numbers")
    for name in ("wrong_iid_stationary_max_error", "wrong_iid_all_starts_max_error"):
        require(f"{metrics[name]:.8f}" in manuscript, "Model-mismatch prose number")
    for loss in (0, .01, .1, .5, 1):
        # One XOR over eight data succeeds with no missing data, or one missing
        # data plus a surviving repair. This is independent of mask enumeration.
        analytic = 1 - (1 - loss) ** 8 - 8 * loss * (1 - loss) ** 8
        row = next(r for r in calibration if r["model"] == "independent" and r["protection"] == "xor-8"
                   and int(r["data_symbols"]) == 8 and float(r["loss"]) == loss)
        require(math.isclose(analytic, float(row["prediction"]), abs_tol=1e-12), "XOR expression")
    policy = read_csv("output/calibration/policy-validation.csv")
    active = [r for r in policy if r["model"] == "binary_markov" and r["policy"] == "burst"
              and r["risk_model"] == "binary Markov parameter envelope"]
    feasible = [r for r in policy if r["model"] == "binary_markov" and r["policy"] == "burst"
                and r["target_met"] == "True"]
    require(len(active) == 29 and len(feasible) == 1
            and feasible[0]["risk_model"] != "binary Markov parameter envelope"
            and float(feasible[0]["ci95_low"]) > .01
            and all(r["upper_below_true_model_failure"] == "False" for r in active),
            "Burst abstention/fallback interpretation")
    require("twenty-nine of thirty cases infeasible" in manuscript
            and "sole feasible choice is a failing independent fallback" in manuscript,
            "Abstract must report abstention")
    codec = read_csv("output/studies/equal-overhead/summary.csv")
    for model, counts in (("bernoulli", (28, 203)), ("gilbert-elliott", (380, 340))):
        for code, count in zip(("grid-2x2", "per-packet-replication"), counts):
            row = next(r for r in codec if r["model"] == model and float(r["loss"]) == .1 and r["code"] == code)
            require(int(row["failed"]) == count, "Equal-budget prose count")
    manifest = read_json("paper/manifest.json")
    for group in ("inputs_sha256", "outputs_sha256"):
        for name, expected in manifest[group].items():
            require(digest(ROOT / name) == expected, "Stale manuscript manifest: " + name)
    for name, spec in specs.items():
        for series in spec["series"]:
            require(len(series["x"]) == len(series["y"]), "Unpaired plot values")
            require(all(spec["xlim"][0] <= v <= spec["xlim"][1] for v in series["x"])
                    and all(spec["ylim"][0] <= v <= spec["ylim"][1] for v in series["y"]),
                    "Clipped plot observations: " + name)
            require(all(spec["ylim"][0] <= y - e and y + e <= spec["ylim"][1]
                        for y, e in zip(series["y"], series.get("error", [0]*len(series["y"])))),
                    "Clipped error bars: " + name)
    # Inspect the actual export, independently of its LaTeX source.
    from pypdf import PdfReader
    pdf = ROOT / "output/pdf/paritylab-paper.pdf"
    reader = PdfReader(pdf)
    page_text = [p.extract_text() or "" for p in reader.pages]
    require(all(len(s.strip()) > 30 for s in page_text), "Blank or unreadable PDF page")
    plain = " ".join(" ".join(page_text).split())
    require("A Aswanth Raj" in plain and "Ranjithkumar S" in plain and "VIT Vellore" in plain,
            "Author/affiliation lost during export")
    require(not re.search(r"\[\s*\?\s*\]|\b\d{2}[A-Z]{3}\d{4}\b", plain), "Unresolved citation/identifier")
    require(all(f"Figure {i}:" in plain for i in range(1, 6)), "Missing PDF figure caption")
    # Latin Modern's bold T/a kerning is extracted with a space by pypdf.
    require(all(re.search(rf"T\s*able {i}\.", plain) for i in range(1, 8)), "Missing PDF table title")
    require("A.1 A.1" not in plain and "A.2 A.2" not in plain, "Duplicated appendix numbering")
    log = ROOT / "tmp/paper-build/main.log"
    compile_check = "log unavailable; PDF/source checked"
    if log.exists():
        log_text = log.read_text(encoding="utf-8", errors="replace")
        require(not re.search(r"^!|ignored error:|Overfull|undefined|LaTeX Warning:", log_text, re.M),
                "Compiler diagnostics require review")
        compile_check = "two-pass local compilation: no errors, overfull boxes, undefined citations or LaTeX warnings"
    if render:
        import pypdfium2 as pdfium
        from PIL import Image, ImageOps, ImageDraw
        output = ROOT / "tmp/pdfs/paper"
        output.mkdir(parents=True, exist_ok=True)
        doc = pdfium.PdfDocument(str(pdf))
        thumbs = []
        for i in range(len(doc)):
            page = doc[i]
            bitmap = page.render(scale=1.45)
            pil = bitmap.to_pil()
            pil.save(output / f"page-{i+1}.png")
            thumb = ImageOps.contain(pil, (230, 327))
            cell = Image.new("RGB", (244, 354), "#dddddd")
            cell.paste(thumb, ((244-thumb.width)//2, 5))
            ImageDraw.Draw(cell).text((8, 336), str(i+1), fill="black")
            thumbs.append(cell)
            bitmap.close()
            page.close()
        doc.close()
        for start in range(0, len(thumbs), 12):
            sheet = Image.new("RGB", (976, 1062), "white")
            for j, thumb in enumerate(thumbs[start:start+12]):
                sheet.paste(thumb, ((j % 4)*244, (j//4)*354))
            sheet.save(output / f"contact-{start//12+1}.png")
    receipt = {
        "status": "passed",
        "scope": "saved-data integrity, source provenance, manuscript reconstruction, selected prose numbers, citations, plots, PDF extraction and compiler diagnostics",
        "measured_revision": manifest["measured_revision"],
        "counts": {k: v for k, v in metrics.items() if isinstance(v, int)},
        "table_count": len(tables), "figure_count": len(specs), "reference_count": len(references),
        "pdf_pages": len(reader.pages), "pdf_text_characters": sum(map(len, page_text)),
        "compile_check": compile_check,
        "selected_prose_statistics": verified_numbers,
        "inputs_sha256": {name: digest(ROOT / name) for name in
                         ("scripts/audit_paper.py", "paper/manifest.json", "paper/references.bib",
                          "output/pdf/paritylab-paper.pdf")},
        "visual_review": "Rendering is available with --render; automated extraction does not certify visual layout.",
        "submission_status": "author declarations, approval and venue requirements unconfirmed",
    }
    (PAPER / "verification.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render", action="store_true", help="Render all PDF pages and contact sheets into tmp/")
    args = parser.parse_args()
    result = audit(args.render)
    print(json.dumps({k: result[k] for k in ("status", "table_count", "figure_count", "reference_count", "pdf_pages", "compile_check")}, indent=2))
