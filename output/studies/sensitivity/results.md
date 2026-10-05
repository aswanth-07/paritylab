# Parameter sensitivity

370 byte-verified transfers with 5 seeds per condition.

One parameter changes from independent 10%, 50ms, 5Mbps, window32, packet1024, fixed block8. Burst cases use the stated Markov mean run. Block-size sweep applies to fixed XOR only.

Small windows and high delay expose pipeline limits. A timeout shorter than the return path can add unnecessary transmissions. These are implementation measurements at the recorded file size; they do not establish an optimal configuration.

| Parameter | Value | Scheme | Goodput Mbps, mean ± sample SD | Retries, mean ± sample SD |
| --- | --- | --- | --- | --- |
| baseline | baseline | gbn | 0.360 ± 0.120 | 146.4 ± 63.7 |
| baseline | baseline | sr | 1.003 ± 0.342 | 6.2 ± 2.6 |
| baseline | baseline | fixed | 1.361 ± 0.593 | 3.6 ± 2.6 |
| baseline | baseline | adaptive | 1.104 ± 0.284 | 5.0 ± 1.6 |
| delay_ms | 0 | gbn | 0.748 ± 0.251 | 146.4 ± 63.7 |
| delay_ms | 0 | sr | 2.401 ± 0.794 | 6.2 ± 2.6 |
| delay_ms | 0 | fixed | 3.001 ± 0.940 | 3.6 ± 2.6 |
| delay_ms | 0 | adaptive | 2.622 ± 0.574 | 5.2 ± 1.5 |
| delay_ms | 25 | gbn | 0.496 ± 0.173 | 146.4 ± 63.7 |
| delay_ms | 25 | sr | 1.457 ± 0.525 | 6.2 ± 2.6 |
| delay_ms | 25 | fixed | 2.001 ± 0.921 | 3.6 ± 2.6 |
| delay_ms | 25 | adaptive | 1.595 ± 0.423 | 5.0 ± 1.6 |
| delay_ms | 100 | gbn | 0.232 ± 0.074 | 146.4 ± 63.7 |
| delay_ms | 100 | sr | 0.617 ± 0.199 | 6.2 ± 2.6 |
| delay_ms | 100 | fixed | 0.831 ± 0.345 | 3.6 ± 2.6 |
| delay_ms | 100 | adaptive | 0.683 ± 0.171 | 5.0 ± 1.6 |
| bandwidth_mbps | 1 | gbn | 0.128 ± 0.044 | 146.4 ± 63.7 |
| bandwidth_mbps | 1 | sr | 0.372 ± 0.125 | 6.2 ± 2.6 |
| bandwidth_mbps | 1 | fixed | 0.495 ± 0.194 | 3.6 ± 2.6 |
| bandwidth_mbps | 1 | adaptive | 0.420 ± 0.096 | 5.2 ± 1.5 |
| bandwidth_mbps | 2 | gbn | 0.217 ± 0.075 | 146.4 ± 63.7 |
| bandwidth_mbps | 2 | sr | 0.616 ± 0.211 | 6.2 ± 2.6 |
| bandwidth_mbps | 2 | fixed | 0.874 ± 0.383 | 3.6 ± 2.6 |
| bandwidth_mbps | 2 | adaptive | 0.714 ± 0.171 | 4.8 ± 1.8 |
| bandwidth_mbps | 10 | gbn | 0.458 ± 0.146 | 146.4 ± 63.7 |
| bandwidth_mbps | 10 | sr | 1.222 ± 0.396 | 6.2 ± 2.6 |
| bandwidth_mbps | 10 | fixed | 1.652 ± 0.694 | 3.6 ± 2.6 |
| bandwidth_mbps | 10 | adaptive | 1.353 ± 0.340 | 5.0 ± 1.6 |
| window | 8 | gbn | 0.365 ± 0.073 | 46.4 ± 20.4 |
| window | 8 | sr | 0.431 ± 0.062 | 6.2 ± 2.6 |
| window | 8 | fixed | 0.460 ± 0.092 | 3.4 ± 2.3 |
| window | 8 | adaptive | 0.498 ± 0.034 | 2.2 ± 0.4 |
| window | 16 | gbn | 0.348 ± 0.082 | 120.6 ± 38.5 |
| window | 16 | sr | 0.599 ± 0.133 | 6.2 ± 2.6 |
| window | 16 | fixed | 0.755 ± 0.287 | 3.4 ± 2.3 |
| window | 16 | adaptive | 0.651 ± 0.066 | 4.2 ± 1.1 |
| window | 64 | gbn | 0.256 ± 0.048 | 252.4 ± 95.6 |
| window | 64 | sr | 1.110 ± 0.320 | 6.2 ± 2.6 |
| window | 64 | fixed | 1.726 ± 0.763 | 3.4 ± 2.4 |
| window | 64 | adaptive | 1.110 ± 0.320 | 6.2 ± 2.6 |
| timeout_ms | 70 | gbn | 0.887 ± 0.265 | 188.8 ± 61.7 |
| timeout_ms | 70 | sr | 1.413 ± 0.320 | 71.2 ± 3.5 |
| timeout_ms | 70 | fixed | 1.730 ± 0.299 | 69.0 ± 4.5 |
| timeout_ms | 70 | adaptive | 1.596 ± 0.274 | 69.4 ± 2.7 |
| timeout_ms | 180 | gbn | 0.371 ± 0.123 | 146.4 ± 63.7 |
| timeout_ms | 180 | sr | 1.025 ± 0.345 | 6.2 ± 2.6 |
| timeout_ms | 180 | fixed | 1.379 ± 0.585 | 3.6 ± 2.6 |
| timeout_ms | 180 | adaptive | 1.126 ± 0.285 | 5.0 ± 1.6 |
| timeout_ms | 500 | gbn | 0.149 ± 0.056 | 146.4 ± 63.7 |
| timeout_ms | 500 | sr | 0.511 ± 0.226 | 6.2 ± 2.6 |
| timeout_ms | 500 | fixed | 0.937 ± 0.795 | 3.6 ± 2.6 |
| timeout_ms | 500 | adaptive | 0.588 ± 0.200 | 5.0 ± 1.6 |
| packet_size | 512 | gbn | 0.250 ± 0.034 | 356.0 ± 80.9 |
| packet_size | 512 | sr | 0.524 ± 0.114 | 15.6 ± 3.6 |
| packet_size | 512 | fixed | 0.737 ± 0.146 | 9.6 ± 3.9 |
| packet_size | 512 | adaptive | 0.691 ± 0.062 | 7.6 ± 2.2 |
| packet_size | 1200 | gbn | 0.564 ± 0.297 | 109.2 ± 74.6 |
| packet_size | 1200 | sr | 1.060 ± 0.238 | 5.2 ± 1.8 |
| packet_size | 1200 | fixed | 1.516 ± 0.514 | 2.8 ± 1.8 |
| packet_size | 1200 | adaptive | 1.117 ± 0.216 | 4.8 ± 1.5 |
| fixed_k | 4 | fixed | 1.455 ± 0.539 | 2.0 ± 1.9 |
| fixed_k | 16 | fixed | 1.154 ± 0.255 | 5.0 ± 2.2 |
| burst_mean_packets | 2 | gbn | 0.928 ± 0.405 | 59.0 ± 50.4 |
| burst_mean_packets | 2 | sr | 1.295 ± 0.229 | 4.2 ± 4.0 |
| burst_mean_packets | 2 | fixed | 1.619 ± 0.677 | 2.6 ± 3.2 |
| burst_mean_packets | 2 | adaptive | 1.239 ± 0.336 | 4.6 ± 4.8 |
| burst_mean_packets | 5 | gbn | 1.684 ± 0.827 | 21.2 ± 20.1 |
| burst_mean_packets | 5 | sr | 1.846 ± 0.639 | 4.8 ± 4.8 |
| burst_mean_packets | 5 | fixed | 1.703 ± 0.589 | 4.0 ± 4.0 |
| burst_mean_packets | 5 | adaptive | 1.816 ± 0.670 | 4.8 ± 4.8 |
| burst_mean_packets | 10 | gbn | 1.927 ± 0.873 | 13.8 ± 20.1 |
| burst_mean_packets | 10 | sr | 2.072 ± 0.644 | 3.6 ± 5.4 |
| burst_mean_packets | 10 | fixed | 1.942 ± 0.557 | 3.2 ± 4.9 |
| burst_mean_packets | 10 | adaptive | 2.066 ± 0.653 | 3.6 ± 5.4 |

![Sensitivity](sensitivity.png)
