from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256

from .build import BuildIdentity, canonical_json, content_id


class RelationType(str, Enum):
    SUPPORTS = "supports"
    REPEATS = "repeats"
    ELABORATES = "elaborates"
    REFINES = "refines"
    QUALIFIES = "qualifies"
    CONTRADICTS = "contradicts"
    SUPERSEDES = "supersedes"
    UNRELATED = "unrelated"
    POLARITY_OPPOSES = "polarity_opposes"


SYMMETRIC_RELATIONS = {
    RelationType.CONTRADICTS,
    RelationType.UNRELATED,
    RelationType.POLARITY_OPPOSES,
    RelationType.REPEATS,
}


class RelationDisposition(str, Enum):
    STRUCTURAL = "structural"
    SUGGESTED = "suggested"
    REVIEW_REQUIRED = "review_required"


@dataclass(frozen=True, slots=True)
class RelationEvidence:
    kind: str
    source_ref: str
    score: float
    reason: str
    provider: str | None = None

    def __post_init__(self) -> None:
        if not self.kind.strip() or not self.source_ref.strip() or not self.reason.strip():
            raise ValueError("relation evidence fields must be non-empty")
        if not -1.0 <= self.score <= 1.0:
            raise ValueError("relation evidence score must be between -1 and 1")

    @property
    def evidence_id(self) -> str:
        return content_id("relevidv0", self)


@dataclass(frozen=True, slots=True)
class RelationKey:
    source_group_id: str
    target_group_id: str
    relation_type: RelationType

    def __post_init__(self) -> None:
        if not self.source_group_id.strip() or not self.target_group_id.strip():
            raise ValueError("relation endpoints must be non-empty")
        if self.source_group_id == self.target_group_id:
            raise ValueError("self-relations are not emitted by K06")
        if self.relation_type in SYMMETRIC_RELATIONS:
            source, target = sorted((self.source_group_id, self.target_group_id))
            object.__setattr__(self, "source_group_id", source)
            object.__setattr__(self, "target_group_id", target)

    @property
    def relation_key_id(self) -> str:
        return content_id("relkeyv0", self)


@dataclass(frozen=True, slots=True)
class RelationProposal:
    key: RelationKey
    proposer: str
    evidence: tuple[RelationEvidence, ...]

    def __post_init__(self) -> None:
        if not self.proposer.strip() or not self.evidence:
            raise ValueError("relation proposals require proposer and evidence")

    @property
    def proposal_id(self) -> str:
        return content_id("relpropv0", self)


@dataclass(frozen=True, slots=True)
class CompiledRelation:
    key: RelationKey
    score: float
    evidence: tuple[RelationEvidence, ...]
    proposers: tuple[str, ...]
    disposition: RelationDisposition

    @property
    def relation_id(self) -> str:
        return content_id("relationv0", self)


@dataclass(frozen=True, slots=True)
class RelationCompilationResult:
    build: BuildIdentity
    relations: tuple[CompiledRelation, ...]

    @property
    def output_hash(self) -> str:
        return sha256(canonical_json(self.relations).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class RelationPolicy:
    review_threshold: float = 0.80
    structural_polarity_score: float = 1.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.review_threshold <= 1.0:
            raise ValueError("review_threshold must be between 0 and 1")
        if not 0.0 <= self.structural_polarity_score <= 1.0:
            raise ValueError("structural_polarity_score must be between 0 and 1")
