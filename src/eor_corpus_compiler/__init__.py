"""EOR Corpus Compiler K00-K09 primitives."""

from .build import BuildIdentity, canonical_json, content_id
from .conflict_model import (
    ConflictCase,
    ConflictCompilationResult,
    ConflictDiagnostic,
    ConflictDisposition,
    ConflictKind,
    ConflictPolicy,
    EffectiveRelation,
)
from .conflicts import ConflictCompiler, compare_effective_anchors, effective_interval
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
from .normalizer import SemanticNormalizer, normalize_semantic_text
from .projection_model import (
    EntityProjectionCard,
    ProjectionDiagnostic,
    ProjectionRole,
    PropositionProjection,
    SynthesisProjectionResult,
)
from .relation_model import (
    CompiledRelation,
    RelationCompilationResult,
    RelationDisposition,
    RelationEvidence,
    RelationKey,
    RelationPolicy,
    RelationProposal,
    RelationType,
)
from .relations import RelationCompiler
from .resolver import EntityResolver
from .semantic_model import (
    ArgumentKind,
    ArgumentResolutionDecision,
    ArgumentRole,
    NormalizationDiagnostic,
    NormalizedAssertion,
    Polarity,
    PredicateAlias,
    PredicateOntology,
    SemanticArgument,
    SemanticArgumentIdentity,
    SemanticGroup,
    SemanticNormalizationResult,
    SemanticSignature,
)
from .synthesis import SynthesisProjector
from .temporal import TemporalCompiler, compare_source_times
from .temporal_model import (
    Chronology,
    CompiledSupersession,
    StateSlotKey,
    SupersessionDisposition,
    SupersessionEvidence,
    SupersessionProposal,
    TemporalCompilationResult,
    TemporalDiagnostic,
    TemporalOccurrence,
    TemporalPolicy,
    TemporalStateSlot,
)
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
    "ArgumentKind", "ArgumentResolutionDecision", "ArgumentRole", "NormalizationDiagnostic",
    "NormalizedAssertion", "Polarity", "PredicateAlias", "PredicateOntology", "SemanticArgument",
    "SemanticArgumentIdentity", "SemanticGroup", "SemanticNormalizationResult", "SemanticSignature",
    "SemanticNormalizer", "normalize_semantic_text",
    "CompiledRelation", "RelationCompilationResult", "RelationDisposition", "RelationEvidence",
    "RelationKey", "RelationPolicy", "RelationProposal", "RelationType", "RelationCompiler",
    "Chronology", "CompiledSupersession", "StateSlotKey", "SupersessionDisposition",
    "SupersessionEvidence", "SupersessionProposal", "TemporalCompilationResult", "TemporalDiagnostic",
    "TemporalOccurrence", "TemporalPolicy", "TemporalStateSlot", "TemporalCompiler", "compare_source_times",
    "ConflictCase", "ConflictCompilationResult", "ConflictDiagnostic", "ConflictDisposition", "ConflictKind",
    "ConflictPolicy", "EffectiveRelation", "ConflictCompiler", "compare_effective_anchors", "effective_interval",
    "EntityProjectionCard", "ProjectionDiagnostic", "ProjectionRole", "PropositionProjection",
    "SynthesisProjectionResult", "SynthesisProjector",
]
