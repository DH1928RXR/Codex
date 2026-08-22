from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256

from .build import BuildIdentity, canonical_json, content_id
from .ir import EpistemicType, MemoryClass, TemporalAnchor
from .semantic_model import SemanticArgumentIdentity


class Chronology(str, Enum):
    BEFORE = "before"
    AFTER = "after"
    SAME = "same"
    UNKNOWN = "unknown"


class SupersessionDisposition(str, Enum):
    SUGGESTED = "suggested"
    REVIEW_REQUIRED = "review_required"
    BLOCKED_CHRONOLOGY = "blocked_chronology"
    BLOCKED_SLOT_MISMATCH = "blocked_slot_mismatch"
    BLOCKED_SAME_PROPOSITION = "blocked_same_proposition"


@dataclass(frozen=True, slots=True)
class StateSlotKey:
    subject: SemanticArgumentIdentity
    predicate: str
    epistemic_type: EpistemicType
    memory_class: MemoryClass

    @property
    def state_slot_id(self) -> str:
        return content_id("stateslotv0", self)


@dataclass(frozen=True, slots=True)
class TemporalOccurrence:
    normalized_assertion_id: str
    candidate_id: str
    semantic_group_id: str
    state_slot_id: str
    source_occurrence_times: tuple[str, ...]
    effective_anchor: TemporalAnchor

    @property
    def occurrence_id(self) -> str:
        return content_id("toccv0", self)


@dataclass(frozen=True, slots=True)
class TemporalStateSlot:
    key: StateSlotKey
    occurrence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SupersessionEvidence:
    kind: str
    source_ref: str
    score: float
    reason: str
    provider: str | None = None

    def __post_init__(self) -> None:
        if not self.kind.strip() or not self.source_ref.strip() or not self.reason.strip():
            raise ValueError("supersession evidence fields must be non-empty")
        if not -1.0 <= self.score <= 1.0:
            raise ValueError("supersession evidence score must be between -1 and 1")

    @property
    def evidence_id(self) -> str:
        return content_id("supevidv0", self)


@dataclass(frozen=True, slots=True)
class SupersessionProposal:
    predecessor_assertion_id: str
    successor_assertion_id: str
    proposer: str
    evidence: tuple[SupersessionEvidence, ...]

    def __post_init__(self) -> None:
        if not self.predecessor_assertion_id.strip() or not self.successor_assertion_id.strip() or not self.proposer.strip():
            raise ValueError("supersession proposal identity fields must be non-empty")
        if self.predecessor_assertion_id == self.successor_assertion_id:
            raise ValueError("supersession proposal requires two different assertions")
        if not self.evidence:
            raise ValueError("supersession proposals require evidence")

    @property
    def proposal_id(self) -> str:
        return content_id("suppropv0", self)


@dataclass(frozen=True, slots=True)
class CompiledSupersession:
    predecessor_assertion_id: str
    successor_assertion_id: str
    chronology: Chronology
    score: float
    evidence: tuple[SupersessionEvidence, ...]
    proposers: tuple[str, ...]
    disposition: SupersessionDisposition

    @property
    def supersession_id(self) -> str:
        return content_id("supersessionv0", self)


@dataclass(frozen=True, slots=True)
class TemporalDiagnostic:
    code: str
    message: str
    candidate_id: str | None = None
    normalized_assertion_id: str | None = None

    @property
    def diagnostic_id(self) -> str:
        return content_id("tdiagv0", self)


@dataclass(frozen=True, slots=True)
class TemporalCompilationResult:
    build: BuildIdentity
    occurrences: tuple[TemporalOccurrence, ...]
    state_slots: tuple[TemporalStateSlot, ...]
    supersessions: tuple[CompiledSupersession, ...]
    diagnostics: tuple[TemporalDiagnostic, ...]

    @property
    def output_hash(self) -> str:
        payload = {
            "occurrences": self.occurrences,
            "state_slots": self.state_slots,
            "supersessions": self.supersessions,
            "diagnostics": self.diagnostics,
        }
        return sha256(canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class TemporalPolicy:
    review_threshold: float = 0.80
    require_known_forward_chronology_for_review: bool = False

    def __post_init__(self) -> None:
        if not 0.0 <= self.review_threshold <= 1.0:
            raise ValueError("review_threshold must be between 0 and 1")
