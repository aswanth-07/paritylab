# ParityLab proposal

Author: A Aswanth Raj

## Title

Loss-Adaptive Packet-Level Parity FEC with Selective Repeat ARQ for Reliable Data Transfer over Lossy Networks

## Abstract

Retransmission recovers lost packets but can increase delivery time, particularly when propagation delay is high and the sender's window is bounded. Forward error correction (FEC) sends repair packets that can reconstruct some losses before a retransmission arrives. Fixed redundancy introduces a tradeoff between bandwidth cost and recovery capability as network conditions change. This project implements a hybrid scheme that estimates raw packet loss from receiver feedback and selects a protection level for each block: no parity, one XOR parity packet with an adaptive block size, or two-dimensional row and column parity. Selective Repeat automatic repeat request (ARQ) recovers erasures that parity cannot repair. A Python event-driven emulator compares the scheme with Go-Back-N, plain Selective Repeat, and Selective Repeat with fixed XOR parity under independent, burst, and changing loss. The evaluation measures goodput, completion time, retransmissions, packet recovery delay, parity overhead, and FEC recovery ratio. A three-process localhost UDP transport verifies recovered file bytes for all four sliding-window schemes. Performance improvements are hypotheses to be tested rather than guaranteed outcomes.

## Existing work

Recent work studies adaptive FEC in different transport and application settings. Tsubaki et al. [7] evaluate Reed-Solomon protection for Multipath QUIC datagrams over commercial cellular paths. Chen et al. [9] combine matrix-status feedback and adaptive FEC with reinforcement learning in LTP. A March 2026 QUIC extension draft [10] separates recovered-packet reports from ordinary ACKs; it does not specify a redundancy controller and expired on September 17, 2026. These are context for feedback and adaptation, not implementations reproduced by this project.

Eghbal and Lu [8] report partial-order screen delivery with QUIC FEC in a 2025 journal article. Its deposited abstract supports application-delivery context; full text was not accessed. Wang et al. [11] study measured satellite loss and richer loss models in a 2026 journal article. Its author-posted abstract motivates treating our independent and binary Markov loss models as simplifications. Neither paper's numerical results are used as a comparison baseline.

The coding basis remains Golaghazadeh, Coulombe, and Robert's 2-D parity analysis [2]. FlEC [3], cited as its 2023 journal publication, evaluates application-aware reliability in QUIC. RFC 8681 [1] provides sliding-window coding context. RFC 9002 [4] explains acknowledgment-based loss detection; RFC 9265 [5] discusses preserving congestion signals. The expired 2024 adaptive-FEC draft [6] is retained as a versioned design reference. Adaptive FEC is established prior work. The contribution here is a transparent lab implementation and controlled comparison of parity with reliable retransmission.

## Gap identified

1. Retransmission-only baselines incur loss-detection and resend delays. A bounded window can limit utilization on links with a large bandwidth-delay product. The exact penalty depends on the timer and channel conditions.
2. A fixed parity configuration has a fixed redundancy cost, while its ability to repair erasures depends on loss patterns. This project tests whether switching among simple parity modes improves the latency/overhead tradeoff under selected conditions.
3. The lab needs a reproducible comparison that uses the same payload, link settings, window, and seed set for all four schemes; counts parity and retransmission cost; and preserves raw loss feedback even when decoding succeeds.
4. An independent-loss estimate does not describe burst structure. The experiments must report when a controller misses its model target, when protection is infeasible, and when added parity reduces goodput.

## Work proposed

1. Build a Python emulator with serialization delay, propagation delay, configurable bandwidth, Bernoulli loss, Gilbert-Elliott burst loss, lost acknowledgments, and changing loss phases.
2. Implement textbook Go-Back-N and Selective Repeat baselines with bounded windows and explicit timers; add fixed XOR parity to Selective Repeat.
3. Encode equal-length packet payloads using XOR and row/column parity. Pad the final packet and preserve the original file length. Decode by repeatedly repairing equations with one missing packet.
4. Estimate original data-packet erasures before FEC using an exponentially weighted moving average of receiver reports. Choose the least parity overhead among candidate configurations whose modeled probability of any unrepaired data in a block is at most 1%, accounting for lost repair packets. Use an exact independent-erasure calculation for small grids. If none meets the target, report infeasibility and select the lowest modeled failure probability.
5. Recover residual losses through Selective Repeat and verify the complete file bytes and SHA-256 digest. Reliability is conditional on eventual packet delivery, a working acknowledgment path, and the configured retry/event budget.
6. Evaluate a 0-20% independent-loss sweep, burst loss, and a changing-loss transfer with multiple seeds. Report means and sample standard deviations; examine sensitivity to delay, bandwidth, window, timer, and burst length before generalizing.

## Metrics to be evaluated

