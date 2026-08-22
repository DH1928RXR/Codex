from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
from typing import Sequence

from .build import BuildIdentity, canonical_json
from .ir import CandidateAssertion, CorpusChunk
from .semantic_model import NormalizedAssertion, SemanticNormalizationResult
from .temporal_model import (
    Chronology,
    CompiledSupersession,
    StateSlotKey,
    SupersessionDisposition,
    SupersessionEvidence,
    SupersessionProposal,
    TemporalCompilationResult,
    TemporalDiagnostic,
    TemporalOccurrence,
    TemporalPolicy,
    TemporalStateSlot,
)


def _parse_source_time(value: str) -> tuple[bool, float] | None:
    """Return (timezone-aware, sortable scalar) for source-occurrence chronology."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return True, parsed.astimezone(timezone.utc).timestamp()
    return False, parsed.timestamp()


def compare_source_times(predecessor: Sequence[str], successor: Sequence[str]) -> Chronology:
    left = [_parse_source_time(v) for v in predecessor]
    right = [_parse_source_time(v) for v in successor]
    if not left or not right or any(v is None for v in left + right):
        return Chronology.UNKNOWN
    aware = {v[0] for v in left + right if v is not None}
    if len(aware) != 1:
        return Chronology.UNKNOWN
    left_values = [v[1] for v in left if v is not None]
    right_values = [v[1] for v in right if v is not None]
    if max(left_values) < min(right_values):
        return Chronology.BEFORE
    if min(left_values) > max(right_values):
        return Chronology.AFTER
    if set(left_values) == set(right_values):
        return Chronology.SAME
    return Chronology.UNKNOWN


def _fuse_scores(evidence: Sequence[SupersessionEvidence]) -> float:
    positive_product = 1.0
    negative_product = 1.0
    for item in evidence:
        if item.score >= 0:
            positive_product *= 1.0 - item.score
        else:
            negative_product *= 1.0 - abs(item.score)
    positive = 1.0 - positive_product
    negative = 1.0 - negative_product
    return max(0.0, min(1.0, positive * (1.0 - negative)))


class TemporalCompiler:
    """K07 dual-clock temporal compiler and governed supersession gate.

    Source-occurrence time answers "when was this assertion made?". The K00/K05
    effective TemporalAnchor answers "when does the assertion say it applies?".
    The two are never collapsed. Supersession is never inferred from recency alone.
    """

    def __init__(self, *, compiler_version: str = "0.1.0", policy: TemporalPolicy | None = None):
        self.compiler_version = compiler_version
        self.policy = policy or TemporalPolicy()

    def compile(
        self,
        normalized: SemanticNormalizationResult,
        candidates: Sequence[CandidateAssertion],
        chunks: Sequence[CorpusChunk],
        *,
        supersession_proposals: Sequence[SupersessionProposal] = (),
    ) -> TemporalCompilationResult:
        candidate_by_id = {c.candidate_id: c for c in candidates}
        if len(candidate_by_id) != len(candidates):
            raise ValueError("K07 input contains duplicate candidate identities")
        chunk_by_id = {c.chunk_id: c for c in chunks}
        if len(chunk_by_id) != len(chunks):
            raise ValueError("K07 input contains duplicate chunk identities")
        assertion_by_id = {a.normalized_id: a for a in normalized.assertions}
        if len(assertion_by_id) != len(normalized.assertions):
            raise ValueError("K07 input contains duplicate normalized assertion identities")
        group_by_signature = {g.signature.signature_id: g.group_id for g in normalized.groups}

        input_payload = {
            "normalized": normalized,
            "candidates": candidates,
            "chunks": chunks,
            "supersession_proposals": supersession_proposals,
        }
        input_hash = sha256(canonical_json(input_payload).encode("utf-8")).hexdigest()
        config_hash = sha256(canonical_json(self.policy).encode("utf-8")).hexdigest()
        build = BuildIdentity(
            "K07.compile_temporal_state",
            self.compiler_version,
            "eor.corpus_temporal_state.v0",
            config_hash,
            input_hash,
        )

        diagnostics: list[TemporalDiagnostic] = []
        occurrences: list[TemporalOccurrence] = []
        occurrence_by_assertion: dict[str, TemporalOccurrence] = {}
        slot_key_by_assertion: dict[str, StateSlotKey] = {}

        for assertion in sorted(normalized.assertions, key=lambda a: a.normalized_id):
            candidate = candidate_by_id.get(assertion.candidate_id)
            if candidate is None:
                raise ValueError("normalized assertion references candidate outside K07 inputs")
            source_times: set[str] = set()
            unknown_chunks = False
            for evidence in candidate.evidence:
                if evidence.chunk_id is None:
                    continue
                chunk = chunk_by_id.get(evidence.chunk_id)
                if chunk is None:
                    unknown_chunks = True
                    continue
                if chunk.occurred_at:
                    source_times.add(chunk.occurred_at)
            if unknown_chunks:
                diagnostics.append(TemporalDiagnostic(
                    "unknown_evidence_chunk",
                    "candidate evidence references a chunk outside K07 inputs",
                    candidate.candidate_id,
                    assertion.normalized_id,
                ))
            if not source_times:
                diagnostics.append(TemporalDiagnostic(
                    "missing_source_occurrence_time",
                    "no source-message occurrence time could be recovered from cited chunks",
                    candidate.candidate_id,
                    assertion.normalized_id,
                ))
            if assertion.temporal.is_proxy:
                diagnostics.append(TemporalDiagnostic(
                    "effective_time_is_proxy",
                    "effective temporal anchor is explicitly proxy-derived and remains non-canonical for exact chronology",
                    candidate.candidate_id,
                    assertion.normalized_id,
                ))

            slot_key = StateSlotKey(
                assertion.signature.subject,
                assertion.signature.predicate,
                assertion.signature.epistemic_type,
                assertion.signature.memory_class,
            )
            slot_key_by_assertion[assertion.normalized_id] = slot_key
            group_id = group_by_signature.get(assertion.signature.signature_id)
            if group_id is None:
                raise ValueError("normalized assertion signature has no semantic group")
            occurrence = TemporalOccurrence(
                assertion.normalized_id,
                assertion.candidate_id,
                group_id,
                slot_key.state_slot_id,
                tuple(sorted(source_times)),
                assertion.temporal,
            )
            occurrences.append(occurrence)
            occurrence_by_assertion[assertion.normalized_id] = occurrence

        slots: dict[str, list[TemporalOccurrence]] = defaultdict(list)
        slot_keys: dict[str, StateSlotKey] = {}
        for occurrence in occurrences:
            slot_key = slot_key_by_assertion[occurrence.normalized_assertion_id]
            slot_keys[slot_key.state_slot_id] = slot_key
            slots[slot_key.state_slot_id].append(occurrence)

        def occurrence_sort_key(occurrence: TemporalOccurrence) -> tuple:
            parsed = [_parse_source_time(v) for v in occurrence.source_occurrence_times]
            valid = [v for v in parsed if v is not None]
            if valid and len({v[0] for v in valid}) == 1:
                return (0, min(v[1] for v in valid), occurrence.occurrence_id)
            return (1, occurrence.source_occurrence_times, occurrence.occurrence_id)

        state_slots = tuple(
            TemporalStateSlot(
                slot_keys[slot_id],
                tuple(o.occurrence_id for o in sorted(items, key=occurrence_sort_key)),
            )
            for slot_id, items in sorted(slots.items())
        )

        aggregate: dict[tuple[str, str], dict] = {}
        for proposal in sorted(supersession_proposals, key=lambda p: p.proposal_id):
            predecessor = assertion_by_id.get(proposal.predecessor_assertion_id)
            successor = assertion_by_id.get(proposal.successor_assertion_id)
            if predecessor is None or successor is None:
                raise ValueError("supersession proposal references unknown normalized assertion")
            key = (predecessor.normalized_id, successor.normalized_id)
            slot = aggregate.setdefault(key, {"evidence": {}, "proposers": set()})
            for item in proposal.evidence:
                slot["evidence"][item.evidence_id] = item
            slot["proposers"].add(proposal.proposer)

        supersessions: list[CompiledSupersession] = []
        for (predecessor_id, successor_id), slot in sorted(aggregate.items()):
            predecessor = assertion_by_id[predecessor_id]
            successor = assertion_by_id[successor_id]
            predecessor_occurrence = occurrence_by_assertion[predecessor_id]
            successor_occurrence = occurrence_by_assertion[successor_id]
            chronology = compare_source_times(
                predecessor_occurrence.source_occurrence_times,
                successor_occurrence.source_occurrence_times,
            )
            evidence = tuple(sorted(slot["evidence"].values(), key=lambda e: e.evidence_id))
            score = _fuse_scores(evidence)

            if predecessor.signature.signature_id == successor.signature.signature_id:
                disposition = SupersessionDisposition.BLOCKED_SAME_PROPOSITION
            elif slot_key_by_assertion[predecessor_id].state_slot_id != slot_key_by_assertion[successor_id].state_slot_id:
                disposition = SupersessionDisposition.BLOCKED_SLOT_MISMATCH
            elif chronology in {Chronology.AFTER, Chronology.SAME}:
                disposition = SupersessionDisposition.BLOCKED_CHRONOLOGY
            elif score >= self.policy.review_threshold and (
                chronology == Chronology.BEFORE or not self.policy.require_known_forward_chronology_for_review
            ):
                disposition = SupersessionDisposition.REVIEW_REQUIRED
            else:
                disposition = SupersessionDisposition.SUGGESTED

            supersessions.append(CompiledSupersession(
                predecessor_id,
                successor_id,
                chronology,
                score,
                evidence,
                tuple(sorted(slot["proposers"])),
                disposition,
            ))

        return TemporalCompilationResult(
            build,
            tuple(sorted(occurrences, key=lambda o: o.occurrence_id)),
            state_slots,
            tuple(sorted(supersessions, key=lambda s: s.supersession_id)),
            tuple(sorted(diagnostics, key=lambda d: d.diagnostic_id)),
        )
