# Controller cost comparison

Declared before running the new controller comparison. This is an engineering
evaluation of a project-specific heuristic, not a claim of algorithmic novelty.

The released controller selects the cheapest parity meeting a 1% modeled block
failure target, or the lowest-risk protection if that target is infeasible.
The candidate minimizes `(serialized block time + residual block risk × retry
timeout) / original packets`. It estimates loss from raw first-pass outcomes
and scales the EWMA update weight to the number of reported symbols:
`1 - (1 - 0.25)^(symbols / 16)`. Initial estimated loss is zero in both policies.

Primary comparison: simulated goodput against the released controller. Secondary
comparisons: selective repeat and fixed XOR-8. All use the same 64 KiB payload,
1024-byte packets, window 32 and existing timeout rule. No timeout is tuned for
the candidate. Primary goodput is original bytes divided by receiver completion
time; sender completion, retry count, parity and application delay are retained.

Conditions, with 50 ms one-way delay and 5 Mbps unless stated:

| Condition | Loss / change |
| --- | --- |
| Clean | 0% independent |
| Random 2% | 2% independent |
| Random 5% | 5% independent |
| Random 10% | 10% independent |
| Random 20% | 20% independent |
| Slow link | 10%, 1 Mbps |
| Fast link | 10%, 20 Mbps |
| Short delay | 10%, 5 ms |
| Long delay | 10%, 150 ms |
| Burst | 10% stationary erasures, mean bad run 5 packets |
| Changing | 0%; 10% at 0.25 s; 2% at 0.75 s; 10% at 1.2 s |
| ACK loss | 10% forward, 5% ACK loss |

Revision 2, after development-1 and before development-2 or any held-out run:
cost selection alone missed the adoption threshold (ratio 1.0437). The revised
candidate also uses block status feedback to acknowledge received/repaired data
and retry remaining missing originals immediately, once per original. Timer
fallback remains. Its feedback traverses the impaired reverse link. Add two
ablations: cost selection without early feedback, and legacy selection with
early feedback. This separates recovery scheduling from parity selection.

Development seeds are 0–4. Final seeds are 100–119 and must be used once after
freezing the candidate. Final evaluation: 12 × 20 × 6 = 1440 transfers. Complete
all runs; include failed or corrupted transfers at zero goodput, report them
explicitly, and do not exclude seeds. Retain every development candidate.

Adoption threshold: all bytes and application hashes verify; clean mean goodput
degrades by no more than 2%; the geometric mean of condition-level ratios of mean
goodput to the released controller across the 11 nonclean conditions is at least
1.05. Report all conditions, sample standard deviations and regressions. These
thresholds select a demo option; they do not constitute a statistical significance
test. No method changes after final evaluation.

Limits: the block cost ignores overlap, multiple retry rounds and detailed window
blocking. Independent decoder risk can be wrong for burst/changing loss. Same
seeds across methods do not produce identical erasure masks because schedules
differ. These are finite-file simulator measurements; do not imply Internet gains
or faster real UDP transfers without measuring them separately. Existing paper
results and source archives remain unchanged.
