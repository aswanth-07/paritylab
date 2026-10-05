# Block risk calibration

The byte decoder processed 3,060,000 blocks across 153 registered conditions and 5 seeds per condition. It produced no incorrect recovered bytes.

Loss masks include erased data and repair symbols. Full and partial blocks use the exact repair list from the byte encoder. A failure means that the first data-plus-repair transmission leaves at least one original packet missing before retransmission.

Independent predictions use the independent erasure formula. Burst predictions enumerate the same failing patterns with their binary Markov sequence probabilities. Good receives every symbol; bad erases every symbol. Each trial independently samples either a stationary starting state or the next state conditional on an explicitly received or lost preceding symbol. These conditional trials do not treat the stationary loss fraction as the next-symbol loss probability.

All predictions inside the simultaneous 99% sampling-error bound: **True**. Maximum absolute error: 0.00915. 5 point predictions lie outside their individual 95% Wilson intervals; individual intervals are approximate and a collection is expected to have misses.

Applying an independent prediction to stationary burst conditions gives a maximum absolute error of 0.18469; the maximum rises to 0.63695 when it also ignores a specified preceding outcome. This demonstrates why an independent risk target cannot be read as a burst-loss guarantee.

| Model | Protection | Actual size | Starting condition | Prediction | Measured failure | 95% interval |
| --- | --- | --- | --- | --- | --- | --- |
| independent | xor-8 | 8 | stationary | 0.2252 | 0.2251 | [0.2194, 0.2310] |
| independent | grid-3x3 | 9 | stationary | 0.0114 | 0.0113 | [0.0099, 0.0129] |
| independent | grid-3x3 | 5 | stationary | 0.0056 | 0.0057 | [0.0048, 0.0069] |
| binary_markov | xor-8 | 8 | stationary | 0.1894 | 0.1913 | [0.1859, 0.1968] |
| binary_markov | grid-3x3 | 9 | stationary | 0.1025 | 0.1013 | [0.0972, 0.1056] |
| binary_markov | grid-3x3 | 5 | stationary | 0.0748 | 0.0747 | [0.0712, 0.0785] |
| binary_markov | xor-8 | 8 | after received | 0.1342 | 0.1339 | [0.1293, 0.1387] |
| binary_markov | grid-3x3 | 9 | after received | 0.0701 | 0.0698 | [0.0664, 0.0735] |
| binary_markov | grid-3x3 | 5 | after received | 0.0426 | 0.0425 | [0.0397, 0.0453] |
| binary_markov | xor-8 | 8 | after lost | 0.6870 | 0.6907 | [0.6843, 0.6971] |
| binary_markov | grid-3x3 | 9 | after lost | 0.3939 | 0.3932 | [0.3865, 0.4000] |
| binary_markov | grid-3x3 | 5 | after lost | 0.3648 | 0.3658 | [0.3591, 0.3725] |

## Estimated policy checks

The optional uncertainty policy uses the upper end of a Wilson interval from complete recent raw-loss batches. The burst policy uses adjacent raw loss outcomes to estimate good-to-bad and bad-to-good transition rates. It adds approximate, Bonferroni-adjusted transition intervals and sums each failing pattern's maximum probability over that parameter rectangle. That envelope bounds modeled risk only if the rectangle and stationary binary Markov assumptions are correct. It may be too conservative to meet the target.

The legacy policy keeps its original smoothed point estimate and choices. The new policies are explicit options. Aggregate lost/transmitted feedback provides no ordering, so burst mode falls back to the independent uncertainty policy until at least 16 adjacent transitions and both departure states have been observed. Omitted forward packets break adjacency. Reports use raw first-attempt erasures before repair, rather than residual losses after repair.

Training checks use histories of 64, 512 and 4096 raw outcomes, all three policies, independent and binary Markov models, and a model-mismatch challenge with a repeated 90 received / 10 erased sequence. Test blocks are new independent draws from the configured model, or independent random starting offsets for the fixed-run challenge. `policy-validation.csv` includes every training sequence as a hexadecimal bit mask, transition counts, chosen protection, predicted risk and measured failures.

| Data model | Policy | Cases | Predictions below true modeled risk | Target claimed but measured lower interval above 1% |
| --- | --- | --- | --- | --- |
| independent | legacy | 30 | 13 | 2 |
| independent | uncertainty | 30 | 0 | 0 |
| independent | burst | 30 | 0 | 0 |
| binary_markov | legacy | 30 | 28 | 11 |
| binary_markov | uncertainty | 30 | 20 | 7 |
| binary_markov | burst | 30 | 1 | 1 |
| fixed_runs | legacy | 15 | not defined | 13 |
| fixed_runs | uncertainty | 15 | not defined | 12 |
| fixed_runs | burst | 15 | not defined | 1 |

For fitted burst cases with an active Markov envelope, 1/29 estimated transition rectangles excluded the true parameters. Among rectangles that included them, 0 risk envelopes fell below the exact stationary risk. 1 burst-policy cases lacked usable transitions and used the independent fallback; a fallback does not bound burst risk. These counts are finite checks, not a coverage proof.

Fixed-run results expose a first-order model's limits. Alternating-state or deterministic-duration bursts, abrupt changes, missing feedback and hidden-state emission processes can invalidate the estimates. Neither an estimated target nor a confidence label establishes a bound for those processes. A sender still uses retransmission and byte verification.

## Reproduce

```powershell
python -m paritylab.calibration --output output/calibration --seeds 5 --trials-per-seed 4000
```

The manifest stores source and raw-data hashes, seed rules, sample counts and model limits. `raw-trials.csv.gz` stores every loss mask and byte-decoder outcome; `seed-counts.csv` stores seed totals; `summary.csv` stores full predictions and intervals. The default library needs no third-party dependencies. Add the plots extra for the calibration figure.

![Predicted and measured block failure](calibration.png)
