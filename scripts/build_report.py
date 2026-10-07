"""Build the final measured lab report and its printable PDF from saved evidence."""
import csv
import hashlib
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def check_receipt(receipt):
    if (receipt.get("exit_code") != 0 or receipt.get("references_in_range") is not True
            or receipt.get("experiment_integrity") is not True or receipt.get("measurements_verified") is not True):
        raise RuntimeError("Run successful verification before generating the report")
    fingerprints = {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                    for directory in ("src", "tests") for path in sorted((ROOT / directory).rglob("*.py"))}
    if not fingerprints or receipt.get("source_sha256") != fingerprints:
        raise RuntimeError("The test receipt does not match current source; run verification again")
    measurements = receipt.get("measurements", {})
    expected = {"experiments", "studies/sensitivity", "studies/equal-overhead", "congestion", "socket-evaluation", "calibration"}
    if set(measurements) != expected or any(row.get("passed") is not True or row.get("source_verified") is not True
            or (row.get("source_current") is not True and not row.get("archived_revision"))
            for row in measurements.values()):
        raise RuntimeError("Measurement provenance is incomplete or unverified; run verification again")


def report_text():
    receipt = load("output/verification/receipt.json")
    check_receipt(receipt)
    transcript = (ROOT / "output/verification/tests.txt").read_text()
    tests = int(re.search(r"Ran (\d+) tests", transcript)[1])
    with (ROOT / "output/experiments/summary.csv").open(newline="") as stream:
        summary = list(csv.DictReader(stream))
    calibration = load("output/calibration/manifest.json")
    lines = ["# ParityLab: measured packet reliability", "",
             "Author: A Aswanth Raj", "",
             "Local experimental evaluation, October 2026", "",
             "## Outcome", "",
             "The project implements Go-Back-N, Selective Repeat, fixed XOR parity, and adaptive parity over actual byte payloads. It includes a deterministic event-driven emulator, a three-process localhost UDP transport, a responsive presentation interface with recorded replay, and reproducible raw experiments. The bibliography contains seven sources published within 2020-2026.", "",
             f"The current suite passes {tests} tests. Saved evidence covers 260 baseline transfers, 370 one-factor sensitivity transfers, 70 shared-bottleneck runs (140 flow transfers), 36 three-process socket transfers, 160,000 equal-overhead codec trials, {calibration['decoder_trials']:,} calibration decoder trials, and {calibration['policy_test_trials']:,} estimated-policy trials. Completed transport outputs are checked against the input bytes and digest. These counts describe separate experiments, not one pooled sample.", "",
             ("The saved studies match the current source fingerprints."
              if all(row["source_current"] for row in receipt["measurements"].values()) else
              "The current correctness tests cover this release. Some saved studies describe an earlier measured revision preserved in output/measured-source/. Verification checks the archived source bytes and each recorded artifact. These historical measurements are not new measurements of this release."), "",
             "Adaptive parity reduces recovery work in some tested conditions and costs bandwidth in others. The legacy independent-loss controller does not consistently improve goodput under bursts. The 1% block-failure target is conditional on the fitted loss model; it is not an unconditional delivery or Internet performance guarantee.", "",
             "## Implementation and protocol", "",
             "The emulator serializes forward and reverse links independently, adds one-way propagation delay, and applies seeded independent or binary Gilbert-Elliott erasures. Optional jitter, reordering, ACK loss, reliable metadata, and changing loss phases test protocol robustness. A separate shared finite FIFO bottleneck evaluates two competing flows with a teaching AIMD congestion window that charges data, parity, and retries to the same flight budget.", "",
             "Go-Back-N accepts only the next sequence at the receiver, returns cumulative ACKs, and retries the outstanding window on a base timeout. Selective Repeat buffers out-of-order symbols, selectively ACKs them, and uses per-sequence timers. Fixed and adaptive FEC add parity to Selective Repeat; residual losses still use ARQ. XOR and iterative row/column peeling operate on padded binary symbols and preserve the original file length. A four-corner grid erasure can stop peeling even when all repair packets survive.", "",
             "The real transport launches separate sender, receiver, and impairment-proxy processes for each scheme. A retried manifest, repeated block descriptors, CRC-protected binary framing, raw first-attempt feedback, and retried final SHA-256 confirmation make control loss visible and recoverable. All messages traverse the proxy. Duplicate/corrupt/reordered messages and permanent loss are tested with explicit retry and runtime bounds. CRC detects accidental corruption; it does not authenticate a sender.", "",
             "## Experimental protocol and metrics", "",
             "The baseline uses 128 KiB files (512 KiB for changing loss), 1 KiB symbols, window 32, 5 Mbps bandwidth, 50 ms one-way delay, and five seeds (0-4). Eleven loss settings from 0% through 20% at two-point intervals, one 10% burst condition, and one changing-loss condition produce 260 transfers. The changing channel starts clean and changes at 0.4, 1.2, and 2.0 seconds. Each scheme receives identical configured conditions and seeds; different transmission schedules consume different random draws, so these are not identical loss masks.", "",
             "| Metric | Definition |", "| --- | --- |",
             "| Goodput | Original file bits / receiver completion seconds / 1,000,000 |",
             "| Receiver completion | Last original file byte becomes available |",
             "| Sender completion | Original data ACKs received; socket runs also confirm the final digest |",
             "| Retry count | Every original-data send after its first attempt |",
             "| Recovery delay | Receiver availability minus first send; nearest-rank p95 |",
             "| Application delay | In-order release minus first send; head-of-line wait measured separately |",
             "| Parity overhead | Parity payload bytes / original file bytes |",
             "| FEC recovery ratio | First-attempt data losses reconstructed before retransmission / first-attempt losses |", "",
             "Means are accompanied by sample standard deviation across seeds; this is not a confidence interval. Socket wall-clock measurements include framing and operating-system scheduling and are kept separate from virtual-time results. Forward emulator sizes are accounting assumptions; socket wire counters measure actual framed UDP payload bytes, excluding IP/UDP headers.", "",
             "## Baseline results", "",
             "| Condition | Scheme | Goodput Mbps, mean +/- SD | Retries, mean +/- SD | Parity / file |",
             "| --- | --- | --- | --- | --- |"]
    for r in summary:
        if r["scenario"] == "sweep" and r["loss_percent"] not in {"0", "10", "20"}:
            continue
        condition = f"{r['loss_percent']}% independent" if r['scenario'] == 'sweep' else r['scenario']
        lines.append(f"| {condition} | {r['scheme']} | {float(r['goodput_mbps_mean']):.3f} +/- {float(r['goodput_mbps_std']):.3f} | {float(r['retransmissions_mean']):.1f} +/- {float(r['retransmissions_std']):.1f} | {float(r['parity_overhead_ratio_mean']):.3f} |")
    lines += ["", "Fixed XOR can outperform the adaptive risk-target controller: minimizing parity subject to modeled block risk does not directly maximize goodput. The baseline is retained as a comparison for the legacy policy; uncertainty and burst policies are additional explicit options, not silently substituted into these results.", "",
              "![Loss sweep: five seeds per scheme and condition](../output/experiments/loss-sweep.png)", "",
              "![Recovery-delay CDF for the saved independent-loss condition](../output/experiments/delivery-cdf.png)", "",
              "![Applied adaptive controller decisions in changing loss](../output/experiments/controller-timeline.png)", "",
              "## Robustness and controlled comparisons", "",
              "The 36 socket experiments test each scheme over three seeds under independent data/ACK loss, burst loss, and combined metadata loss, jitter, reordering, duplication, and corruption. All completed files match the input digest and have three distinct process IDs. Reliable metadata and in-order delivery tests demonstrate that unavailable early symbols hold later application bytes until the gap is repaired. Permanent metadata loss has a bounded failure result and does not write a successful output file.", "",
              "The sensitivity study changes one factor at a time from the baseline: delay, capacity, window, timeout, symbol width, fixed XOR block size, or mean burst run length. It contains 370 verified transfers. The equal-overhead study holds the parity budget exactly at 50% or 100%, using identical erasure masks within each codec pair. Its 160,000 trials separate decoder structure from redundancy budget; they do not measure transport goodput. Wilson columns for correlated burst trials are descriptive rather than valid coverage guarantees.", "",
              "![One-factor sensitivity with sample SD across five seeds](../output/studies/sensitivity/sensitivity.png)", "",
              "## Risk calibration and policy limits", "",
              f"Exact independent and binary Markov predictions were tested in 153 conditions across five seeds and 4,000 trials per seed: {calibration['decoder_trials']:,} byte-decoder trials. There were zero incorrect recovered bytes. All exact predictions fell within the registered simultaneous 99% sampling-error check. The largest absolute prediction error was {calibration['maximum_exact_absolute_error']:.5f}; five individual approximate 95% Wilson intervals missed their exact predictions. Those checks have different coverage and are reported separately.", "",
              f"Using an independent model for stationary bursts produced an error up to {calibration['maximum_wrong_iid_stationary_burst_error']:.5f}; ignoring the specified preceding loss raised it to {calibration['maximum_wrong_iid_burst_error']:.5f}. The burst policy fits transition parameters from ordered raw first-attempt observations and uses a risk envelope when enough transitions exist. Count-only or noncontiguous feedback does not invent adjacent observations. Partial-block predictions evaluate the actual admitted size for the optional policies.", "",
              "Estimated-policy validation uses 225,000 further trials. Active Markov envelopes showed no violations when their estimated parameter rectangle contained the truth. Approximate intervals sometimes excluded the truth; independent fallback, changing loss, hidden-state emissions, and unequal data/parity loss do not receive a burst-risk guarantee. Calibrating a known stationary decoder model does not establish an end-to-end transport guarantee.", "",
              "![Exact-model calibration and estimated-policy evaluation](../output/calibration/calibration.png)", "",
              "## Congestion evaluation", "",
              "Seventy runs transfer two 256 KiB files through one finite FIFO link at 2 Mbps and 20 ms one-way delay with 1% channel and ACK loss, queue capacities 8 and 32, and five seeds. Configurations include equal AIMD, equal uncontrolled senders, AIMD versus uncontrolled, and every scheme versus Selective Repeat. All 140 flow outputs are verified. Jain fairness uses actual in-order useful bytes during the common active interval, rather than requested rates or total sent symbols. Equal AIMD settings still have finite-file start/tail effects and unequal shares.", "",
              "The congestion evaluator is a teaching model with ACK-clocked growth and timeout reduction, not RFC-compliant TCP/QUIC. Its block descriptors are out of band; reliable metadata is tested separately. Go-Back-N reliability sequence timers remain independent of congestion flight slots so ACKs for discarded attempts cannot accidentally cancel data recovery. The real socket implementation remains a bounded loopback transport without Internet congestion control.", "",
              "![Congestion window and useful release rate: AIMD versus uncontrolled](../output/congestion/competing-flows.png)", "",
              "## Requirement-to-evidence matrix", "",
              "| Deliverable | Implementation | Verification artifact |", "| --- | --- | --- |",
              "| Four sliding-window schemes | simulation.py, socket_transport.py | tests.txt; experiments/runs.json; socket-evaluation/runs.json |",
              "| XOR / grid codecs and partial tail | fec.py | CodecTests; calibration/verification.json |",
              "| Adaptive raw-loss feedback | controller.py | ControllerTests; recorded controller traces |",
              "| Reliable impaired metadata and in-order release | simulation.py, wire.py, socket_transport.py | SimulatorTests; SocketTransportTests; socket-evaluation |",
              "| Uncertainty and burst-aware policies | controller.py, calibration.py | calibration/raw-trials.csv.gz; policy-validation.csv |",
              "| Multi-seed loss / burst / changing studies and plots | experiments.py | 260 runs; summary.csv; CDF and timeline |",
              "| Sensitivity and matched parity budgets | studies.py | 370 transfers; 160,000 paired decoder trials |",
              "| Shared capacity and congestion behavior | congestion.py, evaluation.py | 70 runs; queue bounds and common-interval fairness |",
              "| Interactive lab presentation | web/, server.py | output/verification/ui.json; frontend tests; recorded exports |",
              "| Reproducible installation and offline assets | setup.py; scripts/ready.ps1 | output/release/verification.json; checksums.json |",
              "| Reviewed 2020-2026 bibliography | docs/proposal.md; references.bib | docs/reference-audit.json; reference year check |", "",
              "## Running and reproducing", "",
              "Install Python 3.10 or newer. From the source bundle, run python -m pip install -e . and python -m paritylab demo, then open http://127.0.0.1:8770. The wheel includes the same UI, local fonts, proposal, and report. No frontend build, account, or online asset is needed after installation. The UI socket button selects any of the four protocols and downloads its actual receipt. Emulator replay stays paused until requested.", "",
              "On Windows, .\\scripts\\ready.ps1 checks the saved evidence, runs the current suite, rebuilds PDFs, and makes a verified release. Add -Reproduce to rerun baseline, sensitivity, paired-codec, congestion, and socket experiments. Add -Calibration to regenerate the full calibration too. Equivalent portable Python commands are in README.md. The measurement audit accepts current source bytes or a checksum-verified archive of the measured revision and reports which was used. Use python scripts/audit_measurements.py --require-current to require fresh measurements of the checkout; historical matches fail that check. Regenerate the relevant measurements rather than relabeling old hashes.", "",
              "The source bundle contains raw records, scripts, tests, figures, PDFs, bibliography, and the offline UI. The release verification installs the wheel in a fresh environment, runs the full suite from outside the checkout, fetches UI assets and both PDFs, and transfers binary bytes using every socket scheme. A checksum manifest accompanies the ZIP and wheel. Timings on a different machine will differ, especially for sockets.", "",
              "## Limitations and conclusion", "",
              "The delivered scope is a local academic lab. It has no cryptographic peer authentication, path-MTU discovery, production congestion-controlled socket transport, or Internet field trial. Binary first-order packet-index Markov erasures are simpler than real network bursts. Default emulator descriptors remain idealized unless reliable metadata is selected. Five-seed summaries are small condition-specific samples; they do not prove universal rankings. Candidate risk infeasibility and finite transfer budgets are explicit failure modes.", "",
              "The project makes the parity/retransmission tradeoff inspectable: a presenter can change conditions, replay recorded packets, explain applied protection choices, verify actual socket bytes, and trace each reported result back to raw data. Modern prior work already studies adaptive FEC; this contribution is an educational implementation and controlled evaluation, not a claim of a new transport standard.", "",
              "## References (2020-2026)", ""]
    references = (ROOT / "docs/proposal.md").read_text().split("## References (2020-2026)", 1)[1].strip()
    return "\n".join(lines) + "\n" + references + "\n"


