# Verification coverage

The table maps the implemented behavior to its checks and saved results. The local testbed includes editable reports, raw measurements, an offline interface, and package verification. Public documents omit college identifiers; the submission originals are retained locally.

| Requirement | Implementation | Evidence and acceptance check |
| --- | --- | --- |
| Go-Back-N, Selective Repeat, fixed XOR and adaptive FEC | `src/paritylab/simulation.py`, `socket_transport.py` | 68-test suite in `output/verification/tests.txt`; byte hashes in baseline and socket records |
| Binary XOR/grid repair, parity loss and partial tails | `fec.py` | Exhaustive small-grid risk/decoder agreement; binary-tail tests; calibration raw masks |
| Capacity, propagation, independent/burst/changing loss and ACK loss | `channel.py`, `simulation.py` | 260 transfers across five seeds; summaries, CDF and controller timeline in `output/experiments` |
| Three separate socket processes and full windows | `wire.py`, `socket_transport.py` | 36 verified transfers in `output/socket-evaluation`; distinct process IDs, actual received bytes and digests |
| Impaired metadata, duplicates, corruption and reordering | `simulation.py`, `socket_transport.py` | Metadata-loss and bounded-failure tests; combined-impairment socket records |
| In-order application delivery | Receiver release records | Contiguous-release tests and measured recovery, application and head-of-line delays |
| Raw-loss adaptation and explicit infeasibility | `controller.py` | Applied decisions preserve original erasures, actual block sizes and model assumptions |
| Uncertainty and burst-aware protection | `controller.py`, `calibration.py` | 3,060,000 decoder trials plus 225,000 estimated-policy trials; source-bound calibration audit |
| Controlled sensitivity | `studies.py` | 370 verified transfers changing delay, capacity, window, timer, symbol/block size and burst duration |
| Equal-overhead decoder comparison | `studies.py` | 160,000 trials; identical erasure masks per codec pair; fixed 50%/100% parity budgets |
| Shared capacity and congestion behavior | `congestion.py`, `evaluation.py` | 70 finite-FIFO competing-flow runs / 140 verified transfers; teaching AIMD; fairness from useful in-order releases |
| Lab presentation controls and animated recorded replay | `web/`, `server.py` | Desktop/mobile browser receipt, keyboard/replay checks and inspected CSV/JSON/socket exports in `output/verification/ui.json` |
| Recorded-result attribution | Immutable last-trial config and changed-settings notice | Control changes retain recorded settings; export wording branches on actual verification |
| References published in 2020–2026 | `docs/proposal.md`, `references.bib` | Seven audited sources; `docs/reference-audit.json`; automatic date-range check |
| Proposal and final report | `scripts/build_proposal.py`, `build_report.py` | PDFs and editable Markdown; page/text/render hashes in `output/verification/pdf-render.json` |
| Reproducible package and offline assets | `setup.py`, `MANIFEST.in`, `scripts/ready.ps1` | `output/release/verification.json`: extracted-source build, clean wheel install, complete installed tests, every socket scheme, UI/fonts/PDF retrieval |

Run `.\scripts\ready.ps1` to verify the saved source-bound measurements, run the suite, rebuild and render both PDFs, and verify the release from outside this checkout. Add `-Reproduce` to regenerate transport studies, or `-Calibration` to include the full calibration. A successful source receipt and a successful isolated-release receipt are the release gates. `output/release/checksums.json` identifies the final ZIP and wheel.

For presentation, start `python -m paritylab demo` and open http://127.0.0.1:8770. Follow `docs/ui-demo.md`. The wheel includes local fonts and both PDFs; there is no frontend build or remote asset dependency.

The results support the recorded conditions. Adaptive parity does not always maximize goodput. The 1% target depends on the chosen loss model and estimated parameters; uncertainty intervals can miss and changing loss receives no universal guarantee. Socket wall time depends on OS scheduling. The AIMD evaluator is a teaching model; the actual socket transport remains loopback-only and has no production Internet congestion controller.
