from hashlib import sha256

import pytest

from eor_corpus_compiler.build import BuildIdentity, canonical_json
from eor_corpus_compiler.conflict_model import ConflictCompilationResult
from eor_corpus_compiler.ir import (
    CandidateAssertion,
    CorpusChunk,
    EpistemicType,
    EvidenceSpan,
    MemoryClass,
    ModelLineage,
    TemporalAnchor,
    TemporalPrecision,
)
from eor_corpus_compiler.m02_adapter import M02StagingAdapter
from eor_corpus_compiler.m02_adapter_model import (
    M02CapabilityDescriptor,
    M02Eligibility,
    M02StagingArtifact,
)
from eor_corpus_compiler.relation_model import (
    CompiledRelation,
    RelationCompilationResult,
    RelationDisposition,
    RelationEvidence,
    RelationKey,
    RelationType,
)
from eor_corpus_compiler.review import ReviewAdjudicator
from eor_corpus_compiler.review_model import (
    ReviewAuthority,
    ReviewDecision,
    ReviewItem,
    ReviewKind,
    ReviewQueue,
    ReviewResponse,
)
from eor_corpus_compiler.semantic_model import (
    ArgumentKind,
    NormalizedAssertion,
    Polarity,
    SemanticArgument,
    SemanticArgumentIdentity,
    SemanticGroup,
    SemanticNormalizationResult,
    SemanticSignature,
)
from eor_corpus_compiler.temporal_model import TemporalCompilationResult
from eor_corpus_compiler.validator import CandidateValidator


def build():
    return BuildIdentity("test", "0", "test", "0" * 64, "1" * 64)


class FakeM02Backend:
    def __init__(self, *, source_types=("chat_message",), preserves_effective_anchor=False, exposes_promotion=False):
        self._capability = M02CapabilityDescriptor(
            "fake-m02-v0",
            "eor.personal_memory_record.v0",
            "eor.personal_memory_staging_bundle.v0",
            tuple(source_types),
            ("supports", "repeats", "elaborates", "refines", "qualifies", "contradicts", "supersedes", "unrelated"),
            ("source_exact_timestamp", "source_bounded_interval"),
            True,
            True,
            preserves_effective_anchor,
            exposes_promotion,
        )
        self.build_calls = 0
        self.validate_calls = 0

    def capabilities(self):
        return self._capability

    def build_pending_staging(self, records, relations, *, bundle_id, created_at):
        self.build_calls += 1
        payload = {"records": records, "relations": relations, "bundle_id": bundle_id, "created_at": created_at}
        digest = sha256(canonical_json(payload).encode()).hexdigest()
        return M02StagingArtifact(
            self._capability.backend_id,
            bundle_id,
            digest,
            tuple(f"record:{record.candidate_id}" for record in records),
            tuple(record.candidate_id for record in records),
            False,
            "BUILT_PENDING_REVIEW",
        )

    def validate_staging(self, artifact):
        self.validate_calls += 1
        return M02StagingArtifact(
            artifact.backend_id,
            artifact.bundle_id,
            artifact.bundle_sha256,
            artifact.record_ids,
            artifact.candidate_ids,
            False,
            "VALID_PENDING_REVIEW",
            "fake-validation-receipt",
        )


def candidate(suffix, *, object_value="EOR", source_type="chat_message", source_hash=True, occurred_at="2026-08-22T10:00:00-04:00", effective=False):
    text = f"Dan is building {object_value} {suffix}."
    digest = sha256(text.encode()).hexdigest() if source_hash else None
    chunk = CorpusChunk(
        f"chunk:{suffix}",
        f"source:{suffix}",
        f"conversation:{suffix}",
        "test",
        "Dan",
        occurred_at,
        text,
        digest,
    )
    evidence = EvidenceSpan(
        f"source:{suffix}",
        source_type,
        f"conversation:{suffix}",
        f"message:{suffix}",
        f"chunk:{suffix}",
        "Dan",
        text,
        source_sha256=digest,
    )
    temporal = (
        TemporalAnchor("2028-01-01", None, TemporalPrecision.DAY, "America/Toronto", original_expression="in 2028")
        if effective
        else TemporalAnchor(None, None, TemporalPrecision.UNKNOWN, "America/Toronto")
    )
    item = CandidateAssertion(
        f"Dan is building {object_value}.",
        "Dan",
        "builds",
        object_value,
        EpistemicType.PROJECT_STATE,
        MemoryClass.PROJECT,
        (evidence,),
        temporal,
        (),
        ("eor",),
        ModelLineage("test", "model", "extractor", "contract", "1"),
        0.9,
        1.0,
        0.8,
        0.8,
    )
    return item, chunk


