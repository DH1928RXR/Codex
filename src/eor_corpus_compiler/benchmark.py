from __future__ import annotations

from hashlib import sha256

from .benchmark_model import (
    BenchmarkFinding,
    BenchmarkMetrics,
    BenchmarkReport,
    BenchmarkStatus,
    CorpusScaleReport,
    QualityThresholds,
)
from .build import BuildIdentity, canonical_json
from .conflict_model import ConflictCompilationResult
from .entity_model import EntityResolutionResult, EntityStatus, HypothesisDisposition
from .m02_adapter_model import M02Eligibility, M02PreparationResult
from .projection_model import SynthesisProjectionResult
from .relation_model import RelationCompilationResult
from .review_model import ReviewAuthority, ReviewQueue
from .scheduler import CorpusTaskGraphBuilder, IncrementalScheduler
from .scheduler_model import PlanDisposition
from .semantic_model import SemanticNormalizationResult
from .temporal_model import TemporalCompilationResult
from .validator import ValidationResult


class BenchmarkAuditor:
    """K13 aggregate audit over compiler outputs; contains no personal source text."""

    def __init__(self, *, compiler_version: str = "0.1.0", thresholds: QualityThresholds | None = None):
        self.compiler_version = compiler_version
        self.thresholds = thresholds or QualityThresholds()

    @staticmethod
    def _rate(numerator: int, denominator: int) -> float:
        return 0.0 if denominator == 0 else numerator / denominator

    def compile(
        self,
        validation: ValidationResult,
        entity_resolution: EntityResolutionResult,
        normalized: SemanticNormalizationResult,
        relations: RelationCompilationResult,
        temporal: TemporalCompilationResult,
        conflicts: ConflictCompilationResult,
        projections: SynthesisProjectionResult,
        review_queue: ReviewQueue,
        m02: M02PreparationResult,
    ) -> BenchmarkReport:
        payload = {
            "validation": validation,
            "entity_resolution": entity_resolution,
            "normalized": normalized,
            "relations": relations,
            "temporal": temporal,
            "conflicts": conflicts,
            "projections": projections,
            "review_queue": review_queue,
            "m02": m02,
        }
        input_hash = sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        config_hash = sha256(canonical_json(self.thresholds).encode("utf-8")).hexdigest()
        build = BuildIdentity(
            "K13.benchmark_audit",
            self.compiler_version,
            "eor.corpus_benchmark_report.v0",
            config_hash,
            input_hash,
        )

        candidate_total = len(validation.accepted) + len(validation.quarantined)
        active_entities = sum(1 for entity in entity_resolution.registry.entities if entity.status == EntityStatus.ACTIVE)
        unresolved_hypotheses = sum(
            1 for hypothesis in entity_resolution.hypotheses
            if hypothesis.disposition != HypothesisDisposition.BLOCKED
        )
        missing_source_time = sum(1 for occurrence in temporal.occurrences if not occurrence.source_occurrence_times)
        terra = sum(1 for item in review_queue.items if item.route == ReviewAuthority.TERRA)
        sol = sum(1 for item in review_queue.items if item.route == ReviewAuthority.SOL)
        dan = sum(1 for item in review_queue.items if item.route == ReviewAuthority.DAN)
        m02_total = len(m02.candidate_dispositions)
        m02_eligible = sum(1 for item in m02.candidate_dispositions if item.eligibility == M02Eligibility.ELIGIBLE)
        m02_blocked = m02_total - m02_eligible

        metrics = BenchmarkMetrics(
            candidate_total,
            len(validation.accepted),
            len(validation.quarantined),
            self._rate(len(validation.quarantined), candidate_total),
            active_entities,
            unresolved_hypotheses,
            self._rate(unresolved_hypotheses, active_entities),
            len(normalized.groups),
            len(normalized.assertions),
            len(relations.relations),
            len(temporal.occurrences),
            missing_source_time,
            self._rate(missing_source_time, len(temporal.occurrences)),
            len(conflicts.conflicts),
            len(projections.cards),
            len(review_queue.items),
            terra,
            sol,
            dan,
            self._rate(dan, len(review_queue.items)),
            m02_total,
            m02_eligible,
            m02_blocked,
            self._rate(m02_blocked, m02_total),
            len(m02.eligible_relations),
        )

        findings: list[BenchmarkFinding] = []
        checks = (
            ("quarantine_rate", metrics.quarantine_rate, self.thresholds.max_quarantine_rate),
            (
                "unresolved_entity_hypotheses_per_entity",
                metrics.unresolved_entity_hypotheses_per_entity,
                self.thresholds.max_unresolved_entity_hypotheses_per_entity,
            ),
            ("missing_source_time_rate", metrics.missing_source_time_rate, self.thresholds.max_missing_source_time_rate),
            ("m02_block_rate", metrics.m02_block_rate, self.thresholds.max_m02_block_rate),
            ("dan_review_rate", metrics.dan_review_rate, self.thresholds.max_dan_review_rate),
        )
        for metric, observed, limit in checks:
            if limit is not None and observed > limit:
                findings.append(BenchmarkFinding(
                    metric,
                    observed,
                    limit,
                    f"{metric} exceeds configured maximum",
                ))

        return BenchmarkReport(
            build,
            metrics,
            self.thresholds,
            tuple(sorted(findings, key=lambda finding: finding.finding_id)),
            BenchmarkStatus.FAIL if findings else BenchmarkStatus.PASS,
        )


