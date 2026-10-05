# Manuscript review and readiness

Reviewed on 5 October 2026. These are structured internal reviews by the drafting assistant, not reports from external peers. The judgments address the empirical contribution actually claimed. No venue is selected, so no journal quartile, scope verdict, acceptance probability, or official submission clearance is assigned.

Scores use an internal five-point scale: 1 = technically unsound as stated; 2 = substantial evidence or significance limitations; 3 = defensible within a narrow empirical scope; 4 = strong evidence and a clear advance; 5 = exceptional advance with broad validation. Scores are assessments, not measurements.

## Desk editor

**Verdict: author-review copy complete; formal submission deferred.** The title and abstract identify the empirical study, include the principal mixed results, and avoid a new-code claim. Methods, uncertainty, limitations, provenance, access, and AI assistance are disclosed. Author names and affiliation follow the supplied order.

Venue fit and length cannot be checked against recent issues or an official template without a venue. A Aswanth Raj confirmed no funding and described Dr. Ranjithkumar S as mentor; the manuscript records mentorship and supervision. Remaining contribution details, corresponding-author contact, conflicts, any institutional ethics requirement, and both authors' approval remain unconfirmed. Missing information has not been converted into declarations of no conflict or approval.

## R1: novelty and positioning

**Score: 3/5.** The contribution is a reproducible empirical chain from an explicit peeling decoder to exact risk, fitted-policy diagnostics, and finite-transfer outcomes. The most useful negative findings are infeasibility versus target success, retry/goodput divergence, and an ordering reversal under matched masks.

The underlying codes, exact enumeration, adaptation principle, and congestion tradeoff have substantial prior art. The paper acknowledges the closest 2-D parity analysis, AC-RLNC, FlEC, FEC standards, and contemporary adaptive QUIC work. The distinction is the recorded cross-layer experiment and inspectable evidence, rather than historical priority for a coding mechanism.

Searches were run and close results were examined. Automated citation-graph queries were rate-limited, and the 2020-2026 bibliography is a requested contemporary scope. Neither supports exhaustive novelty. This limits how strongly the contribution can be sold; it does not invalidate the reported results.

## R2: methodology and evidence

**Score: 3/5.** The manuscript distinguishes independently initialized calibration draws, shared training histories, independent test blocks, seed-level paired burst traces, and finite-file transport runs. The simultaneous calibration check is separate from individual Wilson intervals. Sample SD is labeled and is not presented as a confidence interval.

Three reporting defects were corrected during review:

1. The 225 policy decisions arise from 75 histories reused across three policies; they are not 225 independent training datasets.
2. The burst policy declares 29 of 30 Markov choices infeasible. Its sole feasible independent fallback fails the diagnostic. Low violation count cannot be interpreted as 29 successes.
3. Simulator descriptors are idealized, while feedback is serialized in reverse. Legacy feedback counts source outcomes; optional ordered feedback also includes repairs and resets adjacency between blocks. The separate socket evaluation impairs every message type.

The remaining limitations are study-design boundaries: all framing is retrospective, no reporting set is held out, transport masks are not paired, and there are five transport seeds or three socket seeds per group. Optional policy risk checks are not end-to-end goodput comparisons. No calibrated family-wise interpretation is assigned to the policy diagnostics. These limitations prevent a general superiority claim and are preserved in the text.

## R3: significance and practical scope

**Score: 2/5.** The artifact is useful for teaching and reproducible small-code experiments, including negative findings that a favorable single result could hide. Raw masks, byte checks, common-interval useful release, and impaired-control socket runs make the scope inspectable.

Deployment significance is limited by synthetic packet-index loss, fixed source-before-repair ordering, small blocks/files, loopback execution, and a teaching congestion controller. There is no measured comparison against a deployed QUIC stack, FlEC, AC-RLNC, or Reed-Solomon under a common tuning budget. External network traces and a prospective objective-specific study would be needed to claim practical superiority. Published numbers from those systems are not reused as if they were comparable baselines.

## Meta-review

**Score: 3/5; disposition: complete technical manuscript for author review.** The reported descriptive findings survive the internal review after the corrections above. The novelty is modest and empirical. The paper should be assessed as a reproducibility and evaluation study, rather than as a new coding algorithm.

Numeric reconstruction checks all nine tables and five displays against saved records. The audit independently recalculates selected prose statistics, verifies source/artifact hashes and paired masks, checks citations and BibTeX years, and inspects the exported PDF. All pages were rendered and visually inspected; table headers, captions, graphs, mathematical expressions, and appendix breaks were reviewed. The local two-pass compilation has no errors, overfull boxes, unresolved citations, or LaTeX warnings. The native editor compiler failed before source parsing because of a platform-directory error; the PDF was exported with the existing local MiKTeX installation.

The reproducibility receipt is in [verification.json](verification.json). It checks technical consistency and does not certify literature saturation, human approval, external review, or deployment validity.

## Actions before submission

- Both authors read and approve the final text, citations, findings, attribution, and AI disclosure.
- Confirm remaining contribution details, corresponding-author email, conflicts, and applicable ethics/restriction statements.
- Choose a venue and apply its current official template, length, anonymity, reporting, AI-assistance and supplementary-artifact requirements.
- For a venue requiring a stronger method or systems advance, run a separately designed prospective study with comparable stronger baselines and external traces; do not relabel this study as that evidence.

The manuscript has not been submitted to a venue or posted as a preprint.
