from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256

from .build import BuildIdentity, canonical_json, content_id
from .ir import EpistemicType, MemoryClass
from .semantic_model import Polarity


class ProjectionRole(str, Enum):
    SUBJECT = "subject"
    OBJECT = "object"
    BOTH = "both"


@dataclass(frozen=True, slots=True)
class PropositionProjection:
    group_id: str
    signature_id: str
    role: ProjectionRole
    representative_candidate_id: str
    representative_statement: str
    epistemic_type: EpistemicType
    memory_class: MemoryClass
    polarity: Polarity
    normalized_assertion_ids: tuple[str, ...]
    occurrence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("group_id", "signature_id", "representative_candidate_id", "representative_statement"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must be non-empty")

    @property
    def proposition_projection_id(self) -> str:
        return content_id("propprojv0", self)


@dataclass(frozen=True, slots=True)
class EntityProjectionCard:
    entity_id: str
    entity_type: str | None
    canonical_name: str
    aliases: tuple[str, ...]
    propositions: tuple[PropositionProjection, ...]
    relation_ids: tuple[str, ...]
    conflict_ids: tuple[str, ...]
    supersession_ids: tuple[str, ...]
    unresolved_hypothesis_ids: tuple[str, ...]
    latest_observed_occurrence_ids: tuple[str, ...]
    diagnostics: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.entity_id.strip() or not self.canonical_name.strip():
            raise ValueError("entity projection identity fields must be non-empty")

    @property
    def card_id(self) -> str:
        return content_id("entitycardv0", self)


@dataclass(frozen=True, slots=True)
class ProjectionDiagnostic:
    code: str
    message: str
    entity_id: str | None = None
    ref_id: str | None = None

    @property
    def diagnostic_id(self) -> str:
        return content_id("projdiagv0", self)


@dataclass(frozen=True, slots=True)
class SynthesisProjectionResult:
    build: BuildIdentity
    cards: tuple[EntityProjectionCard, ...]
    diagnostics: tuple[ProjectionDiagnostic, ...]

    @property
    def output_hash(self) -> str:
        return sha256(canonical_json({"cards": self.cards, "diagnostics": self.diagnostics}).encode("utf-8")).hexdigest()
