# EOR Corpus Compiler

Deterministic, provenance-bound compiler pipeline that transforms the existing EOR PersonalCorpus into staged semantic memory without granting extraction models canonical write authority.

This workstream is the **K Track**. The C Track is reserved for Persistent Controller Closure.

## Current implementation

- **K00 — Corpus IR v0**: typed atomic candidate assertions, exact evidence spans, temporal anchors, entity mentions, model lineage, content-derived identities.
- **K01 — Extraction compiler v0**: backend-neutral extraction boundary with deterministic input/build/output identities and post-extraction provenance validation. The v1 extraction contract explicitly separates source-occurrence time (`CorpusChunk.occurred_at`) from asserted/effective time (`CandidateAssertion.temporal`).
- **K02 — Candidate validator / quarantine v0**: independently validates evidence containment and quarantines provenance-invalid candidates.
- **K03 — Entity mention compiler v0**: builds deterministic mention indexes without prematurely merging entity identities.
- **K04 — Global entity resolution v0**: stable entity identities, verified-alias reuse, redirects, keep-distinct constraints, auditable decision journal/retractions, indexed fuzzy candidate generation, and soft multi-model proposals that never silently merge identities.
- **K05 — Semantic normalization / exact dedup v0**: resolves verified entity arguments while preserving literals, separates polarity, preserves epistemic type, supports versioned predicate aliases, and groups exact semantic equivalence without losing individual source occurrences or their temporal anchors.
- **K06 — Typed relation proposal compiler v0**: derives only structurally entailed polarity opposition automatically; semantic relations such as supports/refines/contradicts/supersedes remain scored provenance-bound proposals for downstream review.
- **K07 — Dual-clock temporal / supersession compiler v0**: preserves source occurrence and asserted/effective time as separate clocks, builds temporal state slots, and accepts evidence-bearing supersession proposals while blocking reverse chronology, slot mismatch, and same-proposition replacement. Recency alone never implies supersession.
- **K08 — Temporal-aware conflict compiler v0**: combines K06 conflict signals with K07 temporal state to distinguish overlapping contradiction candidates, temporally disjoint historical change, change-over-time candidates, and unresolved temporal ambiguity. Polarity opposition is never automatically promoted to canonical contradiction.

The compiler is designed to bridge the existing `personal_corpus_v04.duckdb` corpus to the existing M02 personal-memory staging/promotion machinery. Extractors emit staging IR only; later passes perform synthesis, review routing, and M02 bundle construction.

## Invariants

1. No extraction backend receives canonical-memory write authority.
2. Every candidate is bound to exact source evidence.
3. Epistemic ownership is preserved: user statements, assistant proposals, interpretations, decisions, outcomes, etc. are distinct.
4. Source-occurrence time and asserted/effective time are separate clocks and are never silently substituted for each other.
5. Temporal proxy time is explicit and cannot silently masquerade as exact chronology.
6. IDs and build receipts are content-derived from canonical JSON.
7. Candidate evidence may only cite compiler input chunks.
8. Soft similarity/model proposals remain hypotheses until governed resolution.
9. Existing M02/M03 canonical storage and recall are reused rather than reimplemented.
10. Decision retractions that would split an already-projected identity require deterministic full replay rather than unsafe in-place mutation.
11. Semantic deduplication never deletes or fuses source occurrences; temporal history remains available to later passes.
12. Recency never implies supersession.
13. Structural polarity opposition is an internal compiler signal, not an automatic canonical contradiction claim.
14. Temporally disjoint opposition is preserved as possible historical change rather than flattened into simultaneous inconsistency.

## Roadmap

- K00 Corpus IR — implemented v0.1
- K01 Candidate extraction — implemented deterministic shell v0.1; dual-clock prompt contract v1 frozen
- K02 Candidate validator / quarantine — implemented v0.1
- K03 Entity mention compiler — implemented v0.1
- K04 Entity resolution — implemented v0.1
- K05 Claim / decision / goal normalization and semantic deduplication — implemented v0.1
- K06 Relation compiler — implemented v0.1
- K07 Temporal / supersession compiler — implemented v0.1
- K08 Contradiction / conflict compiler — implemented v0.1
- K09 Entity/project/concept synthesis projection
- K10 Review router / adjudicator
- K11 IR → M02 staging adapter
- K12 Incremental scheduler / dependency graph
- K13 Full-corpus benchmark and promotion run

## Verified checkpoint

A disposable pull-request CI probe against the exact K00–K08 `main` state completed successfully on GitHub Actions using Python 3.11.16 / Ubuntu 24.04: **50 tests passed in 0.27 s**. The proof PR was closed without merge after evidence capture, so no probe-only file entered `main`.

**Next gate: K09 — deterministic entity/project/concept synthesis projections.** K09 may summarize and organize compiled evidence, but it may not promote unresolved material into canonical current truth; K10 owns adjudication.
