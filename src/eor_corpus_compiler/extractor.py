from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol, Sequence

from .build import BuildIdentity, canonical_json
from .ir import CandidateAssertion, CorpusChunk


EXTRACTION_CONTRACT = "eor.corpus_candidate_assertion.v0"
PROMPT_CONTRACT = "eor.corpus_extraction_prompt.v0"


class ExtractionBackend(Protocol):
    """Interchangeable model/runtime boundary. Backends never receive write authority."""

    provider: str
    model: str

    def extract(self, chunks: Sequence[CorpusChunk]) -> Sequence[CandidateAssertion]:
        ...


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    build: BuildIdentity
    input_chunk_ids: tuple[str, ...]
    candidates: tuple[CandidateAssertion, ...]

    @property
    def output_hash(self) -> str:
        return sha256(canonical_json(self.candidates).encode("utf-8")).hexdigest()


class ExtractionCompiler:
    """C01 coordinator: deterministic inputs/outputs around a non-deterministic backend."""

    def __init__(self, backend: ExtractionBackend, *, compiler_version: str = "0.1.0", config: dict | None = None):
        self.backend = backend
        self.compiler_version = compiler_version
        self.config = config or {}

    def compile(self, chunks: Sequence[CorpusChunk]) -> ExtractionResult:
        if not chunks:
            raise ValueError("compile requires at least one chunk")
        ordered = tuple(sorted(chunks, key=lambda c: (c.conversation_id, c.occurred_at or "", c.chunk_id)))
        config_hash = sha256(canonical_json(self.config).encode("utf-8")).hexdigest()
        input_hash = sha256(canonical_json(ordered).encode("utf-8")).hexdigest()
        build = BuildIdentity(
            compiler="C01.extract",
            compiler_version=self.compiler_version,
            contract=EXTRACTION_CONTRACT,
            config_hash=config_hash,
            input_hash=input_hash,
        )
        raw = self.backend.extract(ordered)
        candidates = tuple(sorted(raw, key=lambda c: c.candidate_id))
        self._validate_result(ordered, candidates)
        return ExtractionResult(
            build=build,
            input_chunk_ids=tuple(c.chunk_id for c in ordered),
            candidates=candidates,
        )

    @staticmethod
    def _validate_result(chunks: Sequence[CorpusChunk], candidates: Sequence[CandidateAssertion]) -> None:
        chunk_ids = {c.chunk_id for c in chunks}
        candidate_ids: set[str] = set()
        for candidate in candidates:
            if candidate.candidate_id in candidate_ids:
                raise ValueError(f"duplicate candidate: {candidate.candidate_id}")
            candidate_ids.add(candidate.candidate_id)
            for evidence in candidate.evidence:
                if evidence.chunk_id is not None and evidence.chunk_id not in chunk_ids:
                    raise ValueError("candidate cites chunk outside compiler input")
