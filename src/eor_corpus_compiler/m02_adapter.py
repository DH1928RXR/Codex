from __future__ import annotations

from hashlib import sha256
from typing import Sequence

from .build import BuildIdentity, canonical_json
from .conflict_model import ConflictCompilationResult, ConflictDisposition
from .ir import CandidateAssertion, CorpusChunk, TemporalPrecision
from .m02_adapter_model import (
    M02AdapterDiagnostic,
    M02CandidateDisposition,
    M02CapabilityDescriptor,
    M02Eligibility,
    M02EvidenceInput,
    M02PreparationResult,
    M02RecordInput,
    M02RelationInput,
    M02StagingArtifact,
    VerifiedM02StagingBackend,
)
from .relation_model import RelationCompilationResult, RelationDisposition, RelationType
from .review_model import AdjudicationDisposition, AdjudicationResult, ReviewQueue
from .semantic_model import SemanticNormalizationResult
from .temporal_model import SupersessionDisposition, TemporalCompilationResult
from .validator import ValidationResult


_M02_RELATIONS = {
    RelationType.SUPPORTS: "supports",
    RelationType.REPEATS: "repeats",
    RelationType.ELABORATES: "elaborates",
    RelationType.REFINES: "refines",
    RelationType.QUALIFIES: "qualifies",
    RelationType.CONTRADICTS: "contradicts",
    RelationType.SUPERSEDES: "supersedes",
    RelationType.UNRELATED: "unrelated",
}


