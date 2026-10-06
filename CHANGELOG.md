# Changelog

## Unreleased

- Rework the local demo with plain labels, separate transmission lanes, packet inspection, event jumps, and in-order delivery curves.
- Add five-seed comparisons, session run history, recorded-settings links, and presentation mode.
- Record receiver acceptance and application release for replay without changing transport measurements.
- Preserve measured source for saved studies in a checksum-verified archive and distinguish historical verification from current-source measurements.
- Check replay reconstruction, statistical summaries, CSV exports, and historical-source integrity in the test suites.

## 1.0.0 — 2026-10-05

- Implement Go-Back-N, Selective Repeat, fixed XOR, and adaptive parity over binary payloads.
- Add deterministic channel simulation and three-process sliding-window UDP transfers with impaired controls, integrity checks, and bounded failures.
- Add independent-loss, uncertainty, and fitted burst protection policies with decoder-aware risk calculations.
- Provide replay, comparisons, controller inspection, result exports, and socket verification in a local browser interface.
- Include baseline, sensitivity, matched-budget codec, congestion, socket, and calibration studies with source-bound manifests.
- Package offline UI assets and reports; verify clean installation and add Windows/Linux CI.
- Document the model assumptions, contribution limits, and references from 2020–2026.
