from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256

from .build import BuildIdentity, canonical_json, content_id
from .entity_model import ResolutionEvidence
from .ir import EpistemicType, MemoryClass, TemporalAnchor


class ArgumentKind(str, Enum):
    ENTITY = "entity"
    LITERAL = "literal"


class ArgumentRole(str, Enum):
    SUBJECT = "subject"
    OBJECT = "object"


class Polarity(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


@dataclass(frozen=True, slots=True)
class SemanticArgumentIdentity:
    kind: ArgumentKind
    value: str

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise ValueError("semantic argument identity value must be non-empty")


@dataclass(frozen=True, slots=True)
class SemanticArgument:
    kind: ArgumentKind
    value: str
    display: str
    basis: str

    def __post_init__(self) -> None:
        if not self.value.strip() or not self.display.strip() or not self.basis.strip():
            raise ValueError("semantic argument fields must be non-empty")

    @property
    def identity(self) -> SemanticArgumentIdentity:
        return SemanticArgumentIdentity(self.kind, self.value)


@dataclass(frozen=True, slots=True)
class PredicateAlias:
    alias: str
    canonical: str


@dataclass(frozen=True, slots=True)
class PredicateOntology:
    aliases: tuple[PredicateAlias, ...] = ()


@dataclass(frozen=True, slots=True)
class ArgumentResolutionDecision:
    candidate_id: str
    role: ArgumentRole
    entity_id: str
    authority: str
    evidence: tuple[ResolutionEvidence, ...]

    def __post_init__(self) -> None:
        if not self.candidate_id.strip() or not self.entity_id.strip() or not self.authority.strip():
            raise ValueError("argument resolution decision fields must be non-empty")
        if not self.evidence:
            raise ValueError("argument resolution decisions require evidence")

    @property
    def decision_id(self) -> str:
        return content_id("argdecv0", self)


@dataclass(frozen=True, slots=True)
class SemanticSignature:
    subject: SemanticArgumentIdentity
    predicate: str
    object: SemanticArgumentIdentity
    polarity: Polarity
    epistemic_type: EpistemicType
    memory_class: MemoryClass

    @property
    def signature_id(self) -> str:
        return content_id("semsigv0", self)


@dataclass(frozen=True, slots=True)
class NormalizedAssertion:
    candidate_id: str
    signature: SemanticSignature
    subject_argument: SemanticArgument
    object_argument: SemanticArgument
    statement: str
    evidence_ids: tuple[str, ...]
    temporal: TemporalAnchor
    extractor_confidence: float
    source_origin_probability: float
    importance: float
    durability: float

    @property
    def normalized_id(self) -> str:
        return content_id("nassertv0", self)


@dataclass(frozen=True, slots=True)
class SemanticGroup:
    signature: SemanticSignature
    normalized_assertion_ids: tuple[str, ...]
    candidate_ids: tuple[str, ...]
    representative_candidate_id: str

    @property
    def group_id(self) -> str:
        return content_id("semgroupv0", self.signature)


@dataclass(frozen=True, slots=True)
class NormalizationDiagnostic:
    code: str
    message: str
    candidate_id: str
    role: ArgumentRole | None = None

    @property
    def diagnostic_id(self) -> str:
        return content_id("semdiagv0", self)


@dataclass(frozen=True, slots=True)
class SemanticNormalizationResult:
    build: BuildIdentity
    assertions: tuple[NormalizedAssertion, ...]
    groups: tuple[SemanticGroup, ...]
    diagnostics: tuple[NormalizationDiagnostic, ...]

    @property
    def output_hash(self) -> str:
        payload = {"assertions": self.assertions, "groups": self.groups, "diagnostics": self.diagnostics}
        return sha256(canonical_json(payload).encode("utf-8")).hexdigest()
