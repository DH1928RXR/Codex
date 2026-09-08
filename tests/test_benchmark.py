from hashlib import sha256

from eor_corpus_compiler.benchmark import BenchmarkAuditor, CorpusScaleProbe
from eor_corpus_compiler.benchmark_model import BenchmarkStatus, QualityThresholds
from eor_corpus_compiler.build import BuildIdentity
from eor_corpus_compiler.conflict_model import ConflictCompilationResult
from eor_corpus_compiler.entity_model import (
    EntityHypothesis,
    EntityRecord,
    EntityRegistrySnapshot,
    EntityResolutionResult,
    EntityStatus,
    HypothesisDisposition,
    ResolutionEvidence,
)
from eor_corpus_compiler.ir import (
    CandidateAssertion,
    EpistemicType,
    EvidenceSpan,
    MemoryClass,
    ModelLineage,
    TemporalAnchor,
    TemporalPrecision,
)
from eor_corpus_compiler.m02_adapter_model import (
    M02CandidateDisposition,
    M02Eligibility,
    M02PreparationResult,
)
from eor_corpus_compiler.projection_model import SynthesisProjectionResult
from eor_corpus_compiler.relation_model import RelationCompilationResult
from eor_corpus_compiler.review_model import ReviewAuthority, ReviewItem, ReviewKind, ReviewQueue
from eor_corpus_compiler.semantic_model import SemanticNormalizationResult
from eor_corpus_compiler.temporal_model import TemporalCompilationResult
from eor_corpus_compiler.validator import CandidateDisposition, ValidationResult


def build():
    return BuildIdentity("test", "0", "test", "0" * 64, "1" * 64)


def empty_inputs(*, review_items=(), m02_dispositions=()):
    return (
        ValidationResult(build(), (), (), ()),
        EntityResolutionResult(build(), EntityRegistrySnapshot(), ()),
        SemanticNormalizationResult(build(), (), (), ()),
        RelationCompilationResult(build(), ()),
        TemporalCompilationResult(build(), (), (), (), ()),
        ConflictCompilationResult(build(), (), ()),
        SynthesisProjectionResult(build(), (), ()),
        ReviewQueue(build(), tuple(review_items)),
        M02PreparationResult(build(), "cap:test", (), tuple(m02_dispositions), (), ()),
    )


def candidate():
    evidence = EvidenceSpan("source", "chat_message", "conv", "msg", "chunk", "Dan", "exact text", source_sha256=sha256(b"exact text").hexdigest())
    return CandidateAssertion(
        "Dan has a goal.", "Dan", "has_goal", "goal", EpistemicType.GOAL, MemoryClass.GOAL,
        (evidence,), TemporalAnchor(None, None, TemporalPrecision.UNKNOWN, "America/Toronto"), (), (),
        ModelLineage("test", "model", "extractor", "contract", "1"), 0.9, 1.0, 0.8, 0.8,
    )


def unresolved_hypothesis():
    evidence = ResolutionEvidence("synthetic", "mention:test", 0.9, "synthetic unresolved identity")
    return EntityHypothesis(
        "mention:test",
        "entity:candidate",
        0.9,
        (evidence,),
        HypothesisDisposition.REVIEW_REQUIRED,
    )


def active_entity(entity_id: str):
    return EntityRecord(entity_id, None, entity_id, (), f"mention:{entity_id}", EntityStatus.ACTIVE)


def test_empty_audit_passes_when_no_threshold_is_violated():
    report = BenchmarkAuditor().compile(*empty_inputs())
    assert report.status == BenchmarkStatus.PASS
    assert report.findings == ()
    assert report.metrics.candidates_total == 0


def test_configured_quality_thresholds_fail_closed():
    item = candidate()
    validation = ValidationResult(build(), (), (CandidateDisposition(item, False, ()),), ())
    dan_review = ReviewItem(
        ReviewKind.CONFLICT, "conflict:1", 0.5, 0.5, 1.0, 1.0, ReviewAuthority.DAN, ("test",), (), ()
    )
    m02_disposition = M02CandidateDisposition(item.candidate_id, M02Eligibility.BLOCKED_SOURCE_EXACTNESS, ("test",))
    inputs = list(empty_inputs(review_items=(dan_review,), m02_dispositions=(m02_disposition,)))
    inputs[0] = validation
    thresholds = QualityThresholds(max_quarantine_rate=0.2, max_m02_block_rate=0.2, max_dan_review_rate=0.2)
    report = BenchmarkAuditor(thresholds=thresholds).compile(*inputs)
    assert report.status == BenchmarkStatus.FAIL
    assert {finding.metric for finding in report.findings} == {"quarantine_rate", "m02_block_rate", "dan_review_rate"}


def test_positive_unresolved_hypotheses_fail_with_zero_active_entities():
    inputs = list(empty_inputs())
    inputs[1] = EntityResolutionResult(build(), EntityRegistrySnapshot(), (unresolved_hypothesis(),))
    thresholds = QualityThresholds(max_unresolved_entity_hypotheses_per_entity=100.0)

    report = BenchmarkAuditor(thresholds=thresholds).compile(*inputs)

    assert report.metrics.active_entities == 0
    assert report.metrics.unresolved_entity_hypotheses == 1
    assert report.metrics.unresolved_entity_hypotheses_per_entity == 0.0
    assert report.status == BenchmarkStatus.FAIL
    assert len(report.findings) == 1
    assert report.findings[0].metric == "unresolved_entity_hypotheses_per_entity"
    assert "zero active entities" in report.findings[0].message


def test_zero_unresolved_hypotheses_with_zero_active_entities_is_vacuous_pass():
    thresholds = QualityThresholds(max_unresolved_entity_hypotheses_per_entity=0.0)

    report = BenchmarkAuditor(thresholds=thresholds).compile(*empty_inputs())

    assert report.metrics.active_entities == 0
    assert report.metrics.unresolved_entity_hypotheses == 0
    assert report.metrics.unresolved_entity_hypotheses_per_entity == 0.0
    assert report.status == BenchmarkStatus.PASS
    assert report.findings == ()


def test_unresolved_hypothesis_rate_with_active_entities_is_unchanged():
    registry = EntityRegistrySnapshot(entities=(active_entity("entity:one"), active_entity("entity:two")))
    inputs = list(empty_inputs())
    inputs[1] = EntityResolutionResult(build(), registry, (unresolved_hypothesis(),))
    thresholds = QualityThresholds(max_unresolved_entity_hypotheses_per_entity=0.5)

    report = BenchmarkAuditor(thresholds=thresholds).compile(*inputs)

    assert report.metrics.active_entities == 2
    assert report.metrics.unresolved_entity_hypotheses == 1
    assert report.metrics.unresolved_entity_hypotheses_per_entity == 0.5
    assert report.status == BenchmarkStatus.PASS
    assert report.findings == ()


def test_597_conversation_scale_shape_matches_reference_dag():
    report = CorpusScaleProbe().run(597)
    assert report.conversation_count == 597
    assert report.task_count == 1799
    assert report.map_task_count == 1791
    assert report.global_task_count == 8
    assert report.wave_count == 10
    assert report.run_task_count == 1799
    assert report.reuse_task_count == 0


def test_single_conversation_change_reuses_1788_of_1799_tasks_initially():
    report = CorpusScaleProbe().run(597)
    assert report.single_change_run_task_count == 11
    assert report.single_change_reuse_task_count == 1788


def test_scale_probe_is_deterministic():
    first = CorpusScaleProbe().run(25)
    second = CorpusScaleProbe().run(25)
    assert first == second
    assert first.scale_report_id == second.scale_report_id
