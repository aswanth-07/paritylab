# Literature positioning, updated October 7, 2026

The current bibliography has fourteen references from 2020–2026: twelve read in full and two read at abstract level. The [October 7 review](../docs/recent-literature.md) records the seven new Crossref/arXiv framings, primary checks, four additions, status corrections and the decision to preserve the frozen demo method. Historical measurements and paper results are unchanged.

## October 5 search and positioning

The contribution is a reproducible empirical artifact connecting small-code decoder risk, estimated feasibility, and finite-transfer observations. Adaptive FEC, XOR/grid parity, causal coding with feedback, and the congestion/redundancy tradeoff are established prior work. No priority or exhaustive novelty assertion is used in the manuscript.

The current project requested references dated 2020-2026. All ten sources cited at that stage meet that interval. Earlier author manuscripts were read where they correspond to a cited publication inside the interval; this is recorded rather than shifting their original preprint date. FlEC is cited as its final 2023 journal article, with its 2022 author manuscript identified. Draft and preprint status are explicit.

The structured search used seven framings:

| Framing | Query | Sources | Assessment |
| --- | --- | --- | --- |
| Functional | adaptive forward erasure correction burst loss reliability | OpenAlex, arXiv | Reached FlEC, AC-RLNC and related systems; broad query also returned irrelevant domains |
| Structural | two dimensional parity residual packet loss | OpenAlex, Crossref | Reached the 2022 2-D parity analysis; OpenAlex rate-limited |
| Causal | adaptive causal network coding feedback | OpenAlex, arXiv | Returned irrelevant causal-inference papers; excluded. AC-RLNC was reached independently by the functional query |
| Problem | forward error correction burst loss calibration | Crossref, arXiv | Reached WebRTC/sliding-window guidance and unrelated PHY/quantum work |
| Effect | forward error correction throughput redundancy overhead | Crossref, arXiv | Established relevant tradeoff vocabulary; many retrieved results concern physical-layer coding |
| Inverse | forward error correction performance degradation congestion | Crossref, arXiv | Reached RFC 9265; supports capacity and congestion positioning |
| Domain transfer | packet erasure coding reliability model uncertainty | Crossref, arXiv | Reached interplanetary and streaming-code work; objectives differ from this artifact |

At the October 5 stage, primary full-text reading covered ten cited sources, with locations in `references.json`. The references in FlEC, AC-RLNC, the 2-D parity manuscript, and the 2026 MPQUIC preprint supplied further vocabulary and adjacent works. Separate web checks examined 2025-2026 adaptive coding and recent preprints, including LTP reinforcement-learning FEC and practical 5G network coding. They were not used as measured performance baselines. There is no standard external benchmark used by this local artifact.

Automated backward, forward and related-work graph queries from three close publications returned HTTP 429. Those queries are failed coverage attempts, not empty-literature results. Full forward/backward/co-citation coverage and two saturation cycles were not established. This limit remains on the research record. The search supports fair positioning against the read sources; it cannot support “first,” “no prior work,” or an exhaustive field-wide gap. No such wording is in the manuscript.

| Closest work | What it establishes | Difference of the present study |
| --- | --- | --- |
| Golaghazadeh et al., 2022 | Residual packet-loss analysis, bounds, deadlocks and burst considerations for Pro-MPEG 2-D parity | Exact small-code unrepaired-block endpoint, conditional starts/partial tails, and connection to fitted-policy diagnostics |
| Cohen et al., 2020 | Adaptive causal random linear coding with feedback and throughput/in-order-delay analysis | Inspectable XOR/grid calibration and failure characterization; no AC-RLNC performance comparison claimed |
| Michel et al., 2023 | Application-tailored reliability and protection patterns within QUIC | A local artifact separates decoder calibration, estimate coverage and finite-file metrics, while preserving unfavorable parity results |
| RFC 9265, 2022 | Coding placement and congestion interaction | Concrete accounting within a disclosed teaching FIFO model; no claim to discover the principle |
| Tsubaki et al., 2026 preprint | Scheduler-agnostic expected-loss RS protection and cellular field evaluation | Exact small-code risks and synthetic model tests; no multipath or cellular deployment claim |

These differences justify an empirical/artifact paper, with modest method novelty. They do not establish that the integration itself is unprecedented. A selective networking venue would likely require current coding baselines, external traces and a prospectively evaluated controller contribution.
