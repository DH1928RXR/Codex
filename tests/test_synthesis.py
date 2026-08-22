from eor_corpus_compiler.build import BuildIdentity
from eor_corpus_compiler.conflict_model import (
    ConflictCase,
    ConflictCompilationResult,
    ConflictDisposition,
    ConflictKind,
    EffectiveRelation,
)
from eor_corpus_compiler.entity_model import (
    EntityAlias,
    EntityHypothesis,
    EntityRecord,
    EntityRegistrySnapshot,
    EntityResolutionResult,
    EntityStatus,
    HypothesisDisposition,
    ResolutionEvidence,
)
from eor_corpus_compiler.ir import EpistemicType, MemoryClass, TemporalAnchor, TemporalPrecision
from eor_corpus_compiler.projection_model import ProjectionRole
from eor_corpus_compiler.relation_model import (
    CompiledRelation,
    RelationCompilationResult,
    RelationDisposition,
    RelationEvidence,
    RelationKey,
    RelationType,
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
from eor_corpus_compiler.synthesis import SynthesisProjector
from eor_corpus_compiler.temporal_model import (
    Chronology,
    CompiledSupersession,
    SupersessionDisposition,
    SupersessionEvidence,
    TemporalCompilationResult,
    TemporalOccurrence,
)


def build():
    return BuildIdentity("test", "0", "test", "0" * 64, "1" * 64)


def entity(entity_id="entity:dan", name="Dan", status=EntityStatus.ACTIVE):
    alias = EntityAlias(name.casefold(), (name, name.upper()), (f"mention:{name}",))
    return EntityRecord(entity_id, "person", name, (alias,), f"mention:{name}", status)


def assertion(candidate_id, subject_id="entity:dan", object_value="EOR", *, object_kind=ArgumentKind.LITERAL, day="2026-08-21"):
    signature = SemanticSignature(
        SemanticArgumentIdentity(ArgumentKind.ENTITY, subject_id),
        "builds",
        SemanticArgumentIdentity(object_kind, object_value),
        Polarity.POSITIVE,
        EpistemicType.PROJECT_STATE,
        MemoryClass.PROJECT,
    )
    item = NormalizedAssertion(
        candidate_id,
        signature,
        SemanticArgument(ArgumentKind.ENTITY, subject_id, "Dan", "test"),
        SemanticArgument(object_kind, object_value, object_value, "test"),
        f"statement {candidate_id}",
        (f"evidence:{candidate_id}",),
        TemporalAnchor(day, None, TemporalPrecision.DAY, "America/Toronto"),
        0.9,
        1.0,
        0.7,
        0.7,
    )
    group = SemanticGroup(signature, (item.normalized_id,), (candidate_id,), candidate_id)
    return item, group


def inputs(assertions_and_groups, *, entities=None, hypotheses=(), times=None, relations=(), conflicts=(), supersessions=()):
    assertions = tuple(x[0] for x in assertions_and_groups)
    groups = tuple(x[1] for x in assertions_and_groups)
    registry = EntityRegistrySnapshot(tuple(entities or (entity(),)))
    resolution = EntityResolutionResult(build(), registry, tuple(hypotheses))
    normalized = SemanticNormalizationResult(build(), assertions, groups, ())
    occurrences = []
    for index, (item, group) in enumerate(assertions_and_groups):
        occurred = (times[index],) if times and times[index] is not None else ()
        occurrences.append(TemporalOccurrence(item.normalized_id, item.candidate_id, group.group_id, "slot", occurred, item.temporal))
    temporal = TemporalCompilationResult(build(), tuple(occurrences), (), tuple(supersessions), ())
    relation_result = RelationCompilationResult(build(), tuple(relations))
    conflict_result = ConflictCompilationResult(build(), tuple(conflicts), ())
    return resolution, normalized, relation_result, temporal, conflict_result


def test_card_contains_source_bound_proposition_and_aliases():
    item = assertion("candidate:1")
    result = SynthesisProjector().compile(*inputs((item,), times=("2026-08-21T10:00:00-04:00",)))
    card = result.cards[0]
    assert card.canonical_name == "Dan"
    assert "DAN" in card.aliases
    assert card.propositions[0].representative_statement == "statement candidate:1"
    assert card.propositions[0].role == ProjectionRole.SUBJECT
    assert card.latest_observed_occurrence_ids == card.propositions[0].occurrence_ids


def test_entity_can_be_subject_and_object_without_duplication():
    item = assertion("candidate:1", object_value="entity:dan", object_kind=ArgumentKind.ENTITY)
    result = SynthesisProjector().compile(*inputs((item,), times=("2026-08-21T10:00:00-04:00",)))
    card = result.cards[0]
    assert len(card.propositions) == 1
    assert card.propositions[0].role == ProjectionRole.BOTH


def test_latest_observed_uses_source_occurrence_chronology():
    first = assertion("candidate:1", day="2030-01-01")
    second = assertion("candidate:2", day="2027-01-01")
    result = SynthesisProjector().compile(*inputs(
        (first, second),
        times=("2026-08-21T10:00:00-04:00", "2026-08-22T10:00:00-04:00"),
    ))
    card = result.cards[0]
    occurrences = {o.occurrence_id: o for o in inputs((first, second), times=("2026-08-21T10:00:00-04:00", "2026-08-22T10:00:00-04:00"))[3].occurrences}
    assert len(card.latest_observed_occurrence_ids) == 1
    latest = occurrences[card.latest_observed_occurrence_ids[0]]
    assert latest.candidate_id == "candidate:2"


def test_incomparable_latest_observations_are_preserved_as_set():
    first = assertion("candidate:1")
    second = assertion("candidate:2")
    result = SynthesisProjector().compile(*inputs(
        (first, second),
        times=("2026-08-21T10:00:00-04:00", None),
    ))
    card = result.cards[0]
    assert len(card.latest_observed_occurrence_ids) == 2
    assert "latest_observed_not_unique" in card.diagnostics


def test_relation_conflict_and_supersession_refs_are_projected():
    first = assertion("candidate:1")
    second = assertion("candidate:2")
    g1, g2 = first[1], second[1]
    relation = CompiledRelation(
        RelationKey(g1.group_id, g2.group_id, RelationType.REFINES),
        0.9,
        (RelationEvidence("review", "r1", 0.9, "refines", "terra"),),
        ("terra",),
        RelationDisposition.REVIEW_REQUIRED,
    )
    conflict = ConflictCase(
        g1.group_id,
        g2.group_id,
        ConflictKind.SEMANTIC_CONTRADICTION,
        EffectiveRelation.OVERLAP,
        0.9,
        (relation.relation_id,),
        (),
        ConflictDisposition.REVIEW_REQUIRED,
    )
    supersession = CompiledSupersession(
        first[0].normalized_id,
        second[0].normalized_id,
        Chronology.BEFORE,
        0.9,
        (SupersessionEvidence("review", "s1", 0.9, "supersedes", "terra"),),
        ("terra",),
        SupersessionDisposition.REVIEW_REQUIRED,
    )
    result = SynthesisProjector().compile(*inputs(
        (first, second),
        times=("2026-08-21T10:00:00-04:00", "2026-08-22T10:00:00-04:00"),
        relations=(relation,), conflicts=(conflict,), supersessions=(supersession,),
    ))
    card = result.cards[0]
    assert relation.relation_id in card.relation_ids
    assert conflict.conflict_id in card.conflict_ids
    assert supersession.supersession_id in card.supersession_ids


def test_unresolved_identity_hypothesis_is_visible_on_candidate_entity_card():
    dan = entity()
    hypothesis = EntityHypothesis(
        "mention:emperor",
        dan.entity_id,
        0.85,
        (ResolutionEvidence("context", "source:1", 0.85, "possible alias", "terra"),),
        HypothesisDisposition.REVIEW_REQUIRED,
    )
    item = assertion("candidate:1")
    result = SynthesisProjector().compile(*inputs(
        (item,), entities=(dan,), hypotheses=(hypothesis,), times=("2026-08-21T10:00:00-04:00",),
    ))
    assert hypothesis.hypothesis_id in result.cards[0].unresolved_hypothesis_ids


def test_redirected_entity_does_not_get_projection_card():
    active = entity()
    redirected = entity("entity:old", "Old Dan", EntityStatus.REDIRECTED)
    item = assertion("candidate:1")
    result = SynthesisProjector().compile(*inputs(
        (item,), entities=(active, redirected), times=("2026-08-21T10:00:00-04:00",),
    ))
    assert [card.entity_id for card in result.cards] == [active.entity_id]
