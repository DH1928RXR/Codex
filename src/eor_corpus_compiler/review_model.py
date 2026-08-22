from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum
from hashlib import sha256

from .build import BuildIdentity, canonical_json, content_id


class ReviewKind(str, Enum):
    ENTITY_RESOLUTION = "entity_resolution"
    RELATION = "relation"
    SUPERSESSION = "supersession"
    CONFLICT = "conflict"
    PROJECTION_DIAGNOSTIC = "projection_diagnostic"


class ReviewAuthority(IntEnum):
    TERRA = 1
    SOL = 2
    DAN = 3


@dataclass(frozen=True, slots=True)
class ReviewPolicy:
    sol_priority_threshold: float = 0.58
    dan_priority_threshold: float = 0.84
    dan_impact_threshold: float = 0.82
    high_centrality_proposition_count: int = 8

    def __post_init__(self) -> None:
        for name in ("sol_priority_threshold", "dan_priority_threshold", "dan_impact_threshold"):
            if not 0.0 <= getattr(self, name) <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.high_centrality_proposition_count < 1:
            raise ValueError("high_centrality_proposition_count must be positive")


@dataclass(frozen=True, slots=True)
class ReviewItem:
    kind: ReviewKind
    source_ref: str
    score: float
    ambiguity: float
    impact: float
    priority: float
    route: ReviewAuthority
    reason_codes: tuple[str, ...]
    related_entity_ids: tuple[str, ...] = ()
    related_group_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.source_ref.strip():
            raise ValueError("review item source_ref must be non-empty")
        for name in ("score", "ambiguity", "impact", "priority"):
            if not 0.0 <= getattr(self, name) <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
        object.__setattr__(self, "reason_codes", tuple(sorted(set(self.reason_codes))))
        object.__setattr__(self, "related_entity_ids", tuple(sorted(set(self.related_entity_ids))))
        object.__setattr__(self, "related_group_ids", tuple(sorted(set(self.related_group_ids))))

    @property
    def review_item_id(self) -> str:
        return content_id("reviewitemv0", self)


@dataclass(frozen=True, slots=True)
class ReviewQueue:
    build: BuildIdentity
    items: tuple[ReviewItem, ...]

    @property
    def output_hash(self) -> str:
        return sha256(canonical_json(self.items).encode("utf-8")).hexdigest()


class ReviewDecision(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    DEFER = "defer"
    ESCALATE = "escalate"


@dataclass(frozen=True, slots=True)
class ReviewResponse:
    review_item_id: str
    reviewer: str
    authority: ReviewAuthority
    decision: ReviewDecision
    reason: str
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.review_item_id.strip() or not self.reviewer.strip() or not self.reason.strip():
            raise ValueError("review response identity/reason fields must be non-empty")
        if self.decision in {ReviewDecision.ACCEPT, ReviewDecision.REJECT} and not self.evidence_refs:
            raise ValueError("final accept/reject responses require evidence refs")
        object.__setattr__(self, "evidence_refs", tuple(sorted(set(self.evidence_refs))))

    @property
    def response_id(self) -> str:
        return content_id("reviewrespv0", self)


class AdjudicationDisposition(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DEFERRED = "deferred"
    ESCALATED = "escalated"
    PENDING = "pending"


@dataclass(frozen=True, slots=True)
class AdjudicationRecord:
    review_item_id: str
    disposition: AdjudicationDisposition
    controlling_response_id: str | None
    response_ids: tuple[str, ...]
    final_authority: ReviewAuthority | None
    reason: str

    @property
    def adjudication_id(self) -> str:
        return content_id("adjudicationv0", self)


@dataclass(frozen=True, slots=True)
class AdjudicationResult:
    build: BuildIdentity
    records: tuple[AdjudicationRecord, ...]

    @property
    def output_hash(self) -> str:
        return sha256(canonical_json(self.records).encode("utf-8")).hexdigest()