class CorpusScaleProbe:
    """Synthetic aggregate probe; no real corpus text or identifiers leave private storage."""

    @staticmethod
    def _hash(value: str) -> str:
        return sha256(value.encode("utf-8")).hexdigest()

    def run(self, conversation_count: int) -> CorpusScaleReport:
        if conversation_count < 1:
            raise ValueError("conversation_count must be positive")
        scheduler = IncrementalScheduler()
        builder = CorpusTaskGraphBuilder({}, {})
        old_inputs = {
            f"conversation-{index:06d}": self._hash(f"conversation-input:{index}")
            for index in range(conversation_count)
        }
        old_global = self._hash("global-input:v1")
        old_specs = builder.build(old_inputs, global_input_hash=old_global)
        cold_plan = scheduler.plan(old_specs, {})

        cache = {}
        output_by_key = {}
        for planned in sorted(cold_plan.tasks, key=lambda item: (item.wave, item.spec.key)):
            dependency_outputs = {dep: output_by_key[dep] for dep in planned.spec.dependencies}
            output_hash = self._hash(f"stable-output:{planned.spec.key.stage}:{planned.spec.key.partition}")
            entry = scheduler.complete_entry(planned.spec, dependency_outputs, output_hash)
            cache[planned.spec.key] = entry
            output_by_key[planned.spec.key] = output_hash

        changed_inputs = dict(old_inputs)
        first_key = sorted(changed_inputs)[0]
        changed_inputs[first_key] = self._hash("conversation-input:changed")
        changed_specs = builder.build(changed_inputs, global_input_hash=self._hash("global-input:v2"))
        changed_plan = scheduler.plan(changed_specs, cache)

        run_count = sum(task.disposition == PlanDisposition.RUN for task in cold_plan.tasks)
        reuse_count = len(cold_plan.tasks) - run_count
        single_run = sum(task.disposition == PlanDisposition.RUN for task in changed_plan.tasks)
        single_reuse = len(changed_plan.tasks) - single_run
        map_tasks = sum(spec.key.stage in {"K01", "K02", "K03"} for spec in old_specs)
        global_tasks = len(old_specs) - map_tasks

        return CorpusScaleReport(
            conversation_count,
            len(old_specs),
            run_count,
            reuse_count,
            len(cold_plan.waves),
            map_tasks,
            global_tasks,
            single_run,
            single_reuse,
        )
