from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from typing import Sequence

from .build import BuildIdentity, canonical_json, content_id
from .ir import CandidateAssertion, CorpusChunk


class DiagnosticSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    severity: DiagnosticSeverity
    message: str
    candidate_id: str | None = None
    evidence_id: str | None = None

    @property
    def diagnostic_id(self) -> str:
        return content_id("cdiagv0", self)


@dataclass(frozen=True, slots=True)
class CandidateDisposition:
    candidate: CandidateAssertion
    accepted: bool
    diagnostics: tuple[Diagnostic, ...]


@dataclass(frozen=True, slots=True)
class ValidationResult:
    build: BuildIdentity
    accepted: tuple[CandidateAssertion, ...]
    quarantined: tuple[CandidateDisposition, ...]
    diagnostics: tuple[Diagnostic, ...]

    @property
    def output_hash(self) -> str:
        return sha256(canonical_json({"accepted": self.accepted, "quarantined": self.quarantined, "diagnostics": self.diagnostics}).encode("utf-8")).hexdigest()


class CandidateValidator:
    """K02 deterministic validator. Never mutates candidates or canonical stores."""

    def __init__(self, *, compiler_version: str = "0.1.0", min_source_origin_probability: float = 0.5):
        if not 0.0 <= min_source_origin_probability <= 1.0:
            raise ValueError("min_source_origin_probability must be between 0 and 1")
        self.compiler_version = compiler_version
        self.min_source_origin_probability = min_source_origin_probability

    def validate(self, chunks: Sequence[CorpusChunk], candidates: Sequence[CandidateAssertion]) -> ValidationResult:
        chunk_by_id = {c.chunk_id: c for c in chunks}
        input_hash = sha256(canonical_json({"chunks": chunks, "candidates": candidates}).encode("utf-8")).hexdigest()
        config_hash = sha256(canonical_json({"min_source_origin_probability": self.min_source_origin_probability}).encode("utf-8")).hexdigest()
        build = BuildIdentity("K02.validate", self.compiler_version, "eor.corpus_candidate_validation.v0", config_hash, input_hash)
        accepted = []; quarantined = []; diagnostics = []; seen = set()
        for candidate in sorted(candidates, key=lambda c: c.candidate_id):
            local = []; cid = candidate.candidate_id
            if cid in seen:
                local.append(Diagnostic("duplicate_candidate", DiagnosticSeverity.ERROR, "candidate identity appears more than once", cid))
            seen.add(cid)
            if candidate.source_origin_probability < self.min_source_origin_probability:
                local.append(Diagnostic("low_source_origin_probability", DiagnosticSeverity.ERROR, "source-origin probability is below policy threshold", cid))
            cited_chunk_ids = {e.chunk_id for e in candidate.evidence if e.chunk_id is not None}
            if not cited_chunk_ids:
                local.append(Diagnostic("missing_chunk_provenance", DiagnosticSeverity.ERROR, "candidate has no chunk-bound evidence", cid))
            for evidence in candidate.evidence:
                if evidence.chunk_id is None: continue
                chunk = chunk_by_id.get(evidence.chunk_id)
                if chunk is None:
                    local.append(Diagnostic("unknown_chunk", DiagnosticSeverity.ERROR, "evidence cites a chunk outside validator inputs", cid, evidence.evidence_id)); continue
                if evidence.exact_text not in chunk.text:
                    local.append(Diagnostic("evidence_text_mismatch", DiagnosticSeverity.ERROR, "exact evidence text is not present in cited chunk", cid, evidence.evidence_id))
                if evidence.conversation_id is not None and evidence.conversation_id != chunk.conversation_id:
                    local.append(Diagnostic("conversation_mismatch", DiagnosticSeverity.ERROR, "evidence conversation does not match cited chunk", cid, evidence.evidence_id))
                if evidence.source_id != chunk.source_id:
                    local.append(Diagnostic("source_mismatch", DiagnosticSeverity.ERROR, "evidence source does not match cited chunk", cid, evidence.evidence_id))
            if candidate.temporal.is_proxy:
                local.append(Diagnostic("proxy_time", DiagnosticSeverity.WARNING, "candidate uses explicit proxy time", cid))
            if candidate.extractor_confidence < 0.5:
                local.append(Diagnostic("low_extractor_confidence", DiagnosticSeverity.WARNING, "extractor confidence is below 0.5", cid))
            fatal = any(d.severity == DiagnosticSeverity.ERROR for d in local); diagnostics.extend(local)
            if fatal: quarantined.append(CandidateDisposition(candidate, False, tuple(local)))
            else: accepted.append(candidate)
        return ValidationResult(build, tuple(accepted), tuple(quarantined), tuple(sorted(diagnostics, key=lambda d: d.diagnostic_id)))
