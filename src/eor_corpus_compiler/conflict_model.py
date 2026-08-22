from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256

from .build import BuildIdentity, canonical_json, content_id


class EffectiveRelation(str, Enum):
    OVERLAP = "overlap"
    DISJOINT = "disjoint"
    UNKNOWN = "unknown"


class ConflictKind(str, Enum):
    POLARITY_OPPOSITION = "polarity_opposition"
    SEMANTIC_CONTRADICTION = "semantic_contradiction"


class ConflictDisposition(str, Enum):
    REVIEW_REQUIRED = "review_required"
    SUGGESTED = "suggested"
    TEMPORALLY_DISJOINT = "temporally_disjoint"
    CHANGE_OVER_TIME_CANDIDATE = "change_over_time_candidate"
    UNKNOWN_TEMPORAL = "unknown_temporal"


@dataclass(frozen=True, slots=True)
class ConflictCase:
    left_group_id: str
    right_group_id: str
    kind: ConflictKind
    effective_relation: EffectiveRelation
    score: float
    source_relation_ids: tuple[str, ...]
    source_supersession_ids: tuple[str, ...]
    disposition: ConflictDisposition

    def __post_init__(self) -> None:
        if not self.left_group_id.strip() or not self.right_group_id.strip():
            raise ValueError("conflict endpoints must be non-empty")
        if self.left_group_id == self.right_group_id:
            raise ValueError("conflict case requires two different groups")
        left, right = sorted((self.left_group_id, self.right_group_id))
        object.__setattr__(self, "left_group_id", left)
        object.__setattr__(self, "right_group_id", right)
        if not 0.0 <= self.score <= 1.0:
            raise ValueError("conflict score must be between 0 and 1")
        if not self.source_relation_ids:
            raise ValueError("conflict cases require at least one source relation")

    @property
    def conflict_id(self) -> str:
        return content_id("conflictv0", self)


@dataclass(frozen=True, slots=True)
class ConflictDiagnostic:
    code: str
    message: str
    left_group_id: str | None = None
    right_group_id: str | None = None

    @property
    def diagnostic_id(self) -> str:
        return content_id("confdiagv0", self)


@dataclass(frozen=True, slots=True)
class ConflictCompilationResult:
    build: BuildIdentity
    conflicts: tuple[ConflictCase, ...]
    diagnostics: tuple[ConflictDiagnostic, ...]

    @property
    def output_hash(self) -> str:
        return sha256(canonical_json({"conflicts": self.conflicts, "diagnostics": self.diagnostics}).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ConflictPolicy:
    review_threshold: float = 0.80

    def __post_init__(self) -> None:
        if not 0.0 <= self.review_threshold <= 1.0:
            raise ValueError("review_threshold must be between 0 and 1")