def normalized_for(*items):
    assertions = []
    groups_by_id = {}
    for item in items:
        signature = SemanticSignature(
            SemanticArgumentIdentity(ArgumentKind.LITERAL, "dan"),
            "builds",
            SemanticArgumentIdentity(ArgumentKind.LITERAL, item.object.casefold()),
            Polarity.POSITIVE,
            item.epistemic_type,
            item.memory_class,
        )
        assertion = NormalizedAssertion(
            item.candidate_id,
            signature,
            SemanticArgument(ArgumentKind.LITERAL, "dan", "Dan", "literal"),
            SemanticArgument(ArgumentKind.LITERAL, item.object.casefold(), item.object, "literal"),
            item.statement,
            tuple(e.evidence_id for e in item.evidence),
            item.temporal,
            item.extractor_confidence,
            item.source_origin_probability,
            item.importance,
            item.durability,
        )
        assertions.append(assertion)
        group = groups_by_id.get(signature.signature_id)
        if group is None:
            groups_by_id[signature.signature_id] = SemanticGroup(signature, (assertion.normalized_id,), (item.candidate_id,), item.candidate_id)
        else:
            groups_by_id[signature.signature_id] = SemanticGroup(
                signature,
                tuple(sorted(group.normalized_assertion_ids + (assertion.normalized_id,))),
                tuple(sorted(group.candidate_ids + (item.candidate_id,))),
                min(group.representative_candidate_id, item.candidate_id),
            )
    return SemanticNormalizationResult(build(), tuple(assertions), tuple(groups_by_id.values()), ())


def empty_review_state():
    queue = ReviewQueue(build(), ())
    return queue, ReviewAdjudicator().compile(queue, ())


def compile_inputs(items, chunks, *, relation_result=None, queue=None, adjudication=None):
    validation = CandidateValidator().validate(chunks, items)
    normalized = normalized_for(*items)
    relations = relation_result or RelationCompilationResult(build(), ())
    temporal = TemporalCompilationResult(build(), (), (), (), ())
    conflicts = ConflictCompilationResult(build(), (), ())
    if queue is None or adjudication is None:
        queue, adjudication = empty_review_state()
    return validation, items, chunks, normalized, relations, temporal, conflicts, queue, adjudication


def test_k11_rejects_promotion_capable_backend():
    with pytest.raises(ValueError):
        M02StagingAdapter(FakeM02Backend(exposes_promotion=True))


def test_exact_chat_source_becomes_eligible_record():
    item, chunk = candidate("1")
    adapter = M02StagingAdapter(FakeM02Backend())
    prepared = adapter.prepare(*compile_inputs((item,), (chunk,)))
    assert len(prepared.eligible_records) == 1
    assert prepared.eligible_records[0].candidate_id == item.candidate_id
    assert prepared.eligible_records[0].temporal_basis == "source_exact_timestamp"
    assert prepared.candidate_dispositions[0].eligibility == M02Eligibility.ELIGIBLE


def test_missing_source_sha_blocks_exact_staging():
    item, chunk = candidate("1", source_hash=False)
    adapter = M02StagingAdapter(FakeM02Backend())
    prepared = adapter.prepare(*compile_inputs((item,), (chunk,)))
    assert prepared.eligible_records == ()
    disposition = prepared.candidate_dispositions[0]
    assert disposition.eligibility == M02Eligibility.BLOCKED_SOURCE_EXACTNESS
    assert "source_sha256_missing" in disposition.reason_codes


def test_unsupported_source_type_requires_backend_contract_support():
    item, chunk = candidate("1", source_type="drive_file")
    adapter = M02StagingAdapter(FakeM02Backend(source_types=("chat_message",)))
    prepared = adapter.prepare(*compile_inputs((item,), (chunk,)))
    assert prepared.candidate_dispositions[0].eligibility == M02Eligibility.BLOCKED_SOURCE_MODE


def test_semantic_effective_time_blocks_backend_that_cannot_preserve_it():
    item, chunk = candidate("1", effective=True)
    adapter = M02StagingAdapter(FakeM02Backend(preserves_effective_anchor=False))
    prepared = adapter.prepare(*compile_inputs((item,), (chunk,)))
    assert prepared.candidate_dispositions[0].eligibility == M02Eligibility.BLOCKED_TEMPORAL_CONTRACT
    assert "semantic_effective_time_not_preserved_by_m02_backend" in prepared.candidate_dispositions[0].reason_codes


def test_semantic_effective_time_can_cross_when_backend_explicitly_preserves_it():
    item, chunk = candidate("1", effective=True)
    adapter = M02StagingAdapter(FakeM02Backend(preserves_effective_anchor=True))
    prepared = adapter.prepare(*compile_inputs((item,), (chunk,)))
    assert prepared.candidate_dispositions[0].eligibility == M02Eligibility.ELIGIBLE
    assert prepared.eligible_records[0].effective_anchor.start == "2028-01-01"


