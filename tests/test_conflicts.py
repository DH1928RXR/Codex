from eor_corpus_compiler.build import BuildIdentity
from eor_corpus_compiler.conflict_model import (
    ConflictDisposition,
    ConflictKind,
    EffectiveRelation,
)
from eor_corpus_compiler.conflicts import ConflictCompiler, compare_effective_anchors, effective_interval
from eor_corpus_compiler.ir import TemporalAnchor, TemporalPrecision
from eor_corpus_compiler.relation_model import (
    CompiledRelation,
    RelationCompilationResult,
    RelationDisposition,
    RelationEvidence,
    RelationKey,
    RelationType,
)
from eor_corpus_compiler.temporal_model import (
    Chronology,
    CompiledSupersession,
    SupersessionDisposition,
    SupersessionEvidence,
    TemporalCompilationResult,
    TemporalOccurrence,
)


def build(stage="test"):
    return BuildIdentity(stage, "0", "test", "0" * 64, "1" * 64)


def anchor(start, *, precision=TemporalPrecision.DAY, end=None, proxy=False):
    return TemporalAnchor(
        start,
        end,
        precision,
        "America/Toronto",
        is_proxy=proxy,
        proxy_reason="proxy" if proxy else None,
    )


def occurrence(assertion_id, group_id, temporal_anchor):
    return TemporalOccurrence(
        assertion_id,
        f"candidate:{assertion_id}",
        group_id,
        "slot:1",
        ("2026-08-22T10:00:00-04:00",),
        temporal_anchor,
    )


def relation(left, right, relation_type=RelationType.POLARITY_OPPOSES, score=1.0):
    key = RelationKey(left, right, relation_type)
    evidence = (RelationEvidence("test", "source:1", score, "test evidence", "K06.rule"),)
    return CompiledRelation(key, score, evidence, ("K06.rule",), RelationDisposition.STRUCTURAL if relation_type == RelationType.POLARITY_OPPOSES else RelationDisposition.REVIEW_REQUIRED)


def relation_result(*relations):
    return RelationCompilationResult(build("relations"), tuple(relations))


def temporal_result(*occurrences, supersessions=()):
    return TemporalCompilationResult(build("temporal"), tuple(occurrences), (), tuple(supersessions), ())


def test_overlapping_polarity_opposition_requires_review():
    rel = relation("group:a", "group:b")
    temporal = temporal_result(
        occurrence("a1", "group:a", anchor("2026-01-01", end="2026-12-31", precision=TemporalPrecision.RANGE)),
        occurrence("b1", "group:b", anchor("2026-06-01", end="2026-06-30", precision=TemporalPrecision.RANGE)),
    )
    out = ConflictCompiler().compile(relation_result(rel), temporal)
    case = out.conflicts[0]
    assert case.kind == ConflictKind.POLARITY_OPPOSITION
    assert case.effective_relation == EffectiveRelation.OVERLAP
    assert case.disposition == ConflictDisposition.REVIEW_REQUIRED


def test_disjoint_effective_periods_are_not_flattened_into_simultaneous_contradiction():
    rel = relation("group:a", "group:b")
    temporal = temporal_result(
        occurrence("a1", "group:a", anchor("2025", precision=TemporalPrecision.YEAR)),
        occurrence("b1", "group:b", anchor("2026", precision=TemporalPrecision.YEAR)),
    )
    out = ConflictCompiler().compile(relation_result(rel), temporal)
    case = out.conflicts[0]
    assert case.effective_relation == EffectiveRelation.DISJOINT
    assert case.disposition == ConflictDisposition.TEMPORALLY_DISJOINT


def test_proxy_effective_time_keeps_conflict_temporally_unknown():
    rel = relation("group:a", "group:b")
    temporal = temporal_result(
        occurrence("a1", "group:a", anchor("2026-01-01", proxy=True)),
        occurrence("b1", "group:b", anchor("2026-01-01")),
    )
    out = ConflictCompiler().compile(relation_result(rel), temporal)
    assert out.conflicts[0].effective_relation == EffectiveRelation.UNKNOWN
    assert out.conflicts[0].disposition == ConflictDisposition.UNKNOWN_TEMPORAL


def test_reviewable_supersession_surfaces_change_over_time_candidate():
    rel = relation("group:a", "group:b")
    left = occurrence("assertion:a", "group:a", anchor("2025", precision=TemporalPrecision.YEAR))
    right = occurrence("assertion:b", "group:b", anchor("2026", precision=TemporalPrecision.YEAR))
    sup_evidence = (SupersessionEvidence("review", "source:sup", 0.9, "later belief replaces earlier", "terra"),)
    supersession = CompiledSupersession(
        "assertion:a",
        "assertion:b",
        Chronology.BEFORE,
        0.9,
        sup_evidence,
        ("terra",),
        SupersessionDisposition.REVIEW_REQUIRED,
    )
    out = ConflictCompiler().compile(relation_result(rel), temporal_result(left, right, supersessions=(supersession,)))
    case = out.conflicts[0]
    assert case.disposition == ConflictDisposition.CHANGE_OVER_TIME_CANDIDATE
    assert case.source_supersession_ids == (supersession.supersession_id,)


def test_semantic_contradiction_retains_its_kind():
    rel = relation("group:a", "group:b", RelationType.CONTRADICTS, 0.9)
    temporal = temporal_result(
        occurrence("a1", "group:a", anchor("2026-01-01")),
        occurrence("b1", "group:b", anchor("2026-01-01")),
    )
    out = ConflictCompiler().compile(relation_result(rel), temporal)
    assert out.conflicts[0].kind == ConflictKind.SEMANTIC_CONTRADICTION


def test_non_conflict_relations_are_ignored():
    rel = relation("group:a", "group:b", RelationType.SUPPORTS, 0.9)
    out = ConflictCompiler().compile(relation_result(rel), temporal_result())
    assert out.conflicts == ()


def test_missing_temporal_occurrence_is_diagnosed():
    rel = relation("group:a", "group:b")
    temporal = temporal_result(occurrence("a1", "group:a", anchor("2026-01-01")))
    out = ConflictCompiler().compile(relation_result(rel), temporal)
    assert out.conflicts[0].disposition == ConflictDisposition.UNKNOWN_TEMPORAL
    assert any(d.code == "missing_temporal_occurrence" for d in out.diagnostics)


def test_month_and_year_intervals_are_compared_conservatively():
    yearly = anchor("2026", precision=TemporalPrecision.YEAR)
    monthly = anchor("2026-06", precision=TemporalPrecision.MONTH)
    assert effective_interval(yearly) is not None
    assert compare_effective_anchors((yearly,), (monthly,)) == EffectiveRelation.OVERLAP
