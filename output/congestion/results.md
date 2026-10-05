# Competing-flow evaluation

70 shared-bottleneck runs, 140 byte-verified file transfers.

Shared finite FIFO bottleneck; AIMD model includes parity and retries in congestion window. Local emulator evaluation, not RFC-compliant TCP or Internet validation.

Jain index measured from actual in-order useful bytes on common active interval; finite files and start/tail effects remain. Same configured seed set does not imply identical masks after different packet schedules.

| Configuration | Queue packets | Aggregate goodput Mbps, mean ± sample SD | Jain fairness, mean ± sample SD | Mean queue drops |
| --- | --- | --- | --- | --- |
| aimd_equal | 8 | 1.765 ± 0.055 | 0.961 ± 0.055 | 34.2 |
| aimd_equal | 32 | 1.734 ± 0.065 | 0.957 ± 0.031 | 48.0 |
| uncontrolled_equal | 8 | 1.381 ± 0.049 | 0.815 ± 0.107 | 1768.0 |
| uncontrolled_equal | 32 | 1.697 ± 0.089 | 0.928 ± 0.116 | 512.6 |
| aimd_vs_uncontrolled | 8 | 1.549 ± 0.177 | 0.959 ± 0.049 | 742.8 |
| aimd_vs_uncontrolled | 32 | 1.586 ± 0.150 | 0.772 ± 0.176 | 141.6 |
| gbn_vs_sr | 8 | 1.172 ± 0.119 | 0.787 ± 0.078 | 32.2 |
| gbn_vs_sr | 32 | 1.348 ± 0.181 | 0.905 ± 0.081 | 48.2 |
| sr_vs_sr | 8 | 1.765 ± 0.055 | 0.961 ± 0.055 | 34.2 |
| sr_vs_sr | 32 | 1.734 ± 0.065 | 0.957 ± 0.031 | 48.0 |
| fixed_vs_sr | 8 | 1.662 ± 0.038 | 0.956 ± 0.062 | 34.4 |
| fixed_vs_sr | 32 | 1.710 ± 0.033 | 0.960 ± 0.013 | 48.2 |
| adaptive_vs_sr | 8 | 1.552 ± 0.040 | 0.952 ± 0.056 | 36.6 |
| adaptive_vs_sr | 32 | 1.662 ± 0.105 | 0.993 ± 0.005 | 47.0 |

The comparison preserves negative results. Equal AIMD settings can still obtain unequal finite-transfer shares. FEC that hides residual data loss still pays for repair packets in the congestion budget. Arbitrary Internet use remains outside the implementation scope.

![Shared bottleneck](competing-flows.png)
