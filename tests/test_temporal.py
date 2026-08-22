from eor_corpus_compiler.build import BuildIdentity
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
from eor_corpus_compiler.temporal import TemporalCompiler
from eor_corpus_compiler.temporal_model import (
    Chronology,
    SupersessionDisposition,
    SupersessionEvidence,
    SupersessionProposal,
    TemporalPolicy,
)


def fixture(
    suffix: str,
    *,
    object_value: str,
    occurred_at: str | None,
    effective_start: str,
    effective_proxy: bool = False,
    predicate: str = "prefers",
):
    chunk_id = f"chunk:{suffix}"
    evidence = EvidenceSpan(
        f"source:{suffix}",
        "chat_message",
        f"conversation:{suffix}",
        f"message:{suffix}",
        chunk_id,
        "Dan",
        f"evidence {suffix}",
    )
    anchor = TemporalAnchor(
        effective_start,
        None,
        TemporalPrecision.DAY,
        "America/Toronto",
        is_proxy=effective_proxy,
        proxy_reason="artifact timestamp only" if effective_proxy else None,
    )
    candidate = CandidateAssertion(
        statement=f"Dan {predicate} {object_value}",
        subject="Dan",
        predicate=predicate,
        object=object_value,
        epistemic_type=EpistemicType.BELIEF,
        memory_class=MemoryClass.PREFERENCE,
        evidence=(evidence,),
        temporal=anchor,
        entity_mentions=(),
        tags=("test",),
        lineage=ModelLineage("test", "model", "extractor", "contract", "1"),
        extractor_confidence=0.9,
        source_origin_probability=1.0,
        importance=0.7,
        durability=0.7,
    )
    chunk = CorpusChunk(
        chunk_id,
        f"source:{suffix}",
        f"conversation:{suffix}",
        "test",
        "Dan",
        occurred_at,
        f"evidence {suffix}",
    )
    subject_identity = SemanticArgumentIdentity(ArgumentKind.ENTITY, "entity:dan")
    object_identity = SemanticArgumentIdentity(ArgumentKind.LITERAL, object_value.casefold())
    signature = SemanticSignature(
        subject_identity,
        predicate,
        object_identity,
        Polarity.POSITIVE,
        EpistemicType.BELIEF,
        MemoryClass.PREFERENCE,
    )
    assertion = NormalizedAssertion(
        candidate.candidate_id,
        signature,
        SemanticArgument(ArgumentKind.ENTITY, "entity:dan", "Dan", "test"),
        SemanticArgument(ArgumentKind.LITERAL, object_value.casefold(), object_value, "literal"),
        candidate.statement,
        (evidence.evidence_id,),
        anchor,
        0.9,
        1.0,
        0.7,
        0.7,
    )
    group = SemanticGroup(signature, (assertion.normalized_id,), (candidate.candidate_id,), candidate.candidate_id)
    return candidate, chunk, assertion, group


def normalized(*items):
    assertions = tuple(item[2] for item in items)
    groups = tuple(item[3] for item in items)
    build = BuildIdentity("test", "0", "test", "0" * 64, "1" * 64)
    return SemanticNormalizationResult(build, assertions, groups, ())


def evidence(score=0.9):
    return (SupersessionEvidence("review", "review:1", score, "later statement replaces earlier preference", "terra"),)


def test_source_occurrence_and_effective_time_remain_distinct():
    item = fixture("1", object_value="A", occurred_at="2026-08-22T10:00:00-04:00", effective_start="2028-01-01")
    out = TemporalCompiler().compile(normalized(item), (item[0],), (item[1],))
    occurrence = out.occurrences[0]
    assert occurrence.source_occurrence_times == ("2026-08-22T10:00:00-04:00",)
    assert occurrence.effective_anchor.start == "2028-01-01"


def test_state_slot_orders_occurrences_by_source_time_not_effective_time():
    later_effective = fixture("1", object_value="A", occurred_at="2026-08-21T10:00:00-04:00", effective_start="2030-01-01")
    earlier_effective = fixture("2", object_value="B", occurred_at="2026-08-22T10:00:00-04:00", effective_start="2027-01-01")
    out = TemporalCompiler().compile(
        normalized(later_effective, earlier_effective),
        (later_effective[0], earlier_effective[0]),
        (later_effective[1], earlier_effective[1]),
    )
    occurrences = {o.occurrence_id: o for o in out.occurrences}
    ordered = [occurrences[oid].candidate_id for oid in out.state_slots[0].occurrence_ids]
    assert ordered == [later_effective[0].candidate_id, earlier_effective[0].candidate_id]


