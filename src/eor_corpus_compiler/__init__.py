"""EOR Corpus Compiler C00/C01 primitives."""

from .ir import CandidateAssertion, CorpusChunk, EntityMention, EpistemicType, EvidenceSpan, MemoryClass, ModelLineage, TemporalAnchor, TemporalPrecision
from .build import BuildIdentity, canonical_json, content_id
from .extractor import ExtractionBackend, ExtractionCompiler, ExtractionResult

__all__ = ["CandidateAssertion", "CorpusChunk", "EntityMention", "EpistemicType", "EvidenceSpan", "MemoryClass", "ModelLineage", "TemporalAnchor", "TemporalPrecision", "BuildIdentity", "canonical_json", "content_id", "ExtractionBackend", "ExtractionCompiler", "ExtractionResult"]
