from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from hashlib import sha256
from typing import Any

from .build import canonical_json, content_id


class EpistemicType(str, Enum):
    FACT = "fact"
    USER_STATEMENT = "user_statement"
    OBSERVED_ACTION = "observed_action"
    DECISION = "decision"
    GOAL = "goal"
    PLAN = "plan"
    PREFERENCE = "preference"
    BELIEF = "belief"
    HYPOTHESIS = "hypothesis"
    INTERPRETATION = "interpretation"
    ASSISTANT_PROPOSAL = "assistant_proposal"
    PROJECT_STATE = "project_state"
    OUTCOME = "outcome"
    RELATIONSHIP = "relationship"
    EVENT = "event"
    QUESTION = "question"
    UNCERTAINTY = "uncertainty"


class MemoryClass(str, Enum):
    EXPERIENCE = "experience"
    BELIEF = "belief"
    PREFERENCE = "preference"
    GOAL = "goal"
    DECISION = "decision"
    PLAN = "plan"
    PROJECT = "project"
    RELATIONSHIP = "relationship"
    PERSON = "person"
    CONCEPT = "concept"
    EVENT = "event"
    SELF_MODEL = "self_model"
    WORK = "work"
    OTHER = "other"


class TemporalPrecision(str, Enum):
    EXACT = "exact"
    DAY = "day"
    MONTH = "month"
    YEAR = "year"
    RANGE = "range"
    RELATIVE = "relative"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ModelLineage:
    provider: str
    model: str
    role: str
    prompt_contract: str
    prompt_version: str
    invocation_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("provider", "model", "role", "prompt_contract", "prompt_version"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must be non-empty")


@dataclass(frozen=True, slots=True)
class EvidenceSpan:
    source_id: str
    source_type: str
    conversation_id: str | None
    message_id: str | None
    chunk_id: str | None
    speaker: str | None
    exact_text: str
    start_offset: int | None = None
    end_offset: int | None = None
    source_sha256: str | None = None

    def __post_init__(self) -> None:
        if not self.source_id.strip() or not self.source_type.strip():
            raise ValueError("source_id and source_type are required")
        if not self.exact_text.strip():
            raise ValueError("exact_text is required")
        if (self.start_offset is None) != (self.end_offset is None):
            raise ValueError("start_offset and end_offset must be both present or both absent")
        if self.start_offset is not None:
            if self.start_offset < 0 or self.end_offset < self.start_offset:
                raise ValueError("invalid evidence offsets")
        if self.source_sha256 is not None and len(self.source_sha256) != 64:
            raise ValueError("source_sha256 must be a SHA-256 hex digest")

    @property
    def evidence_sha256(self) -> str:
        return sha256(self.exact_text.encode("utf-8")).hexdigest()

    @property
    def evidence_id(self) -> str:
        return content_id("evidv0", self)


@dataclass(frozen=True, slots=True)
class TemporalAnchor:
    start: str | None
    end: str | None
    precision: TemporalPrecision
    timezone: str | None
    is_proxy: bool = False
    proxy_reason: str | None = None
    original_expression: str | None = None

    def __post_init__(self) -> None:
        if self.is_proxy and not (self.proxy_reason or "").strip():
            raise ValueError("proxy temporal anchors require proxy_reason")
        if not self.is_proxy and self.proxy_reason is not None:
            raise ValueError("proxy_reason is only valid for proxy anchors")
        for value in (self.start, self.end):
            if value is not None:
                try:
                    datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    if len(value) not in (4, 7, 10):
                        raise ValueError(f"invalid temporal value: {value}")


@dataclass(frozen=True, slots=True)
class EntityMention:
    mention_text: str
    entity_type_hint: str | None
    evidence_id: str
    canonical_hint: str | None = None
    confidence: float = 0.0

    def __post_init__(self) -> None:
        if not self.mention_text.strip():
            raise ValueError("mention_text is required")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")

    @property
    def mention_id(self) -> str:
        return content_id("ementionv0", self)


@dataclass(frozen=True, slots=True)
class CorpusChunk:
    chunk_id: str
    source_id: str
    conversation_id: str
    title: str | None
    speaker: str
    occurred_at: str | None
    text: str
    source_sha256: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("chunk_id", "source_id", "conversation_id", "speaker"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must be non-empty")
        if not self.text.strip():
            raise ValueError("text must be non-empty")

    @property
    def canonical_hash(self) -> str:
        return sha256(canonical_json(self).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CandidateAssertion:
    statement: str
    subject: str
    predicate: str
    object: str
    epistemic_type: EpistemicType
    memory_class: MemoryClass
    evidence: tuple[EvidenceSpan, ...]
    temporal: TemporalAnchor
    entity_mentions: tuple[EntityMention, ...]
    tags: tuple[str, ...]
    lineage: ModelLineage
    extractor_confidence: float
    source_origin_probability: float
    importance: float
    durability: float
    fidelity: str = "source_bound"
    notes: str | None = None

    def __post_init__(self) -> None:
        for name in ("statement", "subject", "predicate", "object", "fidelity"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must be non-empty")
        if not self.evidence:
            raise ValueError("at least one evidence span is required")
        for name in ("extractor_confidence", "source_origin_probability", "importance", "durability"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
        normalized_tags = tuple(sorted({t.strip().lower() for t in self.tags if t.strip()}))
        object.__setattr__(self, "tags", normalized_tags)
        if len(normalized_tags) > 32:
            raise ValueError("at most 32 normalized tags are allowed")
        evidence_ids = {e.evidence_id for e in self.evidence}
        for mention in self.entity_mentions:
            if mention.evidence_id not in evidence_ids:
                raise ValueError("entity mention must reference candidate evidence")

    @property
    def candidate_id(self) -> str:
        return content_id("cirv0", self)