def test_unknown_source_occurrence_time_is_fail_closed():
    item, chunk = candidate("1", occurred_at=None)
    adapter = M02StagingAdapter(FakeM02Backend())
    prepared = adapter.prepare(*compile_inputs((item,), (chunk,)))
    assert prepared.candidate_dispositions[0].eligibility == M02Eligibility.BLOCKED_TEMPORAL_CONTRACT


def accepted_relation_state(first, second, relation):
    item = ReviewItem(
        ReviewKind.RELATION,
        relation.relation_id,
        relation.score,
        1.0 - relation.score,
        0.5,
        0.5,
        ReviewAuthority.TERRA,
        ("test",),
        (),
        (relation.key.source_group_id, relation.key.target_group_id),
    )
    queue = ReviewQueue(build(), (item,))
    response = ReviewResponse(item.review_item_id, "terra", ReviewAuthority.TERRA, ReviewDecision.ACCEPT, "accepted", ("review:evidence",))
    return queue, ReviewAdjudicator().compile(queue, (response,))


def test_relation_requires_k10_acceptance_before_m02_emission():
    first, c1 = candidate("1", object_value="EOR")
    second, c2 = candidate("2", object_value="MCP")
    normalized = normalized_for(first, second)
    groups = {group.representative_candidate_id: group for group in normalized.groups}
    relation = CompiledRelation(
        RelationKey(groups[first.candidate_id].group_id, groups[second.candidate_id].group_id, RelationType.REFINES),
        0.9,
        (RelationEvidence("review", "r1", 0.9, "refines", "terra"),),
        ("terra",),
        RelationDisposition.REVIEW_REQUIRED,
    )
    relation_result = RelationCompilationResult(build(), (relation,))
    adapter = M02StagingAdapter(FakeM02Backend())
    unaccepted = adapter.prepare(*compile_inputs((first, second), (c1, c2), relation_result=relation_result))
    assert unaccepted.eligible_relations == ()
    assert any(d.code == "relation_not_adjudicated_accepted" for d in unaccepted.diagnostics)

    queue, adjudication = accepted_relation_state(first, second, relation)
    accepted = adapter.prepare(*compile_inputs(
        (first, second), (c1, c2), relation_result=relation_result, queue=queue, adjudication=adjudication
    ))
    assert len(accepted.eligible_relations) == 1
    assert accepted.eligible_relations[0].relation_type == "refines"


def test_group_level_relation_is_not_fanned_out_across_repeated_source_records():
    first, c1 = candidate("1", object_value="EOR")
    repeat, c2 = candidate("2", object_value="EOR")
    other, c3 = candidate("3", object_value="MCP")
    normalized = normalized_for(first, repeat, other)
    eor_group = next(g for g in normalized.groups if set(g.candidate_ids) == {first.candidate_id, repeat.candidate_id})
    other_group = next(g for g in normalized.groups if other.candidate_id in g.candidate_ids)
    relation = CompiledRelation(
        RelationKey(eor_group.group_id, other_group.group_id, RelationType.REFINES),
        0.9,
        (RelationEvidence("review", "r1", 0.9, "refines", "terra"),),
        ("terra",),
        RelationDisposition.REVIEW_REQUIRED,
    )
    queue, adjudication = accepted_relation_state(first, other, relation)
    validation = CandidateValidator().validate((c1, c2, c3), (first, repeat, other))
    adapter = M02StagingAdapter(FakeM02Backend())
    prepared = adapter.prepare(
        validation,
        (first, repeat, other),
        (c1, c2, c3),
        normalized,
        RelationCompilationResult(build(), (relation,)),
        TemporalCompilationResult(build(), (), (), (), ()),
        ConflictCompilationResult(build(), (), ()),
        queue,
        adjudication,
    )
    assert prepared.eligible_relations == ()
    assert any(d.code == "ambiguous_group_to_record_relation" for d in prepared.diagnostics)


def test_build_and_validate_delegates_to_verified_backend_and_stays_nonpromotable():
    item, chunk = candidate("1")
    backend = FakeM02Backend()
    adapter = M02StagingAdapter(backend)
    prepared = adapter.prepare(*compile_inputs((item,), (chunk,)))
    artifact = adapter.build_and_validate_pending_bundle(
        prepared,
        bundle_id="k11-test-bundle",
        created_at="2026-08-22T14:00:00Z",
    )
    assert backend.build_calls == 1
    assert backend.validate_calls == 1
    assert artifact.promotable is False
    assert artifact.validation_status == "VALID_PENDING_REVIEW"
    assert artifact.candidate_ids == (item.candidate_id,)