def test_no_supersession_is_inferred_from_recency_alone():
    one = fixture("1", object_value="A", occurred_at="2026-08-21T10:00:00-04:00", effective_start="2026-08-21")
    two = fixture("2", object_value="B", occurred_at="2026-08-22T10:00:00-04:00", effective_start="2026-08-22")
    out = TemporalCompiler().compile(normalized(one, two), (one[0], two[0]), (one[1], two[1]))
    assert out.supersessions == ()


def test_forward_high_confidence_supersession_requires_review():
    one = fixture("1", object_value="A", occurred_at="2026-08-21T10:00:00-04:00", effective_start="2026-08-21")
    two = fixture("2", object_value="B", occurred_at="2026-08-22T10:00:00-04:00", effective_start="2026-08-22")
    proposal = SupersessionProposal(one[2].normalized_id, two[2].normalized_id, "terra", evidence())
    out = TemporalCompiler().compile(normalized(one, two), (one[0], two[0]), (one[1], two[1]), supersession_proposals=(proposal,))
    result = out.supersessions[0]
    assert result.chronology == Chronology.BEFORE
    assert result.disposition == SupersessionDisposition.REVIEW_REQUIRED


def test_reverse_chronology_is_blocked():
    one = fixture("1", object_value="A", occurred_at="2026-08-22T10:00:00-04:00", effective_start="2026-08-22")
    two = fixture("2", object_value="B", occurred_at="2026-08-21T10:00:00-04:00", effective_start="2026-08-21")
    proposal = SupersessionProposal(one[2].normalized_id, two[2].normalized_id, "terra", evidence())
    out = TemporalCompiler().compile(normalized(one, two), (one[0], two[0]), (one[1], two[1]), supersession_proposals=(proposal,))
    assert out.supersessions[0].disposition == SupersessionDisposition.BLOCKED_CHRONOLOGY


def test_same_proposition_repetition_cannot_supersede_itself():
    one = fixture("1", object_value="A", occurred_at="2026-08-21T10:00:00-04:00", effective_start="2026-08-21")
    two = fixture("2", object_value="A", occurred_at="2026-08-22T10:00:00-04:00", effective_start="2026-08-22")
    proposal = SupersessionProposal(one[2].normalized_id, two[2].normalized_id, "terra", evidence())
    out = TemporalCompiler().compile(normalized(one, two), (one[0], two[0]), (one[1], two[1]), supersession_proposals=(proposal,))
    assert out.supersessions[0].disposition == SupersessionDisposition.BLOCKED_SAME_PROPOSITION


def test_state_slot_mismatch_blocks_supersession():
    one = fixture("1", object_value="A", occurred_at="2026-08-21T10:00:00-04:00", effective_start="2026-08-21", predicate="prefers")
    two = fixture("2", object_value="B", occurred_at="2026-08-22T10:00:00-04:00", effective_start="2026-08-22", predicate="owns")
    proposal = SupersessionProposal(one[2].normalized_id, two[2].normalized_id, "terra", evidence())
    out = TemporalCompiler().compile(normalized(one, two), (one[0], two[0]), (one[1], two[1]), supersession_proposals=(proposal,))
    assert out.supersessions[0].disposition == SupersessionDisposition.BLOCKED_SLOT_MISMATCH


def test_missing_source_time_is_diagnosed_and_can_remain_suggested():
    one = fixture("1", object_value="A", occurred_at=None, effective_start="2026-08-21")
    two = fixture("2", object_value="B", occurred_at=None, effective_start="2026-08-22")
    proposal = SupersessionProposal(one[2].normalized_id, two[2].normalized_id, "terra", evidence())
    out = TemporalCompiler(policy=TemporalPolicy(require_known_forward_chronology_for_review=True)).compile(
        normalized(one, two), (one[0], two[0]), (one[1], two[1]), supersession_proposals=(proposal,)
    )
    assert out.supersessions[0].chronology == Chronology.UNKNOWN
    assert out.supersessions[0].disposition == SupersessionDisposition.SUGGESTED
    assert sum(d.code == "missing_source_occurrence_time" for d in out.diagnostics) == 2


def test_proxy_effective_time_is_preserved_and_diagnosed():
    item = fixture("1", object_value="A", occurred_at="2026-08-22T10:00:00-04:00", effective_start="2026-08-22", effective_proxy=True)
    out = TemporalCompiler().compile(normalized(item), (item[0],), (item[1],))
    assert out.occurrences[0].effective_anchor.is_proxy is True
    assert any(d.code == "effective_time_is_proxy" for d in out.diagnostics)
