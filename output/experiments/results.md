# Prototype experiment results

260 completed transfers across 5 seeds. Every completed output was checked byte for byte.

The sweep/burst link uses 5 Mbps bandwidth, 50 ms one-way delay, 1024-byte symbols, and a 32-packet window. Values are means +/- sample standard deviations across seeds.

| Scenario | Loss % | Scheme | Goodput Mbps | Retransmissions | Parity bytes / file bytes |
| --- | --- | --- | --- | --- | --- |
| sweep | 0 | gbn | 2.559 +/- 0.000 | 0.0 +/- 0.0 | 0.000 +/- 0.000 |
| sweep | 0 | sr | 2.559 +/- 0.000 | 0.0 +/- 0.0 | 0.000 +/- 0.000 |
| sweep | 0 | fixed | 2.327 +/- 0.000 | 0.0 +/- 0.0 | 0.125 +/- 0.000 |
| sweep | 0 | adaptive | 2.559 +/- 0.000 | 0.0 +/- 0.0 | 0.000 +/- 0.000 |
| sweep | 10 | gbn | 0.388 +/- 0.053 | 356.0 +/- 80.9 | 0.000 +/- 0.000 |
| sweep | 10 | sr | 0.874 +/- 0.202 | 15.6 +/- 3.6 | 0.000 +/- 0.000 |
| sweep | 10 | fixed | 1.247 +/- 0.279 | 9.6 +/- 3.9 | 0.125 +/- 0.000 |
| sweep | 10 | adaptive | 1.154 +/- 0.102 | 7.6 +/- 2.2 | 0.344 +/- 0.178 |
| sweep | 20 | gbn | 0.185 +/- 0.039 | 831.8 +/- 163.6 | 0.000 +/- 0.000 |
| sweep | 20 | sr | 0.675 +/- 0.043 | 31.4 +/- 4.6 | 0.000 +/- 0.000 |
| sweep | 20 | fixed | 0.731 +/- 0.076 | 23.6 +/- 5.9 | 0.125 +/- 0.000 |
| sweep | 20 | adaptive | 1.038 +/- 0.323 | 11.0 +/- 3.1 | 0.606 +/- 0.124 |
| burst | 10 | gbn | 1.124 +/- 0.446 | 83.8 +/- 67.3 | 0.000 +/- 0.000 |
| burst | 10 | sr | 1.479 +/- 0.317 | 10.6 +/- 6.4 | 0.000 +/- 0.000 |
| burst | 10 | fixed | 1.465 +/- 0.244 | 8.4 +/- 4.9 | 0.125 +/- 0.000 |
| burst | 10 | adaptive | 1.443 +/- 0.312 | 9.6 +/- 4.9 | 0.106 +/- 0.161 |
| changing | changes | gbn | 0.614 +/- 0.088 | 907.6 +/- 195.5 | 0.000 +/- 0.000 |
| changing | changes | sr | 1.210 +/- 0.171 | 32.4 +/- 11.1 | 0.000 +/- 0.000 |
| changing | changes | fixed | 1.602 +/- 0.141 | 16.6 +/- 6.1 | 0.125 +/- 0.000 |
| changing | changes | adaptive | 1.556 +/- 0.087 | 13.6 +/- 3.5 | 0.318 +/- 0.045 |

Adaptive protection does not improve every condition. Its independent-loss risk model is not calibrated for burst loss. Fixed parity can outperform the adaptive risk-target policy because that policy minimizes parity cost subject to modeled block risk rather than directly maximizing goodput.

The uncertainty shown is sample standard deviation, not a confidence interval. The same seed set is used for every scheme; different transmission schedules consume different random draws. These measurements do not establish congestion fairness or Internet performance.

![Loss sweep](loss-sweep.png)

![Packet recovery delay CDF](delivery-cdf.png)

![Controller timeline](controller-timeline.png)
