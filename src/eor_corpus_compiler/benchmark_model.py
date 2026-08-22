from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256

from .build import BuildIdentity, canonical_json, content_id


class BenchmarkStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class QualityThresholds:
    max_quarantine_rate: float | None = None
    max_unresolved_entity_hypotheses_per_entity: float | None = None
    max_missing_source_time_rate: float | None = None
    max_m02_block_rate: float | None = None
    max_dan_review_rate: float | None = None

    def __post_init__(self) -> None:
        for name in (
            "max_quarantine_rate",
            "max_unresolved_entity_hypotheses_per_entity",
            "max_missing_source_time_rate",
            "max_m02_block_rate",
            "max_dan_review_rate",
        ):
            value = getattr(self, name)
            if value is not None and value < 0.0:
                raise ValueError(f"{name} must be non-negative")


@dataclass(frozen=True, slots=True)
class BenchmarkMetrics:
    candidates_total: int
    candidates_accepted: int
    candidates_quarantined: int
    quarantine_rate: float
    active_entities: int
    unresolved_entity_hypotheses: int
    unresolved_entity_hypotheses_per_entity: float
    semantic_groups: int
    normalized_assertions: int
    compiled_relations: int
    temporal_occurrences: int
    missing_source_time_occurrences: int
    missing_source_time_rate: float
    conflicts: int
    synthesis_cards: int
    review_items: int
    terra_review_items: int
    sol_review_items: int
    dan_review_items: int
    dan_review_rate: float
    m02_candidates_total: int
    m02_candidates_eligible: int
    m02_candidates_blocked: int
    m02_block_rate: float
    m02_relations_eligible: int


@dataclass(frozen=True, slots=True)
class BenchmarkFinding:
    metric: str
    observed: float
    limit: float
    message: str

    @property
    def finding_id(self) -> str:
        return content_id("benchfindingv0", self)


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    build: BuildIdentity
    metrics: BenchmarkMetrics
    thresholds: QualityThresholds
    findings: tuple[BenchmarkFinding, ...]
    status: BenchmarkStatus

    @property
    def report_hash(self) -> str:
        return sha256(canonical_json({
            "metrics": self.metrics,
            "thresholds": self.thresholds,
            "findings": self.findings,
            "status": self.status,
        }).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CorpusScaleReport:
    conversation_count: int
    task_count: int
    run_task_count: int
    reuse_task_count: int
    wave_count: int
    map_task_count: int
    global_task_count: int
    single_change_run_task_count: int
    single_change_reuse_task_count: int

    @property
    def scale_report_id(self) -> str:
        return content_id("scalereportv0", self)
