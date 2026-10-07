# Recent literature and implementation

Checked October 7, 2026. All proposal, report and manuscript references fall within 2020–2026. Recent work is listed first; the earlier parity analysis, FlEC and transport guidance remain the implementation basis. This is a literature-based lab demonstration, with no new coding algorithm or historical-priority claim.

## Recent sources

| Source | Status and access | Connection and implementation boundary |
| --- | --- | --- |
| Tsubaki et al., *Scheduler-Agnostic Adaptive-FEC for MPQUIC: Field Evaluation over Commercial Cellular Paths*, [2026](https://arxiv.org/abs/2607.14482) | arXiv version 1, July 16. Full text read, including controller, evaluation and references. Authors report IEEE VTC2026-Fall acceptance; no published proceedings DOI verified. | Expected-loss adaptation is current context. Its Reed-Solomon codec, multipath QUIC datagrams and cellular field setup differ from XOR/grid peeling, one path and reliable file delivery here. |
| Wang et al., *Packet Loss Modeling and Forward Erasure Correction for LEO Satellite Networks*, [2026](https://doi.org/10.1109/TCOMM.2026.3658383) | Journal article, IEEE Transactions on Communications 74, 3999–4013. Crossref metadata and [author abstract, entry 21](https://onlineacademiccommunity.uvic.ca/starlink/) checked; full text not accessed. | The abstract describes Starlink measurements and a fitted Markovian arrival process. This supports a model limit: independent/binary Markov loss is a simplification. No satellite traces or fitted arrival process are implemented. |
| Zheng and Liu, *FEC Extension for QUIC*, [March 2026 revision 02](https://www.ietf.org/archive/id/draft-zheng-quic-fec-extension-02.html) | Full text read. [IETF status](https://datatracker.ietf.org/doc/draft-zheng-quic-fec-extension/): individual draft expired September 17, 2026; not endorsed and not a standard. | Optional Repair ACK reports reconstructed data without changing RTT/congestion state. It leaves code and redundancy choice unspecified. Local block status also identifies unresolved originals for retry; QUIC Repair ACK is not implemented. |
| Eghbal and Lu, *Lower-Latency Screen Updates over QUIC with Forward Error Correction*, [2025](https://doi.org/10.3390/fi17070297) | Journal article, Future Internet 17(7), 297, published June 30. [Deposited abstract/metadata](https://api.crossref.org/works/10.3390/fi17070297) read. Publisher full-text requests returned HTTP 403/429. | Application-delivery context only: partially ordered screen rectangles differ from strictly ordered file bytes. No detailed method reproduction or numerical comparison claimed. |
| Chen et al., *Reliable Transmission of LTP Using Reinforcement Learning-Based Adaptive FEC*, [2025](https://arxiv.org/abs/2506.22470) | arXiv version 1, June 19. [Full text](https://arxiv.org/html/2506.22470v1) read, especially Sections II-C/III, algorithm and evaluation. No journal publication asserted. | Matrix feedback and report-size-aware loss estimation are relevant. Its LDPC/ECLSA stack and trained policy differ from the local exponential weight and cost rule. Neither LDPC nor reinforcement learning is implemented. |

The proposal/report now cite [FlEC's 2023 journal publication](https://doi.org/10.1109/TNET.2022.3195611), with its 2022 author manuscript identified as the full-text source. A DOI containing an earlier year does not change the publication year. The [2024 adaptive-FEC draft](https://www.ietf.org/archive/id/draft-dmoskvitin-quic-adaptive-fec-00.html) remains a versioned design reference, labeled expired November 7, 2024.

## Algorithm and evidence

Replay compares Go-Back-N, Selective Repeat, fixed XOR and adaptive parity. Adaptive parity offers the original risk-target policy and the updated cost-plus-feedback method. The update chooses among no parity, XOR and row/column parity; weighs serialization against modeled retry cost; weights raw-loss reports by symbol count; and retries unresolved originals when receiver block status arrives. Timers remain a fallback. The cost objective and exponential report weight are local adaptations of established error-control principles.

The final study stays frozen: 1,440 verified transfers, twelve conditions, twenty unused seeds per condition, and six methods including component comparisons. The geometric mean ratio of condition-mean goodput across eleven nonclean conditions is 1.264 (+26.4%) against original adaptive. Fixed XOR wins several conditions. These are simulator measurements, not those papers' results or Internet/UDP speed claims. See the [full results](review-2-results.md) and [comparison contract](controller-cost-contract.md). This reference update changes no algorithm, trial, parameter or measurement.

## Replay decision

The assessment requires an implemented literature-based method with improved metrics; the validated update provides both. A fair additional comparator would need its own codec, transport behavior, controls and held-out evaluation. Reed-Solomon with multipath scheduling, QUIC frames, trained LDPC/LTP adaptation, partial-order screen delivery, and trace-fitted satellite models are substantial separate implementations. Adding their names to the XOR replay would misrepresent them. The final lab release therefore retains its validated methods.

## Search record

The October 7 update ran seven scholarly framings with recent-year filtering, then web and exact-title primary checks. This adds to the [earlier manuscript search](../paper/literature-search.md).

| Framing | Query | Indexes | Assessment |
| --- | --- | --- | --- |
| Functional | adaptive forward erasure correction QUIC packet loss | Crossref, arXiv | Reached 2025 QUIC FEC and 2024 Polar-QUIC; transport relevance checked separately. |
| Structural | packet erasure parity XOR interleaving forward error correction | Crossref, arXiv | Quantum/physical-layer results excluded; no validated drop-in XOR/ARQ comparator established. |
| Causal | feedback adaptive coding retransmission latency throughput | Crossref, arXiv | Reached batched recoding and link-layer work with different architectures. |
| Problem | packet loss burst low latency forward error correction survey | Crossref, arXiv | Reached screen-delivery and SmartNIC work; no new relevant survey verified. |
| Effect | QUIC forward error correction latency goodput overhead | Crossref, arXiv | Repeated application-specific work with different workloads/endpoints. |
| Inverse | forward error correction congestion overhead performance degradation transport | Crossref | Low precision: optical, circuit and quantum work excluded; RFC 9265 remains verified transport guidance. |
| Domain transfer | LTP adaptive forward error correction feedback | Crossref, arXiv | Broad results had low precision; an independent exact-title web check reached Chen's 2025 preprint. |

Web searches covered 2025–2026 adaptive FEC/QUIC, burst coding, LTP, SmartFEC and satellite loss modeling. Primary checks used arXiv, IETF Datatracker/archive, Crossref, publisher pages and author-hosted abstracts. The read 2026 MPQUIC paper's references were inspected manually.

Automatic forward, backward and neighbor citation queries failed with OpenAlex HTTP 429. This is failed coverage, not an empty citation set. Publisher access was limited for the two abstract-level journal sources. Coverage is bounded and not exhaustive; saturation was not established.

## Exclusions and reproducibility

- SmartFEC, DOI 10.1007/s11432-025-5014-9: primary metadata/full-text requests blocked; secondary listings were insufficient for a method claim.
- LSTM-based adaptive polar coding in QUIC, DOI 10.1109/TCCN.2025.3616176: metadata verified, but primary abstract/full text not read; no method claim based on it.
- Polar-QUIC, QUIC-LR and multi-phase batched recoding: different coding or transport architecture; no numerical baseline imported.
- Physical-layer, quantum and circuit error correction: excluded from packet-transport positioning.

Reading locations and status are recorded in [the proposal audit](reference-audit.json) and [the paper records](../paper/references.json). Run `python scripts/audit_references.py` to check identities, years, links and citation consistency. This local check does not re-fetch sources or certify novelty.