- Goodput: original file bits divided by receiver completion time.
- File transfer completion time, with sender confirmation time reported separately.
- Number of retransmitted data packets.
- Mean and 95th percentile packet recovery delay, measured from first transmission until bytes become available at the receiver; this differs from in-order application delivery delay.
- Parity payload bytes divided by original file bytes, plus total modeled forward overhead.
- FEC recovery ratio: original data-packet losses repaired before any retransmission is sent, divided by original data-packet losses.

## Final output

A Python implementation of the emulator and all four schemes; separate localhost sender, receiver, and impairment-proxy processes; reproducible experiment records; a comparison table; plots of goodput, retransmissions, overhead, completion time, and packet recovery delay; a recovery-delay cumulative distribution; and a controller mode-switching time series. The completed lab also includes impaired metadata and in-order delivery, risk calibration, uncertainty and burst-aware controller options, controlled sensitivity and equal-overhead comparisons, and a shared-bottleneck teaching congestion model. The interactive interface provides recorded replay and actual socket verification. The accompanying final report documents current evidence and limitations; Internet deployment remains outside the scope.

## References (2020-2026)

[1] V. Roca and B. Teibi. Sliding Window Random Linear Code (RLC) Forward Erasure Correction (FEC) Schemes for FECFRAME. RFC 8681, January 2020. DOI: 10.17487/RFC8681. [Source](https://www.rfc-editor.org/rfc/rfc8681.html).

[2] F. Golaghazadeh, S. Coulombe, and J.-M. Robert. Residual packet loss rate analysis of 2-D parity forward error correction. Signal Processing: Image Communication 102, 116597, March 2022. DOI: 10.1016/j.image.2021.116597. [Source](https://doi.org/10.1016/j.image.2021.116597).

[3] F. Michel, A. Cohen, D. Malak, Q. De Coninck, M. Medard, and O. Bonaventure. FlEC: Enhancing QUIC With Application-Tailored Reliability Mechanisms. IEEE/ACM Transactions on Networking 31(2), 606-619, April 2023. DOI: 10.1109/TNET.2022.3195611. Author manuscript: arXiv:2208.07741 (2022). [Source](https://doi.org/10.1109/TNET.2022.3195611).

[4] J. Iyengar and I. Swett. QUIC Loss Detection and Congestion Control. RFC 9002, May 2021. DOI: 10.17487/RFC9002. [Source](https://www.rfc-editor.org/rfc/rfc9002.html).

[5] N. Kuhn, E. Lochin, F. Michel, and M. Welzl. Forward Erasure Correction (FEC) Coding and Congestion Control in Transport. RFC 9265, July 2022. DOI: 10.17487/RFC9265. [Source](https://www.rfc-editor.org/rfc/rfc9265.html).

[6] D. Moskvitin, E. Onegin, R. Huang, H. Luo, and Q. Chen. Adaptive Forward Erasure Correction for Delay-Sensitive QUIC Connections. Internet-Draft draft-dmoskvitin-quic-adaptive-fec-00, May 6, 2024. This version expired November 7, 2024; work in progress, not an adopted standard. [Source](https://www.ietf.org/archive/id/draft-dmoskvitin-quic-adaptive-fec-00.html).

[7] T. Tsubaki, S. Anno, S. Komatsu, T. Torii, and T. Tojo. Scheduler-Agnostic Adaptive-FEC for MPQUIC: Field Evaluation over Commercial Cellular Paths. arXiv:2607.14482v1, July 16, 2026. DOI: 10.48550/arXiv.2607.14482. [Source](https://arxiv.org/abs/2607.14482).

[8] N. Eghbal and P. Lu. Lower-Latency Screen Updates over QUIC with Forward Error Correction. Future Internet 17(7), 297, June 30, 2025. DOI: 10.3390/fi17070297. [Source](https://doi.org/10.3390/fi17070297).

[9] L. Chen, Y. Song, K. Zhao, J. A. Fraire, and W. Li. Reliable Transmission of LTP Using Reinforcement Learning-Based Adaptive FEC. arXiv:2506.22470v1, June 19, 2025. DOI: 10.48550/arXiv.2506.22470. Author preprint. [Source](https://arxiv.org/abs/2506.22470).

[10] H. Zheng and Y. Liu. FEC Extension for QUIC. Internet-Draft draft-zheng-quic-fec-extension-02, March 16, 2026. Expired September 17, 2026; individual work in progress, not a standard. [Source](https://www.ietf.org/archive/id/draft-zheng-quic-fec-extension-02.html).

[11] T. Wang, T. Liu, Y. Li, J. Zhao, R. Gao, S. Wu, and J. Pan. Packet Loss Modeling and Forward Erasure Correction for LEO Satellite Networks. IEEE Transactions on Communications 74, 3999-4013, 2026. DOI: 10.1109/TCOMM.2026.3658383. [Source](https://doi.org/10.1109/TCOMM.2026.3658383).
