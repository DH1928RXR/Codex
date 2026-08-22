"""EOR Corpus Compiler K00-K04 primitives."""

from .build import BuildIdentity, canonical_json, content_id
from .entity_model import (
    EntityAlias,
    EntityHypothesis,
    EntityPairConstraint,
    EntityRecord,
    EntityRedirect,
    EntityRegistrySnapshot,
    EntityResolutionPolicy,
    EntityResolutionResult,
    EntityStatus,
    FullRebuildRequired,
    HypothesisDisposition,
    MentionBinding,
    ResolutionAction,
    ResolutionDecision,
    ResolutionEvidence,
    ResolutionProposal,
)
from .extractor import ExtractionBackend, ExtractionCompiler, ExtractionResult
from .ir import (
    CandidateAssertion,
    CorpusChunk,
    EntityMention,
    EpistemicType,
    EvidenceSpan,
    MemoryClass,
    ModelLineage,
    TemporalAnchor,
    TemporalPrecision,
)
from .mentions import EntityMentionCompiler, MentionBucket, MentionIndex, MentionKey, MentionOccurrence
from .resolver import EntityResolver
from .validator import CandidateValidator, ValidationResult

__all__ = [
    "BuildIdentity", "canonical_json", "content_id",
    "CandidateAssertion", "CorpusChunk", "EntityMention", "EpistemicType", "EvidenceSpan",
    "MemoryClass", "ModelLineage", "TemporalAnchor", "TemporalPrecision",
    "ExtractionBackend", "ExtractionCompiler", "ExtractionResult",
    "CandidateValidator", "ValidationResult",
    "EntityMentionCompiler", "MentionBucket", "MentionIndex", "MentionKey", "MentionOccurrence",
    "EntityAlias", "EntityHypothesis", "EntityPairConstraint", "EntityRecord", "EntityRedirect",
    "EntityRegistrySnapshot", "EntityResolutionPolicy", "EntityResolutionResult", "EntityStatus",
    "FullRebuildRequired", "HypothesisDisposition", "MentionBinding", "ResolutionAction",
    "ResolutionDecision", "ResolutionEvidence", "ResolutionProposal", "EntityResolver",
]