def inline(text):
    text = text.replace("â€“", "-").replace("â€”", "-").replace("âˆ’", "-")
    text = html.escape(text)
    return re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<link href="\2" color="#1d7168">\1</link>', text)


def build_pdf(text):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Image, LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

    for name, file in (("Atkinson", "Atkinson-Regular.ttf"), ("AtkinsonBold", "Atkinson-Bold.ttf")):
        pdfmetrics.registerFont(TTFont(name, str(ROOT / "web/assets/fonts" / file)))
    body = ParagraphStyle("Body", fontName="Atkinson", fontSize=10, leading=13.6, spaceAfter=7, textColor=colors.HexColor("#25333b"))
    h1 = ParagraphStyle("Title", parent=body, fontName="AtkinsonBold", fontSize=25, leading=29, spaceAfter=16)
    h2 = ParagraphStyle("Heading", parent=body, fontName="AtkinsonBold", fontSize=15, leading=19, spaceBefore=14, spaceAfter=8, keepWithNext=True)
    cell = ParagraphStyle("Cell", parent=body, fontSize=8.2, leading=10.5, spaceAfter=0, wordWrap="CJK")
    flow = []
    blocks = text.split("\n\n")
    for block in blocks:
        if not block.strip():
            continue
        if block.startswith("# "):
            flow.append(Paragraph(inline(block[2:]), h1))
        elif block.startswith("## "):
            flow.append(Paragraph(inline(block[3:]), h2))
        elif block.startswith("| "):
            rows = [[Paragraph(inline(c.strip()), cell) for c in line.strip().strip("|").split("|")]
                    for line in block.splitlines() if not line.startswith("| ---")]
            available = A4[0] - 80
            widths = {2: [.27, .73], 3: [.26, .28, .46], 5: [.21, .11, .27, .27, .14]}[len(rows[0])]
            table = LongTable(rows, colWidths=[available * w for w in widths], repeatRows=1, hAlign="LEFT")
            table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#e2e8e3")),
                                       ("VALIGN",(0,0),(-1,-1),"TOP"), ("LINEBELOW",(0,0),(-1,-1),.35,colors.HexColor("#c4c9bf")),
                                       ("LEFTPADDING",(0,0),(-1,-1),6), ("RIGHTPADDING",(0,0),(-1,-1),6),
                                       ("TOPPADDING",(0,0),(-1,-1),6), ("BOTTOMPADDING",(0,0),(-1,-1),6)]))
            flow.extend([table, Spacer(1, 10)])
        elif block.startswith("!["):
            match = re.match(r"!\[([^\]]+)\]\(([^)]+)\)", block)
            image = Image(str(ROOT / "docs" / match[2]))
            available = A4[0] - 80
            scale = min(available / image.imageWidth, 530 / image.imageHeight)
            image.drawWidth = image.imageWidth * scale
            image.drawHeight = image.imageHeight * scale
            flow.extend([image, Spacer(1, 5), Paragraph(inline(match[1]), cell), Spacer(1, 12)])
        else:
            flow.append(Paragraph(inline(block), body))

    def footer(canvas, document):
        canvas.setFont("Atkinson", 8)
        canvas.setFillColor(colors.HexColor("#59645f"))
        canvas.drawString(40, 23, "ParityLab | Experimental report | October 2026")
        canvas.drawRightString(A4[0]-40, 23, str(document.page))

    target = ROOT / "output/pdf/project-report.pdf"
    target.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(target), pagesize=A4, leftMargin=40, rightMargin=40, topMargin=38, bottomMargin=40,
                      title="ParityLab: measured packet reliability", author="A Aswanth Raj").build(flow, onFirstPage=footer, onLaterPages=footer)
    print(target)


if __name__ == "__main__":
    report = report_text()
    (ROOT / "docs/project-report.md").write_text(report, encoding="utf-8")
    build_pdf(report)
