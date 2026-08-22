from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256

from .build import BuildIdentity, canonical_json, content_id


class EntityStatus(str, Enum):
    ACTIVE = "active"
    REDIRECTED = "redirected"


class ResolutionAction(str, Enum):
    LINK_MENTION = "link_mention"
    MERGE_ENTITY = "merge_entity"
    KEEP_DISTINCT = "keep_distinct"
    SET_CANONICAL_NAME = "set_canonical_name"
    RETRACT_DECISION = "retract_decision"


class HypothesisDisposition(str, Enum):
    SUGGESTED = "suggested"
    REVIEW_REQUIRED = "review_required"
    BLOCKED = "blocked"


class FullRebuildRequired(RuntimeError):
    """A prior projected decision changed and K04 must replay from an empty registry."""


@dataclass(frozen=True, slots=True)
class ResolutionEvidence:
    kind: str
    source_ref: str
    score: float
    reason: str
    provider: str | None = None

    def __post_init__(self) -> None:
        if not self.kind.strip() or not self.source_ref.strip() or not self.reason.strip():
            raise ValueError("resolution evidence fields must be non-empty")
        if not -1.0 <= self.score <= 1.0:
            raise ValueError("resolution evidence score must be between -1 and 1")

    @property
    def evidence_id(self) -> str:
        return content_id("resevidv0", self)


@dataclass(frozen=True, slots=True)
class ResolutionDecision:
    action: ResolutionAction
    subject_id: str
    object_id: str | None
    authority: str
    evidence: tuple[ResolutionEvidence, ...]
    canonical_name: str | None = None

    def __post_init__(self) -> None:
        if not self.subject_id.strip() or not self.authority.strip():
            raise ValueError("decision subject_id and authority are required")
        if self.action in {
            ResolutionAction.LINK_MENTION,
            ResolutionAction.MERGE_ENTITY,
            ResolutionAction.KEEP_DISTINCT,
        } and not (self.object_id or "").strip():
            raise ValueError(f"{self.action.value} requires object_id")
        if self.action == ResolutionAction.SET_CANONICAL_NAME and not (self.canonical_name or "").strip():
            raise ValueError("set_canonical_name requires canonical_name")
        if self.action == ResolutionAction.RETRACT_DECISION and self.object_id is not None:
            raise ValueError("retract_decision uses subject_id as the retracted decision id")
        if not self.evidence:
            raise ValueError("resolution decisions require evidence")

    @property
    def decision_id(self) -> str:
        return content_id("resdecv0", self)


@dataclass(frozen=True, slots=True)
class ResolutionProposal:
    mention_key_id: str
    candidate_entity_id: str
    proposer: str
    evidence: tuple[ResolutionEvidence, ...]

    def __post_init__(self) -> None:
        if not self.mention_key_id.strip() or not self.candidate_entity_id.strip() or not self.proposer.strip():
            raise ValueError("proposal identity fields must be non-empty")
        if not self.evidence:
            raise ValueError("resolution proposals require evidence")

    @property
    def proposal_id(self) -> str:
        return content_id("respropv0", self)


@dataclass(frozen=True, slots=True)
class EntityAlias:
    normalized: str
    display_forms: tuple[str, ...]
    mention_key_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EntityRecord:
    entity_id: str
    entity_type: str | None
    canonical_name: str
    aliases: tuple[EntityAlias, ...]
    anchor_mention_key_id: str
    status: EntityStatus = EntityStatus.ACTIVE

    def __post_init__(self) -> None:
        if not self.entity_id.strip() or not self.canonical_name.strip() or not self.anchor_mention_key_id.strip():
            raise ValueError("entity identity fields must be non-empty")


@dataclass(frozen=True, slots=True)
class MentionBinding:
    mention_key_id: str
    entity_id: str
    basis: str
    decision_id: str | None = None


@dataclass(frozen=True, slots=True)
class EntityRedirect:
    source_entity_id: str
    target_entity_id: str
    decision_id: str


@dataclass(frozen=True, slots=True)
class EntityPairConstraint:
    left_entity_id: str
    right_entity_id: str
    decision_id: str

    def __post_init__(self) -> None:
        if self.left_entity_id == self.right_entity_id:
            raise ValueError("entity-pair constraint requires two distinct entities")
        left, right = sorted((self.left_entity_id, self.right_entity_id))
        object.__setattr__(self, "left_entity_id", left)
        object.__setattr__(self, "right_entity_id", right)


@dataclass(frozen=True, slots=True)
class EntityHypothesis:
    mention_key_id: str
    candidate_entity_id: str
    score: float
    evidence: tuple[ResolutionEvidence, ...]
    disposition: HypothesisDisposition

    @property
    def hypothesis_id(self) -> str:
        return content_id("reshypv0", self)


@dataclass(frozen=True, slots=True)
class EntityRegistrySnapshot:
    entities: tuple[EntityRecord, ...] = ()
    bindings: tuple[MentionBinding, ...] = ()
    redirects: tuple[EntityRedirect, ...] = ()
    constraints: tuple[EntityPairConstraint, ...] = ()
    decision_log: tuple[ResolutionDecision, ...] = ()
    applied_decision_ids: tuple[str, ...] = ()
    retracted_decision_ids: tuple[str, ...] = ()

    @property
    def snapshot_id(self) -> str:
        return content_id("eregistryv0", self)


@dataclass(frozen=True, slots=True)
class EntityResolutionResult:
    build: BuildIdentity
    registry: EntityRegistrySnapshot
    hypotheses: tuple[EntityHypothesis, ...]

    @property
    def output_hash(self) -> str:
        payload = {"registry": self.registry, "hypotheses": self.hypotheses}
        return sha256(canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class EntityResolutionPolicy:
    fuzzy_candidate_threshold: float = 0.78
    review_threshold: float = 0.80
    canonical_hint_weight: float = 0.90
    name_similarity_weight: float = 0.70
    trigram_weight: float = 0.30
    auto_bind_verified_aliases: bool = True

    def __post_init__(self) -> None:
        for name in (
            "fuzzy_candidate_threshold",
            "review_threshold",
            "canonical_hint_weight",
            "name_similarity_weight",
            "trigram_weight",
        ):
            if not 0.0 <= getattr(self, name) <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