class M02StagingAdapter:
    """K11 prepares corpus records for an already-verified M02 staging backend.

    K11 never materializes canonical M02 schemas itself and never possesses promotion
    authority. It selects/normalizes exact inputs, then delegates closed-bundle build
    and validation to the supplied verified backend.
    """

    def __init__(self, backend: VerifiedM02StagingBackend, *, compiler_version: str = "0.1.0"):
        if not isinstance(backend, VerifiedM02StagingBackend):
            raise TypeError("backend must implement VerifiedM02StagingBackend")
        self.backend = backend
        self.compiler_version = compiler_version
        self.capability = backend.capabilities()
        if self.capability.exposes_promotion:
            raise ValueError("K11 refuses promotion-capable backends")

    @staticmethod
    def _effective_anchor_requires_preservation(candidate: CandidateAssertion) -> bool:
        anchor = candidate.temporal
        if anchor.precision == TemporalPrecision.UNKNOWN and anchor.start is None and anchor.end is None:
            return False
        if anchor.start is None and anchor.end is None and not anchor.original_expression:
            return False
        return True

    @staticmethod
    def _accepted_source_refs(queue: ReviewQueue, adjudication: AdjudicationResult) -> dict[str, str]:
        item_by_id = {item.review_item_id: item for item in queue.items}
        accepted: dict[str, str] = {}
        for record in adjudication.records:
            if record.disposition != AdjudicationDisposition.ACCEPTED:
                continue
            item = item_by_id.get(record.review_item_id)
            if item is None:
                raise ValueError("adjudication references review item outside K10 queue")
            accepted[item.source_ref] = record.adjudication_id
        return accepted

    def prepare(
        self,
        validation: ValidationResult,
        candidates: Sequence[CandidateAssertion],
        chunks: Sequence[CorpusChunk],
        normalized: SemanticNormalizationResult,
        relations: RelationCompilationResult,
        temporal: TemporalCompilationResult,
        conflicts: ConflictCompilationResult,
        review_queue: ReviewQueue,
        adjudication: AdjudicationResult,
    ) -> M02PreparationResult:
        payload = {
            "validation": validation,
            "candidates": candidates,
            "chunks": chunks,
            "normalized": normalized,
            "relations": relations,
            "temporal": temporal,
            "conflicts": conflicts,
            "review_queue": review_queue,
            "adjudication": adjudication,
            "capability": self.capability,
        }
        input_hash = sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        config_hash = sha256(canonical_json({"backend_capability": self.capability}).encode("utf-8")).hexdigest()
        build = BuildIdentity(
            "K11.prepare_m02_staging",
            self.compiler_version,
            "eor.corpus_m02_staging_adapter.v0",
            config_hash,
            input_hash,
        )

        candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
        if len(candidate_by_id) != len(candidates):
            raise ValueError("K11 input contains duplicate candidate identities")
        chunk_by_id = {chunk.chunk_id: chunk for chunk in chunks}
        if len(chunk_by_id) != len(chunks):
            raise ValueError("K11 input contains duplicate chunk identities")
        accepted_validation_ids = {candidate.candidate_id for candidate in validation.accepted}
        quarantined_validation_ids = {item.candidate.candidate_id for item in validation.quarantined}
        if accepted_validation_ids & quarantined_validation_ids:
            raise ValueError("K02 result contains candidate in both accepted and quarantined sets")

        assertion_by_candidate = {assertion.candidate_id: assertion for assertion in normalized.assertions}
        group_by_id = {group.group_id: group for group in normalized.groups}
        candidate_group: dict[str, str] = {}
        for group in normalized.groups:
            for candidate_id in group.candidate_ids:
                existing = candidate_group.get(candidate_id)
                if existing is not None and existing != group.group_id:
                    raise ValueError("candidate belongs to multiple K05 semantic groups")
                candidate_group[candidate_id] = group.group_id

        accepted_review_refs = self._accepted_source_refs(review_queue, adjudication)
        diagnostics: list[M02AdapterDiagnostic] = []
        dispositions: list[M02CandidateDisposition] = []
        provisional_records: dict[str, M02RecordInput] = {}

        supported_sources = set(self.capability.supported_source_types)
        supported_temporal = set(self.capability.supported_temporal_bases)

        for candidate_id, candidate in sorted(candidate_by_id.items()):
            reasons: list[str] = []
            eligibility = M02Eligibility.ELIGIBLE
            if candidate_id not in accepted_validation_ids:
                eligibility = M02Eligibility.BLOCKED_VALIDATION
                reasons.append("k02_not_accepted")
                dispositions.append(M02CandidateDisposition(candidate_id, eligibility, tuple(reasons)))
                continue

            assertion = assertion_by_candidate.get(candidate_id)
            if assertion is None:
                eligibility = M02Eligibility.BLOCKED_VALIDATION
                reasons.append("missing_k05_normalized_assertion")
                dispositions.append(M02CandidateDisposition(candidate_id, eligibility, tuple(reasons)))
                continue

            evidence_inputs: list[M02EvidenceInput] = []
            source_times: set[str] = set()
            source_types: set[str] = set()
            exactness_failed = False
            for evidence in candidate.evidence:
                if evidence.chunk_id is None:
                    exactness_failed = True
                    reasons.append("evidence_without_chunk")
                    continue
                chunk = chunk_by_id.get(evidence.chunk_id)
                if chunk is None:
                    exactness_failed = True
                    reasons.append("evidence_chunk_missing")
                    continue
                source_hash = evidence.source_sha256 or chunk.source_sha256
                if not source_hash or len(source_hash) != 64:
                    exactness_failed = True
                    reasons.append("source_sha256_missing")
                    continue
                if evidence.exact_text not in chunk.text:
                    exactness_failed = True
                    reasons.append("evidence_text_not_in_chunk")
                    continue
                source_types.add(evidence.source_type)
                if chunk.occurred_at:
                    source_times.add(chunk.occurred_at)
                evidence_inputs.append(M02EvidenceInput(
                    evidence.evidence_id,
                    evidence.source_id,
                    evidence.source_type,
                    evidence.conversation_id,
                    evidence.message_id,
                    evidence.chunk_id,
                    evidence.speaker,
                    evidence.exact_text,
                    source_hash,
                    chunk.occurred_at,
                ))

            if exactness_failed or not evidence_inputs:
                eligibility = M02Eligibility.BLOCKED_SOURCE_EXACTNESS
                dispositions.append(M02CandidateDisposition(candidate_id, eligibility, tuple(reasons)))
                continue

            unsupported_sources = source_types - supported_sources
            if unsupported_sources:
                eligibility = M02Eligibility.BLOCKED_SOURCE_MODE
                reasons.extend(f"unsupported_source_type:{value}" for value in sorted(unsupported_sources))
                dispositions.append(M02CandidateDisposition(candidate_id, eligibility, tuple(reasons)))
                continue

            if not source_times:
                temporal_basis = "unknown"
            elif len(source_times) == 1:
                temporal_basis = "source_exact_timestamp"
            else:
                temporal_basis = "source_bounded_interval"

            if temporal_basis not in supported_temporal or temporal_basis == "unknown":
                eligibility = M02Eligibility.BLOCKED_TEMPORAL_CONTRACT
                reasons.append(f"unsupported_temporal_basis:{temporal_basis}")
                dispositions.append(M02CandidateDisposition(candidate_id, eligibility, tuple(reasons)))
                continue

            if self._effective_anchor_requires_preservation(candidate) and not self.capability.preserves_effective_anchor:
                eligibility = M02Eligibility.BLOCKED_TEMPORAL_CONTRACT
                reasons.append("semantic_effective_time_not_preserved_by_m02_backend")
                dispositions.append(M02CandidateDisposition(candidate_id, eligibility, tuple(reasons)))
                continue

            provisional_records[candidate_id] = M02RecordInput(
                candidate_id,
                candidate.memory_class.value,
                candidate.epistemic_type.value,
                candidate.statement,
                candidate.subject,
                candidate.predicate,
                candidate.object,
                candidate.source_origin_probability,
                candidate.extractor_confidence,
                candidate.importance,
                candidate.durability,
                candidate.tags,
                tuple(sorted(evidence_inputs, key=lambda e: e.evidence_id)),
                tuple(sorted(source_times)),
                temporal_basis,
                candidate.temporal,
                (),
            )
            dispositions.append(M02CandidateDisposition(candidate_id, M02Eligibility.ELIGIBLE, ()))

        eligible_ids = set(provisional_records)
        eligible_relations: list[M02RelationInput] = []
        supported_relations = set(self.capability.supported_relation_types)

        def group_candidate(group_id: str, source_ref: str) -> str | None:
            group = group_by_id.get(group_id)
            if group is None:
                diagnostics.append(M02AdapterDiagnostic("unknown_relation_group", "relation references unknown K05 semantic group", source_ref))
                return None
            eligible = sorted(set(group.candidate_ids) & eligible_ids)
            if len(eligible) != 1:
                diagnostics.append(M02AdapterDiagnostic(
                    "ambiguous_group_to_record_relation",
                    "K11 refuses to expand a proposition-level relation across zero or multiple source records",
                    source_ref,
                ))
                return None
            return eligible[0]

        def append_relation(group_a: str, group_b: str, relation_type: str, source_ref: str, adjudication_ref: str) -> None:
            if relation_type not in supported_relations:
                diagnostics.append(M02AdapterDiagnostic("unsupported_m02_relation", f"backend does not support relation type {relation_type}", source_ref))
                return
            left = group_candidate(group_a, source_ref)
            right = group_candidate(group_b, source_ref)
            if left is None or right is None or left == right:
                return
            eligible_relations.append(M02RelationInput(left, right, relation_type, source_ref, adjudication_ref))

        for relation in relations.relations:
            mapped = _M02_RELATIONS.get(relation.key.relation_type)
            if mapped is None:
                continue
            if relation.disposition == RelationDisposition.STRUCTURAL:
                diagnostics.append(M02AdapterDiagnostic(
                    "structural_relation_not_promoted",
                    "K06 structural relation is compiler evidence only and is not emitted as canonical M02 relation",
                    relation.relation_id,
                ))
                continue
            adjudication_ref = accepted_review_refs.get(relation.relation_id)
            if adjudication_ref is None:
                diagnostics.append(M02AdapterDiagnostic("relation_not_adjudicated_accepted", "semantic relation omitted until K10 acceptance", relation.relation_id))
                continue
            append_relation(
                relation.key.source_group_id,
                relation.key.target_group_id,
                mapped,
                relation.relation_id,
                adjudication_ref,
            )

        assertion_group = {}
        for group in normalized.groups:
            for assertion_id in group.normalized_assertion_ids:
                assertion_group[assertion_id] = group.group_id

        for supersession in temporal.supersessions:
            if supersession.disposition not in {SupersessionDisposition.SUGGESTED, SupersessionDisposition.REVIEW_REQUIRED}:
                continue
            adjudication_ref = accepted_review_refs.get(supersession.supersession_id)
            if adjudication_ref is None:
                continue
            predecessor_group = assertion_group.get(supersession.predecessor_assertion_id)
            successor_group = assertion_group.get(supersession.successor_assertion_id)
            if predecessor_group and successor_group:
                append_relation(predecessor_group, successor_group, "supersedes", supersession.supersession_id, adjudication_ref)

        for conflict in conflicts.conflicts:
            if conflict.disposition in {ConflictDisposition.TEMPORALLY_DISJOINT, ConflictDisposition.CHANGE_OVER_TIME_CANDIDATE}:
                continue
            adjudication_ref = accepted_review_refs.get(conflict.conflict_id)
            if adjudication_ref is None:
                continue
            append_relation(conflict.left_group_id, conflict.right_group_id, "contradicts", conflict.conflict_id, adjudication_ref)

        relation_by_source: dict[str, list[M02RelationInput]] = {}
        dedup_relations = {relation.relation_input_id: relation for relation in eligible_relations}
        eligible_relations_tuple = tuple(sorted(dedup_relations.values(), key=lambda r: r.relation_input_id))
        for relation in eligible_relations_tuple:
            relation_by_source.setdefault(relation.source_candidate_id, []).append(relation)

        records = []
        for candidate_id, record in sorted(provisional_records.items()):
            attached = tuple(sorted(relation_by_source.get(candidate_id, []), key=lambda r: r.relation_input_id))
            records.append(M02RecordInput(
                record.candidate_id,
                record.memory_class,
                record.epistemic_type,
                record.statement,
                record.subject,
                record.predicate,
                record.object,
                record.source_origin_probability,
                record.extractor_confidence,
                record.importance,
                record.durability,
                record.tags,
                record.evidence,
                record.source_occurrence_times,
                record.temporal_basis,
                record.effective_anchor,
                attached,
            ))

        return M02PreparationResult(
            build,
            self.capability.capability_id,
            tuple(records),
            tuple(sorted(dispositions, key=lambda d: d.candidate_id)),
            eligible_relations_tuple,
            tuple(sorted(diagnostics, key=lambda d: d.diagnostic_id)),
        )

    def build_and_validate_pending_bundle(
        self,
        prepared: M02PreparationResult,
        *,
        bundle_id: str,
        created_at: str,
    ) -> M02StagingArtifact:
        if prepared.capability_id != self.capability.capability_id:
            raise ValueError("K11 prepared state was built against a different M02 backend capability")
        if not self.capability.can_build_pending_review_bundle:
            raise ValueError("verified M02 backend cannot build pending-review staging bundles")
        if not self.capability.can_validate_bundle:
            raise ValueError("verified M02 backend cannot validate staging bundles")
        artifact = self.backend.build_pending_staging(
            prepared.eligible_records,
            prepared.eligible_relations,
            bundle_id=bundle_id,
            created_at=created_at,
        )
        if artifact.backend_id != self.capability.backend_id:
            raise ValueError("M02 backend returned artifact under unexpected backend identity")
        validated = self.backend.validate_staging(artifact)
        if validated.bundle_id != artifact.bundle_id or validated.bundle_sha256 != artifact.bundle_sha256:
            raise ValueError("M02 validation changed staging bundle identity")
        return validated
