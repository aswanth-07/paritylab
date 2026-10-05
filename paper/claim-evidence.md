# Claim-to-evidence matrix

These are descriptive statements about the configured artifact. Supporting machine checks are distinct from final author review.

| Claim | Evidence and locator | Statistical scope | Excluded interpretation |
| --- | --- | --- | --- |
| Exact decoder predictions agree with sampled byte decoding | Calibration raw masks, seed counts, summary; Table 3 and Figures 2-3 | 153 cases x 20,000 independently initialized blocks; maximum error 0.00914533; simultaneous 99% tolerance 0.01606919; five individual Wilson misses | General hidden-state channel guarantee or online-policy validation |
| Estimated feasibility can fail | `output/calibration/policy-validation.csv`; Table 4 | 225 policy decisions from 75 shared histories, 1,000 fresh test blocks per decision; descriptive per-policy/model counts | 225 independent training datasets or simultaneous policy coverage |
| The envelope's bound is conditional | Equation 4, `fec.py`, policy rows | Every represented parameter in the supplied rectangle is algebraically bounded; the rectangle need not include truth | Approximate confidence intervals imply certain parameter inclusion |
| Burst-policy failure counts largely reflect abstention | Table 4 and active-envelope/fallback rows | 29/30 Markov choices infeasible; the sole feasible fallback fails the diagnostic. All 29 active envelopes are conservative in these saved cases, including the one rectangle that misses truth | Burst controller meets the target in 29 cases or proves goodput superiority |
| Lower retries need not mean higher goodput | 260 baseline records, Table 2 and Figure 1 | Five seeds per scheme/condition; mean +/- sample SD. At 10% IID, adaptive retries 7.6 +/- 2.2 vs fixed 9.6 +/- 3.9, goodput 1.154 +/- 0.102 vs 1.247 +/- 0.279 Mbps | Paired-mask causal comparison, resolved significance, or uniform ranking |
| Equal-budget observed ordering reverses | Equal-budget raw paired masks; Table 5 and Figure 4 | Four data plus four repair symbols, five 1,000-block traces/group. Grid minus replication at 10% IID is -3.50 +/- 0.80 pp; under continuous Markov bursts it is +0.80 +/- 0.29 pp | Generic superiority of a code family or independence of correlated burst blocks |
| Repairs have a shared-capacity cost | Shared-FIFO runs and release timestamps; Table 6 and Figure 5 | 70 two-flow runs, with duplicate SR/AIMD specifications explicitly identified; mean +/- sample SD | Deployed TCP/QUIC compatibility or equilibrium Internet fairness |
| Full protocol executes and verifies bytes on loopback | 36 socket receipts, output files and process IDs; Table 7; correctness tests | Three seeds per scenario/scheme; impaired control/data, exact output/digest checks | Deterministic wall time, authenticated peers, or an Internet field trial |

The independent measurement audit validates raw counts/outcomes and source fingerprints. The paper reconstruction additionally checks all 80,000 shared codec masks, derives paired seed differences, and verifies shared training-history identity across policies. These checks do not substitute for author or external peer review.
