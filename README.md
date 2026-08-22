# EOR Corpus Compiler

Deterministic, provenance-bound compiler pipeline that transforms the existing EOR PersonalCorpus into governed semantic-memory staging without granting extraction models canonical write authority.

This workstream is the **K Track**. The C Track is reserved for Persistent Controller Closure.

## Current implementation

- **K00 — Corpus IR v0**: typed atomic candidate assertions, exact evidence spans, temporal anchors, entity mentions, model lineage, content-derived identities.
- **K01 — Extraction compiler v0**: backend-neutral extraction boundary with deterministic input/build/output identities. Source occurrence (`CorpusChunk.occurred_at`) and asserted/effective time (`CandidateAssertion.temporal`) are explicitly separate clocks.
- **K02 — Candidate validator / quarantine v0**: validates evidence containment and quarantines provenance-invalid candidates.
- **K03 — Entity mention compiler v0**: deterministic mention indexes without premature identity merging.
- **K04 — Global entity resolution v0**: stable entity IDs, alias reuse, redirects, keep-distinct constraints, auditable decisions/retractions, indexed candidate generation, and soft model proposals that never silently merge identities.
- **K05 — Semantic normalization / exact dedup v0**: preserves epistemic type and polarity, resolves verified entity arguments, supports versioned predicate aliases, and groups exact semantic equivalence without deleting source occurrences.
- **K06 — Typed relation proposal compiler v0**: auto-derives only structurally entailed internal signals; semantic supports/refines/contradicts/supersedes edges remain provenance-bound proposals until review.
- **K07 — Dual-clock temporal / supersession compiler v0**: source occurrence and effective time remain separate; recency alone never implies persistence or supersession.
- **K08 — Temporal-aware conflict compiler v0**: distinguishes overlapping contradiction candidates, temporally disjoint historical differences, change-over-time candidates, and unresolved temporal ambiguity.
- **K09 — Lossless synthesis projection v0**: rebuildable entity cards link propositions, source occurrences, relations, conflicts, supersession candidates, unresolved identity hypotheses, and latest-observed occurrence sets. There is no `current_truth` field.
- **K10 — Review router / adjudicator v0**: unifies unresolved compiler state into an authority-routed queue (`Terra < Sol < Dan`). Lower authority cannot finalize higher-routed work; conflicting same-authority final decisions remain pending.
- **K11 — Verified M02 staging bridge v0**: prepares exact corpus records/relations and delegates closed-bundle build/validation to an existing verified M02 backend. K11 rejects promotion-capable backends and contains no canonical append path.
- **K12 — Incremental scheduler / DAG v0**: stage+partition task identities, content-bound cache fingerprints, parallel waves, conservative dirty propagation, resumable failed-task retry, and output-stable replanning.
- **K13 — Benchmark/audit harness v0**: aggregate quality metrics and configurable fail-closed thresholds plus a private-data-free scale probe for the known corpus shape.

## Governing invariants

1. No extraction/model backend receives canonical-memory write authority.
2. Every candidate is bound to exact source evidence.
3. Epistemic ownership is preserved: user statement, assistant proposal, interpretation, decision, goal, plan, outcome, belief, uncertainty, etc. are distinct.
4. Source-occurrence time and asserted/effective time are separate clocks.
5. Proxy time remains labelled proxy time.
6. IDs, build receipts, cache fingerprints, and audit reports are content-derived.
7. Soft identity/relation/supersession/conflict proposals remain hypotheses until governed review.
8. Semantic deduplication never deletes source occurrences.
9. Recency never implies supersession.
10. Temporally disjoint opposition is not flattened into simultaneous contradiction.
11. Synthesis is a rebuildable projection, not canonical truth authority.
12. K10 authority is monotonic: higher-authority decisions control lower-authority disagreement; unresolved equal-authority disagreement remains pending.
13. Existing M02/M03 canonical storage and recall are reused rather than reimplemented.
14. K11 can prepare and validate pending staging but cannot authorize or promote it.
15. K12 cache reuse depends on exact compiler/config/input/dependency-output identity, not timestamps.
16. Real personal-corpus evidence and private benchmark outputs do not enter this public repository.

## K00-K13 status

- K00 Corpus IR — implemented v0.1
- K01 Candidate extraction — implemented v0.1; dual-clock prompt contract frozen
- K02 Validation / quarantine — implemented v0.1
- K03 Entity mention compiler — implemented v0.1
- K04 Entity resolution — implemented v0.1
- K05 Semantic normalization / dedup — implemented v0.1
- K06 Relation compiler — implemented v0.1
- K07 Temporal / supersession compiler — implemented v0.1
- K08 Conflict compiler — implemented v0.1
- K09 Synthesis projections — implemented v0.1
- K10 Review routing / adjudication — implemented v0.1
- K11 Verified-M02 staging bridge — implemented v0.1
- K12 Incremental scheduler / dependency graph — implemented v0.1
- K13 Benchmark/audit and scale harness — implemented v0.1
- **Private K13 corpus execution / quality calibration / governed M02 staging campaign — pending**

## Verified checkpoint

A disposable pull-request CI proof against exact `main` SHA `b591ec2dd8c4a3d5ca8b521980e9da3769b46dd2` completed successfully on GitHub Actions using Python 3.11.16 / Ubuntu 24.04: **91 tests passed in 0.76 s**. The proof PR was closed without merge, so the probe-only file never entered `main`.

Earlier gates were independently proven at 42/42 (through K07), 50/50 (through K08), 57/57 (through K09), 67/67 (through K10), 77/77 (through K11), and 86/86 (through K12).

## Scale probe

The reference DAG for the known 597-conversation PersonalCorpus contains:

- **1,799 total tasks**;
- **1,791 conversation-local K01-K03 map tasks**;
- **8 global K04-K11 reducer/bridge tasks**;
- **10 dependency waves** on a cold build.

A synthetic single-conversation input change initially schedules only **11 tasks to run** and leaves **1,788 tasks reusable**. K12 supports replanning after each wave, so if the changed upstream task recompiles to the same output hash, additional downstream work can collapse back to cache reuse.

## M02 boundary

K11 targets the existing `eor.personal_memory_record.v0` / `eor.personal_memory_staging_bundle.v0` architecture through a capability-discovered verified backend. It deliberately does **not** implement `PersonalPromotionAuthorizationV0`, store pre-state binding, `promote_many()`, database credentials, ledger heads, or any equivalent canonical-write authority.

The next operational gate is therefore not another compiler primitive. It is a **private representative-corpus run**, followed by benchmark calibration, review-routing inspection, M02 compatibility analysis, and only then a governed pending-staging build using the verified M02 implementation.
