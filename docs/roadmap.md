# Implemented scope

The implemented scope and its verification are listed below. See [verification coverage](readiness.md) for evidence. Internet field validation and a production socket congestion controller remain open research/engineering work.

- [x] Implement byte-level XOR and iterative row/column repair, including parity erasures and partial blocks.
- [x] Compare Go-Back-N, Selective Repeat, fixed parity, and adaptive parity in a serialized event-driven channel.
- [x] Validate transfer integrity, controller assumptions, and socket repair with automated tests.
- [x] Run independent/burst/changing loss experiments over five seeds and export figures and raw results.
- [x] Revise the proposal and its supporting references to the 2020-2026 publication range.
- [x] Build a responsive presentation demo with recorded replay, live comparisons, applied controller traces, exports, and a separate localhost UDP check.
- [x] Build separate socket sender, receiver, and impairment-proxy processes using all four full sliding-window state machines.
- [x] Add metadata-loss/reordering tests and in-order application delay measurement.
- [x] Calibrate block risk against empirical failures and add loss-estimate uncertainty and burst-aware protection.
- [x] Sweep capacity, delay, window, timer, block size, and burst duration; compare equal-overhead FEC configurations.
- [x] Add shared-FIFO teaching congestion control and competing-flow evaluation; keep the actual socket transport local.
