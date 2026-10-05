# Emulator and controller model

## Channel and timing

Each forward data or parity symbol occupies `packet_size + 40` modeled wire bytes. Each acknowledgment or loss report occupies 48 modeled wire bytes. Forward and reverse queues serialize independently at the configured bandwidth; propagation delay applies after serialization. Acknowledgments containing recovered sequence numbers are modeled as compact control messages. These sizes are accounting assumptions, not the actual JSON/base64 sizes of the separate UDP demonstration.

The default timeout, in seconds, is `max(0.02, 2 * delay_ms / 1000 + symbol_serialization_time * (window + 16) + 0.005)`. It is the same across schemes at a given link/window configuration and starts at transmission completion. A user-specified timeout can cause unnecessary resends. The simulator now supports optional jitter and extra reordering delay. It has no adaptive round-trip estimator or corruption model; the separate socket proxy injects corruption. The shared-flow evaluator supplies a finite buffer and a teaching AIMD congestion window.

Bernoulli loss makes independent erasure decisions for all forward data and parity packets. Return-path acknowledgments use a separate seeded generator. Gilbert-Elliott loss uses two states: good emits no erasures, and bad erases every packet. The default bad-to-good transition probability is 0.2 per forward packet. At target loss `p`, the good-to-bad transition is `p * b / (1-p)`, where `b` is capped to keep both transition probabilities in range. The initial state has bad-state probability `p`. This gives stationary erasure probability `p` and approximately five-packet mean bad runs at the saved 10% setting. State evolves at packet transmissions, rather than continuously during idle time. Time-varying burst configurations have transient behavior and do not immediately achieve the new stationary rate.

## Protocol state

Go-Back-N retains only the next expected packet at the receiver, sends cumulative acknowledgments, and resends the outstanding window on base-packet timeout. Selective Repeat buffers out-of-order arrivals, acknowledges each received or reconstructed sequence number, and resends only unacknowledged packets on their own timers. Acknowledgments can be lost; duplicate data elicit another acknowledgment.

The sender window bounds outstanding original data sequence numbers. Parity shares link serialization and consumes bandwidth, while original data limits admission to the window. Fixed and adaptive parity modes wait for enough window space for a whole block except for the final block. Unprotected modes use every free slot. This block-admission policy can influence FEC goodput and is part of the measured implementation.

The simulator initializes block descriptors in receiver state out of band. After the final first-attempt block transmission reaches its expected arrival time, the receiver reports how many original data packets arrived, before reconstruction. Loss reports traverse the reverse queue and can be erased. This assumes known block metadata and a known reporting deadline; it is idealized instrumentation. Select `metadata_mode="reliable"` to serialize, impair, acknowledge, and retry block metadata before application interpretation. The full socket protocol carries repeated descriptors in each symbol and retried reporting requests; all control messages traverse its proxy.

## Codec and risk

XOR parity protects equal-width byte strings. Row/column parity assigns one equation to each grid row and column. The receiver iteratively solves equations containing one unknown. A rectangle of four erased data symbols remains unknown when each participating row/column still contains two unknowns, even if all parity survives. Retransmitting one of those symbols can unlock further peeling. Missing final-grid cells are known absent; only actual packet indices are included in equations.

The controller updates `p_hat = (1-alpha) * p_hat + alpha * raw_loss_fraction`, with `alpha = 0.25` and initial `p_hat = 0`. Reports include first-attempt data losses even if FEC repaired them. The controller does not consult the configured loss probability. A clean initial estimate is a startup assumption and can underprotect early blocks.

For independent identical erasure probability `p` and a full block of `k` data packets:

```text
No parity: P_fail = 1 - (1-p)^k
One XOR:  P_fail = 1 - (1-p)^k - k*p*(1-p)^k
```

The XOR expression includes parity loss. Success means either all data arrive, or one datum is lost and the parity arrives. For small grids, every data/parity erasure mask is evaluated against the peeling decoder. If `a_e` is the number of failing masks with `e` erasures among `n` transmitted symbols, the exact modeled risk is `sum(a_e * p^e * (1-p)^(n-e))`.

