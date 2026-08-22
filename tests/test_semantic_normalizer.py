from eor_corpus_compiler.entity_model import ResolutionEvidence
from eor_corpus_compiler.ir import (
    CandidateAssertion,
    EntityMention,
    EpistemicType,
    EvidenceSpan,
    MemoryClass,
    ModelLineage,
    TemporalAnchor,
    TemporalPrecision,
)
from eor_corpus_compiler.mentions import EntityMentionCompiler
from eor_corpus_compiler.normalizer import SemanticNormalizer
from eor_corpus_compiler.resolver import EntityResolver
from eor_corpus_compiler.semantic_model import (
    ArgumentResolutionDecision,
    ArgumentRole,
    Polarity,
    PredicateAlias,
    PredicateOntology,
)


def candidate(
    suffix: str,
    *,
    subject: str = "Dan",
    predicate: str = "likes",
    object_: str = "Moa",
    epistemic_type: EpistemicType = EpistemicType.USER_STATEMENT,
    memory_class: MemoryClass = MemoryClass.RELATIONSHIP,
    mention_subject: bool = True,
    mention_object: bool = True,
) -> CandidateAssertion:
    evidence = EvidenceSpan(
        f"source:{suffix}",
        "chat_message",
        f"conversation:{suffix}",
        f"message:{suffix}",
        f"chunk:{suffix}",
        "Dan",
        f"evidence text {suffix}",
    )
    mentions = []
    if mention_subject:
        mentions.append(EntityMention(subject, "person", evidence.evidence_id, subject, 0.95))
    if mention_object:
        mentions.append(EntityMention(object_, "person", evidence.evidence_id, object_, 0.95))
    return CandidateAssertion(
        statement=f"{subject} {predicate} {object_} ({suffix})",
        subject=subject,
        predicate=predicate,
        object=object_,
        epistemic_type=epistemic_type,
        memory_class=memory_class,
        evidence=(evidence,),
        temporal=TemporalAnchor(f"2026-08-{20 + int(suffix):02d}", None, TemporalPrecision.DAY, "America/Toronto"),
        entity_mentions=tuple(mentions),
        tags=("test",),
        lineage=ModelLineage("test", "model", "extractor", "contract", "1"),
        extractor_confidence=0.9,
        source_origin_probability=1.0,
        importance=0.7,
        durability=0.7,
    )


def registry_for(*candidates: CandidateAssertion):
    mentions = EntityMentionCompiler().compile(candidates)
    return EntityResolver().compile(mentions).registry


def test_repeated_semantic_occurrences_group_without_losing_occurrences():
    one = candidate("1")
    two = candidate("2")
    registry = registry_for(one, two)
    result = SemanticNormalizer().compile((one, two), registry)
    assert len(result.assertions) == 2
    assert len(result.groups) == 1
    assert len(result.groups[0].candidate_ids) == 2
    assert {a.temporal.start for a in result.assertions} == {"2026-08-21", "2026-08-22"}


def test_epistemic_type_prevents_false_deduplication():
    one = candidate("1", epistemic_type=EpistemicType.BELIEF)
    two = candidate("2", epistemic_type=EpistemicType.FACT)
    registry = registry_for(one, two)
    result = SemanticNormalizer().compile((one, two), registry)
    assert len(result.groups) == 2


def test_negative_predicate_is_separate_semantic_signature():
    one = candidate("1", predicate="likes")
    two = candidate("2", predicate="does_not_like")
    registry = registry_for(one, two)
    result = SemanticNormalizer().compile((one, two), registry)
    assert len(result.groups) == 2
    assert {a.signature.polarity for a in result.assertions} == {Polarity.POSITIVE, Polarity.NEGATIVE}


def test_versioned_predicate_ontology_can_enable_exact_deduplication():
    one = candidate("1", predicate="plans_to", object_="build EOR", mention_object=False, memory_class=MemoryClass.PLAN)
    two = candidate("2", predicate="intends_to", object_="build EOR", mention_object=False, memory_class=MemoryClass.PLAN)
    registry = registry_for(one, two)
    ontology = PredicateOntology((PredicateAlias("intends_to", "plans_to"),))
    result = SemanticNormalizer(predicate_ontology=ontology).compile((one, two), registry)
    assert len(result.groups) == 1


def test_unresolved_argument_stays_literal_and_is_diagnosed():
    item = candidate("1", object_="a future unnamed project", mention_object=False)
    registry = registry_for(item)
    result = SemanticNormalizer().compile((item,), registry)
    assert result.assertions[0].signature.object.kind.value == "literal"
    assert any(d.code == "unresolved_literal_argument" and d.role == ArgumentRole.OBJECT for d in result.diagnostics)


def test_explicit_argument_decision_can_resolve_nonlexical_coreference():
    moa_source = candidate("1")
    registry = registry_for(moa_source)
    moa_entity = next(e for e in registry.entities if e.canonical_name.casefold() == "moa")
    item = candidate("2", object_="my wife", mention_object=False)
    decision = ArgumentResolutionDecision(
        item.candidate_id,
        ArgumentRole.OBJECT,
        moa_entity.entity_id,
        "human",
        (ResolutionEvidence("coreference_review", "review:1", 1.0, "my wife refers to Moa", "human"),),
    )
    result = SemanticNormalizer().compile((item,), registry, argument_decisions=(decision,))
    assert result.assertions[0].signature.object.value == moa_entity.entity_id
    assert result.assertions[0].signature.object.basis == "explicit_argument_decision"
