# Equal-overhead codec comparison

Paired masks: four data packets, then either two or four equal-width repair packets; no retransmission. Continuous packet-index Markov channel across blocks for burst cases.

Controlled codec residual block failure at exact 50% or 100% parity payload budgets; not transport goodput or controller adaptation.

| Model | Loss | Parity budget | Code | Failed blocks / trials | Failure rate |
| --- | --- | --- | --- | --- | --- |
| bernoulli | 1% | 100% | grid-2x2 | 0 / 5000 | 0.000% |
| bernoulli | 1% | 100% | per-packet-replication | 1 / 5000 | 0.020% |
| bernoulli | 1% | 50% | pairwise-xor | 1 / 5000 | 0.020% |
| bernoulli | 1% | 50% | repeated-block-xor | 3 / 5000 | 0.060% |
| bernoulli | 5% | 100% | grid-2x2 | 2 / 5000 | 0.040% |
| bernoulli | 5% | 100% | per-packet-replication | 50 / 5000 | 1.000% |
| bernoulli | 5% | 50% | pairwise-xor | 74 / 5000 | 1.480% |
| bernoulli | 5% | 50% | repeated-block-xor | 93 / 5000 | 1.860% |
| bernoulli | 10% | 100% | grid-2x2 | 28 / 5000 | 0.560% |
| bernoulli | 10% | 100% | per-packet-replication | 203 / 5000 | 4.060% |
| bernoulli | 10% | 50% | pairwise-xor | 273 / 5000 | 5.460% |
| bernoulli | 10% | 50% | repeated-block-xor | 298 / 5000 | 5.960% |
| bernoulli | 20% | 100% | grid-2x2 | 193 / 5000 | 3.860% |
| bernoulli | 20% | 100% | per-packet-replication | 747 / 5000 | 14.940% |
| bernoulli | 20% | 50% | pairwise-xor | 962 / 5000 | 19.240% |
| bernoulli | 20% | 50% | repeated-block-xor | 941 / 5000 | 18.820% |
| gilbert-elliott | 1% | 100% | grid-2x2 | 31 / 5000 | 0.620% |
| gilbert-elliott | 1% | 100% | per-packet-replication | 27 / 5000 | 0.540% |
| gilbert-elliott | 1% | 50% | pairwise-xor | 53 / 5000 | 1.060% |
| gilbert-elliott | 1% | 50% | repeated-block-xor | 53 / 5000 | 1.060% |
| gilbert-elliott | 5% | 100% | grid-2x2 | 201 / 5000 | 4.020% |
| gilbert-elliott | 5% | 100% | per-packet-replication | 180 / 5000 | 3.600% |
| gilbert-elliott | 5% | 50% | pairwise-xor | 324 / 5000 | 6.480% |
| gilbert-elliott | 5% | 50% | repeated-block-xor | 333 / 5000 | 6.660% |
| gilbert-elliott | 10% | 100% | grid-2x2 | 380 / 5000 | 7.600% |
| gilbert-elliott | 10% | 100% | per-packet-replication | 340 / 5000 | 6.800% |
| gilbert-elliott | 10% | 50% | pairwise-xor | 573 / 5000 | 11.460% |
| gilbert-elliott | 10% | 50% | repeated-block-xor | 595 / 5000 | 11.900% |
| gilbert-elliott | 20% | 100% | grid-2x2 | 810 / 5000 | 16.200% |
| gilbert-elliott | 20% | 100% | per-packet-replication | 751 / 5000 | 15.020% |
| gilbert-elliott | 20% | 50% | pairwise-xor | 1188 / 5000 | 23.760% |
| gilbert-elliott | 20% | 50% | repeated-block-xor | 1223 / 5000 | 24.460% |

95% Wilson intervals quantify independent sampling; burst trials are correlated so their Wilson columns are descriptive and not valid confidence coverage.

The ordering is held fixed because burst correlation depends on wire order. The data-plus-parity mask is reused for both members of each pair. Neither pair establishes a universally best code or supports generalization to other block sizes.
