# EOR Corpus Compiler

Deterministic, provenance-bound compiler pipeline that transforms the existing EOR PersonalCorpus into staged semantic memory without granting extraction models canonical write authority.

This workstream is the **K Track**. The C Track is reserved for Persistent Controller Closure.

## Current implementation

- **K00 — Corpus IR v0**: typed atomic candidate assertions, exact evidence spans, temporal anchors, entity mentions, model lineage, content-derived identities.
- **K01 — Extraction compiler v0**: backend-neutral extraction boundary with deterministic input/build/output identities and post-extraction provenance validation.
- **K02 — Candidate validator / quarantine v0**: independently validates evidence containment and quarantines provenance-invalid candidates.
- **K03 — Entity mention compiler v0**: builds deterministic mention indexes without prematurely merging entity identities.

The compiler is designed to bridge the existing `personal_corpus_v04.duckdb` corpus to the existing M02 personal-memory staging/promotion machinery. Extractors emit staging IR only; later passes perform entity resolution, normalization, temporal/supersession compilation, contradiction handling, synthesis, review routing, and M02 bundle construction.

## Invariants

1. No extraction backend receives canonical-memory write authority.
2. Every candidate is bound to exact source evidence.
3. Epistemic ownership is preserved: user statements, assistant proposals, interpretations, decisions, outcomes, etc. are distinct.
4. Temporal proxy time is explicit and cannot silently masquerade as occurrence time.
5. IDs and build receipts are content-derived from canonical JSON.
6. Candidate evidence may only cite compiler input chunks.
7. Global alias resolution and inter-record relationships belong to later compiler passes.
8. Existing M02/M03 canonical storage and recall are reused rather than reimplemented.

## Roadmap

- K00 Corpus IR — implemented v0.1
- K01 Candidate extraction — implemented deterministic shell v0.1
- K02 Candidate validator / quarantine — implemented v0.1
- K03 Entity mention compiler — implemented v0.1
- K04 Entity resolution
- K05 Claim / decision / goal normalization
- K06 Relation compiler
- K07 Temporal / supersession compiler
- K08 Contradiction compiler
- K09 Entity/project/concept synthesis
- K10 Review router / adjudicator
- K11 IR → M02 staging adapter
- K12 Incremental scheduler / dependency graph
- K13 Full-corpus benchmark and promotion run
