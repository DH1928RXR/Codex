from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from typing import Protocol, Sequence, runtime_checkable

from .build import BuildIdentity, canonical_json, content_id
from .ir import TemporalAnchor


class M02Eligibility(str, Enum):
    ELIGIBLE = "eligible"
    BLOCKED_VALIDATION = "blocked_validation"
    BLOCKED_SOURCE_EXACTNESS = "blocked_source_exactness"
    BLOCKED_SOURCE_MODE = "blocked_source_mode"
    BLOCKED_TEMPORAL_CONTRACT = "blocked_temporal_contract"


@dataclass(frozen=True, slots=True)
class M02CapabilityDescriptor:
    backend_id: str
    record_contract: str
    staging_contract: str
    supported_source_types: tuple[str, ...]
    supported_relation_types: tuple[str, ...]
    supported_temporal_bases: tuple[str, ...]
    can_build_pending_review_bundle: bool
    can_validate_bundle: bool
    preserves_effective_anchor: bool = False
    exposes_promotion: bool = False

    def __post_init__(self) -> None:
        if not self.backend_id.strip() or not self.record_contract.strip() or not self.staging_contract.strip():
            raise ValueError("M02 capability identity fields must be non-empty")
        if self.exposes_promotion:
            raise ValueError("K11 backends must not expose canonical promotion authority")
        object.__setattr__(self, "supported_source_types", tuple(sorted(set(self.supported_source_types))))
        object.__setattr__(self, "supported_relation_types", tuple(sorted(set(self.supported_relation_types))))
        object.__setattr__(self, "supported_temporal_bases", tuple(sorted(set(self.supported_temporal_bases))))

    @property
    def capability_id(self) -> str:
        return content_id("m02capv0", self)


@dataclass(frozen=True, slots=True)
class M02EvidenceInput:
    evidence_id: str
    source_id: str
    source_type: str
    conversation_id: str | None
    message_id: str | None
    chunk_id: str
    speaker: str | None
    exact_text: str
    source_sha256: str
    source_occurrence_time: str | None

    def __post_init__(self) -> None:
        for name in ("evidence_id", "source_id", "source_type", "chunk_id", "exact_text", "source_sha256"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must be non-empty")
        if len(self.source_sha256) != 64:
            raise ValueError("source_sha256 must be a SHA-256 hex digest")


@dataclass(frozen=True, slots=True)
class M02RelationInput:
    source_candidate_id: str
    target_candidate_id: str
    relation_type: str
    source_ref: str
    adjudication_ref: str

    def __post_init__(self) -> None:
        for name in ("source_candidate_id", "target_candidate_id", "relation_type", "source_ref", "adjudication_ref"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must be non-empty")
        if self.source_candidate_id == self.target_candidate_id:
            raise ValueError("M02 relation input requires two different candidates")

    @property
    def relation_input_id(self) -> str:
        return content_id("m02relinputv0", self)


@dataclass(frozen=True, slots=True)
class M02RecordInput:
    candidate_id: str
    memory_class: str
    epistemic_type: str
    statement: str
    subject: str
    predicate: str
    object: str
    source_origin_probability: float
    extractor_confidence: float
    importance: float
    durability: float
    tags: tuple[str, ...]
    evidence: tuple[M02EvidenceInput, ...]
    source_occurrence_times: tuple[str, ...]
    temporal_basis: str
    effective_anchor: TemporalAnchor
    relation_inputs: tuple[M02RelationInput, ...] = ()

    def __post_init__(self) -> None:
        if not self.candidate_id.strip() or not self.statement.strip() or not self.temporal_basis.strip():
            raise ValueError("M02 record input identity/statement/temporal basis must be non-empty")
        if not self.evidence:
            raise ValueError("M02 record input requires exact evidence")
        object.__setattr__(self, "tags", tuple(sorted(set(self.tags))))
        object.__setattr__(self, "source_occurrence_times", tuple(sorted(set(self.source_occurrence_times))))
        object.__setattr__(self, "relation_inputs", tuple(sorted(set(self.relation_inputs), key=lambda r: r.relation_input_id)))


@dataclass(frozen=True, slots=True)
class M02CandidateDisposition:
    candidate_id: str
    eligibility: M02Eligibility
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.candidate_id.strip():
            raise ValueError("candidate_id must be non-empty")
        object.__setattr__(self, "reason_codes", tuple(sorted(set(self.reason_codes))))


@dataclass(frozen=True, slots=True)
class M02AdapterDiagnostic:
    code: str
    message: str
    source_ref: str | None = None

    @property
    def diagnostic_id(self) -> str:
        return content_id("m02diagv0", self)


@dataclass(frozen=True, slots=True)
class M02PreparationResult:
    build: BuildIdentity
    capability_id: str
    eligible_records: tuple[M02RecordInput, ...]
    candidate_dispositions: tuple[M02CandidateDisposition, ...]
    eligible_relations: tuple[M02RelationInput, ...]
    diagnostics: tuple[M02AdapterDiagnostic, ...]

    @property
    def output_hash(self) -> str:
        payload = {
            "capability_id": self.capability_id,
            "eligible_records": self.eligible_records,
            "candidate_dispositions": self.candidate_dispositions,
            "eligible_relations": self.eligible_relations,
            "diagnostics": self.diagnostics,
        }
        return sha256(canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class M02StagingArtifact:
    backend_id: str
    bundle_id: str
    bundle_sha256: str
    record_ids: tuple[str, ...]
    candidate_ids: tuple[str, ...]
    promotable: bool
    validation_status: str
    backend_receipt: str | None = None

    def __post_init__(self) -> None:
        if not self.backend_id.strip() or not self.bundle_id.strip() or not self.bundle_sha256.strip():
            raise ValueError("M02 staging artifact identity fields must be non-empty")
        if len(self.bundle_sha256) != 64:
            raise ValueError("bundle_sha256 must be a SHA-256 hex digest")


@runtime_checkable
class VerifiedM02StagingBackend(Protocol):
    """Adapter surface over the already-verified M02 package.

    The backend may build/validate closed staging bundles. It MUST NOT expose or
    perform canonical promotion. K11 never receives store credentials or ledger heads.
    """

    def capabilities(self) -> M02CapabilityDescriptor: ...

    def build_pending_staging(
        self,
        records: Sequence[M02RecordInput],
        relations: Sequence[M02RelationInput],
        *,
        bundle_id: str,
        created_at: str,
    ) -> M02StagingArtifact: ...

    def validate_staging(self, artifact: M02StagingArtifact) -> M02StagingArtifact: ...
