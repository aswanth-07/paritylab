# Review 2 demonstration

## Title

Loss-Adaptive Packet-Level Parity FEC with Selective Repeat ARQ for Reliable Data Transfer over Lossy Networks

This retains the abstract's subject: error control, packet loss, sliding windows,
acknowledgments, retransmissions, bandwidth, and delivery delay.

## Explain the project

"The sender divides a file into packets. It chooses how much XOR or row/column
parity to send, then uses Selective Repeat to recover losses that parity cannot
repair. The update reduces waiting by using receiver feedback to request missing
packets earlier, and prices parity against retry delay."

This is an implemented algorithm based on established coding and recovery work.
Novelty is not needed for this assessment. The project demonstrates a measured
modification, not a claim to have invented forward error correction.

## Literature and implementation

| Reference | Implemented connection | Boundary |
| --- | --- | --- |
| Golaghazadeh, Coulombe, Robert, *Residual packet loss rate analysis of 2-D parity forward error correction*, 2022, [DOI](https://doi.org/10.1016/j.image.2021.116597) | XOR row/column parity, matrix-size choices, peeling repair, and residual decoder failures. | Small inspectable grids; not a full reproduction of Pro-MPEG configurations or the paper's experiment. |
| Michel et al., *FlEC: Enhancing QUIC with application-tailored reliability mechanisms*, 2023 journal article; [2022 author manuscript](https://arxiv.org/abs/2208.07741) | Combine FEC with reliable retransmission and evaluate useful throughput/delivery tradeoffs. | Local simulator and UDP transport; not FlEC or QUIC. |
| Moskvitin et al., *Adaptive Forward Erasure Correction for Delay-Sensitive QUIC Connections*, [2024 draft, sections 6 and 8](https://www.ietf.org/archive/id/draft-dmoskvitin-quic-adaptive-fec-00.html) | Loss-dependent redundancy and acknowledging FEC-recovered packets as received. | Work-in-progress draft; original risk-target policy follows this selection principle, while the updated cost score is a local adaptation. |
| Iyengar and Swett, [RFC 9002, section 6.1](https://www.rfc-editor.org/rfc/rfc9002.html#section-6.1), 2021 | Receiver evidence can trigger recovery before a long retry timer. | Uses explicit block status with a reordering allowance, not QUIC's exact three-packet/time thresholds or congestion controller. |

The comparison is against the project's implementations of existing methods,
not against published numerical results from different systems or networks.

## Algorithm to describe

1. Send data within a bounded sliding window. Start with no loss observations.
2. Form candidate blocks: no parity, XOR with 2/4/8/16 originals, and 2×2, 2×3,
   or 3×3 row/column parity, limited by the window and file tail.
3. Estimate raw first-pass loss, including erased parity. For a report of `n`
   symbols, use weight `1 - 0.75^(n/16)` so a one-symbol report has less influence
   than a full block.
4. Compute independent-erasure unrepaired-block risk, including lost repairs.
   Choose the minimum score `((k + repairs) × packet serialization + risk ×
   timeout) / k`. This is a decision proxy, not a transfer-time prediction.
5. Decode single-missing XOR equations repeatedly at the receiver. Release file
   bytes to the application only in order.
6. Return block status on the impaired ACK path. Acknowledge received/repaired
   data and resend remaining originals once before their timer when possible.
   Lost reports or unsuccessful retries still use ordinary timeout recovery.
7. Verify the complete bytes and SHA-256 digest.

The original policy stays available. It selects the lowest redundancy meeting
a modeled 1% block-failure target. The update changes the decision objective and
recovery timing, while retaining the parity codes and Selective Repeat.

## Run the demonstration

From the project folder:

```powershell
.\.venv\Scripts\python.exe -m paritylab demo
```

Open `http://127.0.0.1:8770`. If an older server owns that port, stop it with Ctrl+C
in its terminal and start this command again. For a separate instance use
`--port 8771` and open that port. Reload the page after restarting.

1. Show the **Measured evaluation** table. It contains every declared condition
   and all 20 final seeds, with mean ± sample standard deviation.
2. Select **Slow link · 1 Mbps** to run its first five seeds. Show the four
   protocols and **Updated vs original adaptive**. The full 20-seed study finds
   64.5% higher goodput than original adaptive, 17.6% higher than fixed XOR, and
   79.8% higher than Selective Repeat for this condition.
3. Replay **Adaptive parity**. Seek **Next loss**, then **Next retry**. Explain
   how a receiver report can trigger a retry before its timer. Show packet
   acceptance and in-order release in the inspector.
4. Switch to **Delivery** to show useful bytes reaching the application. Use
   **Block decision** to inspect a change in protection and its cost score.
5. Show **Short delay · 5 ms** and **Random 20%** in the full table. The update
   also improves goodput over fixed XOR in those conditions. Show **Random 2%**
   as a counterexample where fixed XOR remains better.
6. Run **Real UDP transfer**. Show byte verification and three distinct process
   IDs. Its wall time is separate from the simulator's metrics.
7. Download CSV and JSON. Their recorded settings include the controller policy
   and the original-controller comparison. Keep the full-table CSV as evidence.

Live five-seed values can differ from the 20-seed table. Both are labeled with
their actual sample. Do not describe a five-seed result as the final average.

## Results to defend

The [complete result table](review-2-results.md) and saved raw runs are the source
of every percentage. All 1,440 final transfers verified. Across 11 nonclean
conditions, the geometric mean goodput ratio to original adaptive is 1.2641.
The clean channel retains its goodput with zero parity and retries.

At random 10% loss, mean goodput rises from 1.078 to 1.388 Mbps and mean completion
falls from 0.506 to 0.390 s. At 1 Mbps, parity overhead falls from 16.6% to 8.3%,
while retries rise slightly from 3.9 to 4.2; fewer retries are not the only goal.
With 5% ACK loss, retries fall from 7.4 to 4.15 and goodput rises by 33.1%.

Most improvement comes from early feedback. The cost-only candidate was weak;
the legacy-with-feedback comparison is retained to show that. No universal
ranking, statistical significance, Internet result, or new coding invention is
claimed. Same seeds do not imply identical erasure masks across schedules.
The short-file changing case finishes before its first change. Use the 256 KiB
Changing loss preset to inspect changes, without treating it as part of the
frozen 64 KiB study.

## Assessment evidence

The Review 2 materials are the interactive demo, the two plots under
`output/review-2/`, the full CSV/JSON under `output/studies/controller-cost/held-out/`,
and the screenshots under `docs/review-2-screenshots/`. Keep screenshots with
their settings and seed count visible. Assessment 9 requires the output
screenshots; upload the selected files through VTOP yourself.

The [screenshot index](review-2-screenshots/README.md) identifies each capture,
its settings, and whether it shows five simulation seeds, the full twenty-seed
study, or one real UDP transfer.

Review 3 is the final document due October 25, 2026. The current manuscript
describes earlier studies; these new results are a separate review supplement
until the final document is explicitly revised.