Candidates are no parity with up to 16 data packets, XOR blocks of 16/8/4/2 packets, and 3x3/2x3/2x2 grids; candidates larger than the sender window are excluded. The controller selects the lowest parity-payload overhead meeting `P_fail <= 0.01`, preferring a larger block on equal overhead. If none meets the target, it selects minimum modeled risk and marks the choice infeasible. The trace records applied choices after a block is admitted, including its actual `data_packets` count. It reports the candidate's full-block risk; shortened blocks contain fewer unknown data symbols. This risk is not a calibrated guarantee under burst loss, loss-estimation error, unequal parity loss, or changing channel conditions.

## Metrics

| Field | Definition |
| --- | --- |
| `completion_time_s` | Virtual time when the last original file byte becomes available at the receiver |
| `sender_completion_time_s` | Virtual time when all original data are acknowledged, or when the run stops incomplete |
| `goodput_mbps` | Original delivered file bytes times eight, divided by receiver completion time and one million |
| `retransmissions` | Every data transmission after a sequence number's first attempt, including unnecessary repeats caused by lost acknowledgments |
| `mean_delay_ms`, `p95_delay_ms` | Recovery time minus first transmission start; nearest-rank 95th percentile; measures receiver availability, not in-order application release |
| `parity_overhead_ratio` | Parity payload bytes divided by original file bytes; final padding is included in parity payload size |
| `total_forward_overhead_ratio` | Modeled forward wire bytes minus original file bytes, divided by original file bytes; includes parity, padding, retransmissions, and fixed headers |
| `fec_recovery_ratio` | Original data erasures reconstructed before a retransmission is sent, divided by original data erasures; zero when no original data were lost |
| `completed` | All data received and acknowledged before the event limit; successful output bytes must equal input |

The localhost demo uses JSON/base64 framing, loss-exempt block-start/report exchanges, and selective retries per block. It does not emulate the virtual link's delay/bandwidth, inject acknowledgment loss, or reproduce simulator timings. Its elapsed time includes receiver shutdown and is not a transport benchmark.

The interactive replay captures actual data, parity, and packet-acknowledgment transmissions with their serialization start, expected arrival, loss outcome, sequence, and attempt. Separate block-loss feedback messages remain outside the replay. The sender completion time bounds playback. Packet paths and briefly held loss marks are illustrative; the timeline uses measured virtual timestamps. FEC recovery is shown as an aggregate because per-packet decoder recovery timestamps are not exported.


## Optional policies and calibration

`controller_policy="legacy"` preserves the baseline EWMA choice and full-candidate risk. `uncertainty` uses approximate Wilson loss intervals and evaluates the actual partial block. `burst` fits first-order binary Markov transitions from ordered first-attempt data observations, reporting independent fallback when transition evidence is insufficient. Noncontiguous/count-only feedback never creates artificial adjacency. History is bounded. Markov envelopes are conservative only when their parameter rectangle includes the true stationary process. Approximate intervals can miss; changing loss, unequal data/parity erasures, and hidden-state emission models fall outside that assurance. `output/calibration/results.md` and raw trials report both exact-model accuracy and estimated-policy failures.

## Application release and competing flows

Results distinguish availability from in-order release with `application_completion_time_s`, `application_packet_delays_ms`, and head-of-line metrics. Original sequence bytes are released only after preceding sequences exist. For completed runs, the application digest must also match the input.

`simulate_competing_flows` uses one shared FIFO bottleneck with tail drop and a congestion window per flow. Data, parity, and retransmissions all consume flight slots. ACK-clocked slow start/additive increase and timeout reduction are teaching rules rather than TCP/QUIC conformance. Queue capacity includes the packet currently in service. Fairness is derived from useful in-order bytes in the common active interval. Congestion wire-flight slots and GBN reliability timers remain independent. Block descriptors are out of band in this evaluator; reliable metadata is tested separately.

## Full socket transport

`socket-run` uses actual CRC-framed binary datagrams with independent sender, proxy, and receiver processes. Unlike the small legacy `udp-demo` described above, all control traffic is impaired, all schemes have full windows, and receivers report availability and application-release timestamps. Framed UDP payload bytes are counted; IP/UDP headers are excluded. Wall clocks and OS scheduling differ from virtual time. See `socket-protocol.md` for limits and framing. The presentation UI invokes this full transport.
