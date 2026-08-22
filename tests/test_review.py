import pytest

from eor_corpus_compiler.build import BuildIdentity
from eor_corpus_compiler.conflict_model import (
    ConflictCase,
    ConflictCompilationResult,
    ConflictDisposition,
    ConflictKind,
    EffectiveRelation,
)
from eor_corpus_compiler.entity_model import EntityRegistrySnapshot, EntityResolutionResult
from eor_corpus_compiler.ir import EpistemicType, MemoryClass, TemporalAnchor, TemporalPrecision
from eor_corpus_compiler.projection_model import EntityProjectionCard, ProjectionDiagnostic, SynthesisProjectionResult
from eor_corpus_compiler.relation_model import (
    CompiledRelation,
    RelationCompilationResult,
    RelationDisposition,
    RelationEvidence,
    RelationKey,
    RelationType,
)
from eor_corpus_compiler.review import ReviewAdjudicator, ReviewRouter
from eor_corpus_compiler.review_model import (
    AdjudicationDisposition,
    ReviewAuthority,
    ReviewDecision,
    ReviewKind,
    ReviewPolicy,
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


def build():
    return BuildIdentity("test", "0", "test", "0" * 64, "1" * 64)


def group(candidate_id, object_value, impact=0.5):
    signature = SemanticSignature(
        SemanticArgumentIdentity(ArgumentKind.ENTITY, "entity:dan"),
        "prefers",
        SemanticArgumentIdentity(ArgumentKind.LITERAL, object_value),
        Polarity.POSITIVE,
        EpistemicType.PREFERENCE,
        MemoryClass.PREFERENCE,
    )
    assertion = NormalizedAssertion(
        candidate_id,
        signature,
        SemanticArgument(ArgumentKind.ENTITY, "entity:dan", "Dan", "test"),
        SemanticArgument(ArgumentKind.LITERAL, object_value, object_value, "literal"),
        f"Dan prefers {object_value}",
        (f"evidence:{candidate_id}",),
        TemporalAnchor("2026-08-22", None, TemporalPrecision.DAY, "America/Toronto"),
        0.9,
        1.0,
        impact,
        impact,
    )
    return assertion, SemanticGroup(signature, (assertion.normalized_id,), (candidate_id,), candidate_id)


def state(*, impact=0.5, relation_disposition=None, conflict_disposition=None, projection_diagnostic=False):
    left = group("candidate:left", "A", impact)
    right = group("candidate:right", "B", impact)
    normalized = SemanticNormalizationResult(build(), (left[0], right[0]), (left[1], right[1]), ())
    entity_resolution = EntityResolutionResult(build(), EntityRegistrySnapshot(), ())

    relations = []
    relation = None
    if relation_disposition is not None:
        relation = CompiledRelation(
            RelationKey(left[1].group_id, right[1].group_id, RelationType.REFINES),
            0.75,
            (RelationEvidence("review", "relation:1", 0.75, "possible refinement", "terra"),),
            ("terra",),
            relation_disposition,
        )
        relations.append(relation)
    relation_result = RelationCompilationResult(build(), tuple(relations))

    conflicts = []
    conflict = None
    if conflict_disposition is not None:
        source_relation_id = relation.relation_id if relation else "relation:structural"
        conflict = ConflictCase(
            left[1].group_id,
            right[1].group_id,
            ConflictKind.SEMANTIC_CONTRADICTION,
            EffectiveRelation.OVERLAP if conflict_disposition != ConflictDisposition.UNKNOWN_TEMPORAL else EffectiveRelation.UNKNOWN,
            0.90,
            (source_relation_id,),
            (),
            conflict_disposition,
        )
        conflicts.append(conflict)
    conflict_result = ConflictCompilationResult(build(), tuple(conflicts), ())

    temporal = TemporalCompilationResult(build(), (), (), (), ())
    card = EntityProjectionCard(
        "entity:dan", "person", "Dan", (), (), (), (), (), (), (),
        ("latest_observed_not_unique",) if projection_diagnostic else (),
    )
    projection_diags = (
        ProjectionDiagnostic("projection_test", "test diagnostic", "entity:dan", "ref:1"),
    ) if projection_diagnostic else ()
    projections = SynthesisProjectionResult(build(), (card,), projection_diags)
    return entity_resolution, normalized, relation_result, temporal, conflict_result, projections, relation, conflict


def test_low_impact_relation_routes_to_terra():
    data = state(impact=0.2, relation_disposition=RelationDisposition.SUGGESTED)
    queue = ReviewRouter().compile(*data[:6])
    item = next(i for i in queue.items if i.kind == ReviewKind.RELATION)
    assert item.route == ReviewAuthority.TERRA


def test_conflict_routes_at_least_to_sol():
    data = state(impact=0.4, conflict_disposition=ConflictDisposition.REVIEW_REQUIRED)
    queue = ReviewRouter().compile(*data[:6])
    item = next(i for i in queue.items if i.kind == ReviewKind.CONFLICT)
    assert item.route == ReviewAuthority.SOL


def test_high_impact_conflict_routes_to_dan():
    policy = ReviewPolicy(dan_impact_threshold=0.70)
    data = state(impact=0.95, conflict_disposition=ConflictDisposition.REVIEW_REQUIRED)
    queue = ReviewRouter(policy=policy).compile(*data[:6])
    item = next(i for i in queue.items if i.kind == ReviewKind.CONFLICT)
    assert item.route == ReviewAuthority.DAN
    assert "high_consequence_high_impact" in item.reason_codes


def test_temporally_disjoint_conflict_is_not_review_queued():
    data = state(impact=0.8, conflict_disposition=ConflictDisposition.TEMPORALLY_DISJOINT)
    queue = ReviewRouter().compile(*data[:6])
    assert not any(i.kind == ReviewKind.CONFLICT for i in queue.items)


def test_projection_diagnostics_are_routed_without_becoming_truth_claims():
    data = state(projection_diagnostic=True)
    queue = ReviewRouter().compile(*data[:6])
    assert sum(i.kind == ReviewKind.PROJECTION_DIAGNOSTIC for i in queue.items) == 2


def sol_queue():
    data = state(impact=0.4, conflict_disposition=ConflictDisposition.REVIEW_REQUIRED)
    queue = ReviewRouter().compile(*data[:6])
    item = next(i for i in queue.items if i.kind == ReviewKind.CONFLICT)
    assert item.route == ReviewAuthority.SOL
    return queue, item


def test_lower_authority_final_response_cannot_control_item():
    queue, item = sol_queue()
    response = ReviewResponse(item.review_item_id, "terra", ReviewAuthority.TERRA, ReviewDecision.ACCEPT, "looks right", ("evidence:1",))
    result = ReviewAdjudicator().compile(queue, (response,))
    record = next(r for r in result.records if r.review_item_id == item.review_item_id)
    assert record.disposition == AdjudicationDisposition.PENDING
    assert record.controlling_response_id is None


def test_required_authority_can_finalize_with_evidence():
    queue, item = sol_queue()
    response = ReviewResponse(item.review_item_id, "sol", ReviewAuthority.SOL, ReviewDecision.ACCEPT, "adjudicated", ("evidence:1",))
    result = ReviewAdjudicator().compile(queue, (response,))
    record = next(r for r in result.records if r.review_item_id == item.review_item_id)
    assert record.disposition == AdjudicationDisposition.ACCEPTED
    assert record.controlling_response_id == response.response_id


def test_conflicting_same_authority_final_responses_remain_pending():
    queue, item = sol_queue()
    accept = ReviewResponse(item.review_item_id, "sol-a", ReviewAuthority.SOL, ReviewDecision.ACCEPT, "accept", ("evidence:a",))
    reject = ReviewResponse(item.review_item_id, "sol-b", ReviewAuthority.SOL, ReviewDecision.REJECT, "reject", ("evidence:b",))
    result = ReviewAdjudicator().compile(queue, (accept, reject))
    record = next(r for r in result.records if r.review_item_id == item.review_item_id)
    assert record.disposition == AdjudicationDisposition.PENDING
    assert record.reason == "conflicting_same_authority_final_responses"


def test_higher_authority_response_controls_lower_authority_disagreement():
    queue, item = sol_queue()
    sol_reject = ReviewResponse(item.review_item_id, "sol", ReviewAuthority.SOL, ReviewDecision.REJECT, "sol rejects", ("evidence:s",))
    dan_accept = ReviewResponse(item.review_item_id, "dan", ReviewAuthority.DAN, ReviewDecision.ACCEPT, "dan accepts", ("evidence:d",))
    result = ReviewAdjudicator().compile(queue, (sol_reject, dan_accept))
    record = next(r for r in result.records if r.review_item_id == item.review_item_id)
    assert record.disposition == AdjudicationDisposition.ACCEPTED
    assert record.final_authority == ReviewAuthority.DAN
    assert record.controlling_response_id == dan_accept.response_id


def test_response_to_unknown_review_item_is_rejected():
    queue, _ = sol_queue()
    response = ReviewResponse("reviewitem:missing", "sol", ReviewAuthority.SOL, ReviewDecision.DEFER, "missing item")
    with pytest.raises(ValueError):
        ReviewAdjudicator().compile(queue, (response,))
