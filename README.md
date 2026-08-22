# EOR Corpus Compiler

Deterministic, provenance-bound compiler pipeline that transforms the existing EOR PersonalCorpus into staged semantic memory without granting extraction models canonical write authority.

This workstream is the **K Track**. The C Track is reserved for Persistent Controller Closure.

## Current implementation

- **K00 — Corpus IR v0**: typed atomic candidate assertions, exact evidence spans, temporal anchors, entity mentions, model lineage, content-derived identities.
- **K01 — Extraction compiler v0**: backend-neutral extraction boundary with deterministic input/build/output identities and post-extraction provenance validation.
- **K02 — Candidate validator / quarantine v0**: independently validates evidence containment and quarantines provenance-invalid candidates.
- **K03 — Entity mention compiler v0**: builds deterministic mention indexes without prematurely merging entity identities.
- **K04 — Global entity resolution v0**: stable entity identities, verified-alias reuse, redirects, keep-distinct constraints, auditable decision journal/retractions, indexed fuzzy candidate generation, and soft multi-model proposals that never silently merge identities.
- **K05 — Semantic normalization / exact dedup v0**: resolves verified entity arguments while preserving literals, separates polarity, preserves epistemic type, supports versioned predicate aliases, and groups exact semantic equivalence without losing individual source occurrences or their temporal anchors.
- **K06 — Typed relation proposal compiler v0**: derives only structurally entailed polarity opposition automatically; semantic relations such as supports/refines/contradicts/supersedes remain scored provenance-bound proposals for downstream review.

The compiler is designed to bridge the existing `personal_corpus_v04.duckdb` corpus to the existing M02 personal-memory staging/promotion machinery. Extractors emit staging IR only; later passes perform temporal/supersession compilation, contradiction handling, synthesis, review routing, and M02 bundle construction.

## Invariants

1. No extraction backend receives canonical-memory write authority.
2. Every candidate is bound to exact source evidence.
3. Epistemic ownership is preserved: user statements, assistant proposals, interpretations, decisions, outcomes, etc. are distinct.
4. Temporal proxy time is explicit and cannot silently masquerade as occurrence time.
5. IDs and build receipts are content-derived from canonical JSON.
6. Candidate evidence may only cite compiler input chunks.
7. Soft similarity/model proposals remain hypotheses until governed resolution.
8. Existing M02/M03 canonical storage and recall are reused rather than reimplemented.
9. Decision retractions that would split an already-projected identity require deterministic full replay rather than unsafe in-place mutation.
10. Semantic deduplication never deletes or fuses source occurrences; temporal history remains available to later passes.
11. K06 structural polarity opposition is an internal compiler relation, not an automatic canonical contradiction claim.

## Roadmap

- K00 Corpus IR — implemented v0.1
- K01 Candidate extraction — implemented deterministic shell v0.1
- K02 Candidate validator / quarantine — implemented v0.1
- K03 Entity mention compiler — implemented v0.1
- K04 Entity resolution — implemented v0.1; focused resolver harness 10/10 PASS; repository CI workflow installed
- K05 Claim / decision / goal normalization and semantic deduplication — implemented v0.1; repository test cases added
- K06 Relation compiler — implemented v0.1; repository test cases added
- K07 Temporal / supersession compiler
- K08 Contradiction compiler
- K09 Entity/project/concept synthesis
- K10 Review router / adjudicator
- K11 IR → M02 staging adapter
- K12 Incremental scheduler / dependency graph
- K13 Full-corpus benchmark and promotion run

Repository-level CI was installed, but the connected interface has not surfaced a completed push workflow result. Do not treat the repository suite as CI-verified until that run is observed.
