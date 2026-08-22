import pytest

from eor_corpus_compiler.build import BuildIdentity
from eor_corpus_compiler.ir import EpistemicType, MemoryClass
from eor_corpus_compiler.relation_model import (
    RelationDisposition,
    RelationEvidence,
    RelationKey,
    RelationPolicy,
    RelationProposal,
    RelationType,
)
from eor_corpus_compiler.relations import RelationCompiler
from eor_corpus_compiler.semantic_model import (
    ArgumentKind,
    Polarity,
    SemanticArgumentIdentity,
    SemanticGroup,
    SemanticNormalizationResult,
    SemanticSignature,
)


def group(name: str, *, polarity=Polarity.POSITIVE, epistemic_type=EpistemicType.BELIEF):
    signature = SemanticSignature(
        SemanticArgumentIdentity(ArgumentKind.ENTITY, "entity:dan"),
        "like",
        SemanticArgumentIdentity(ArgumentKind.ENTITY, "entity:moa"),
        polarity,
        epistemic_type,
        MemoryClass.RELATIONSHIP,
    )
    return SemanticGroup(signature, (f"assertion:{name}",), (f"candidate:{name}",), f"candidate:{name}")


def normalized(*groups):
    build = BuildIdentity("test", "0", "test", "0" * 64, "1" * 64)
    return SemanticNormalizationResult(build, (), tuple(groups), ())


def evidence(score=0.9, source="model:1"):
    return (RelationEvidence("semantic_review", source, score, "review evidence", "terra"),)


def test_opposite_polarity_emits_structural_relation():
    positive = group("positive", polarity=Polarity.POSITIVE)
    negative = group("negative", polarity=Polarity.NEGATIVE)
    out = RelationCompiler().compile(normalized(positive, negative))
    assert len(out.relations) == 1
    rel = out.relations[0]
    assert rel.key.relation_type == RelationType.POLARITY_OPPOSES
    assert rel.disposition == RelationDisposition.STRUCTURAL
    assert rel.score == 1.0


def test_different_epistemic_type_does_not_structurally_oppose():
    positive = group("positive", polarity=Polarity.POSITIVE, epistemic_type=EpistemicType.BELIEF)
    negative = group("negative", polarity=Polarity.NEGATIVE, epistemic_type=EpistemicType.FACT)
    out = RelationCompiler().compile(normalized(positive, negative))
    assert out.relations == ()


def test_symmetric_external_relation_deduplicates_reverse_endpoints_and_fuses_evidence():
    left = group("left")
    # Force a distinct group while keeping tests simple by changing epistemic type.
    right = group("right", epistemic_type=EpistemicType.USER_STATEMENT)
    one = RelationProposal(RelationKey(left.group_id, right.group_id, RelationType.CONTRADICTS), "terra", evidence(0.6, "m1"))
    two = RelationProposal(RelationKey(right.group_id, left.group_id, RelationType.CONTRADICTS), "sol", evidence(0.7, "m2"))
    out = RelationCompiler().compile(normalized(left, right), proposals=(one, two))
    assert len(out.relations) == 1
    rel = out.relations[0]
    assert rel.proposers == ("sol", "terra")
    assert rel.score > 0.7


def test_negative_evidence_reduces_fused_score():
    left = group("left")
    right = group("right", epistemic_type=EpistemicType.USER_STATEMENT)
    key = RelationKey(left.group_id, right.group_id, RelationType.SUPPORTS)
    positive = RelationProposal(key, "terra", evidence(0.9, "positive"))
    mixed = RelationProposal(key, "sol", (RelationEvidence("critic", "negative", -0.5, "counterevidence", "sol"),))
    out = RelationCompiler().compile(normalized(left, right), proposals=(positive, mixed))
    assert len(out.relations) == 1
    assert 0.4 < out.relations[0].score < 0.5


def test_review_threshold_controls_external_disposition():
    left = group("left")
    right = group("right", epistemic_type=EpistemicType.USER_STATEMENT)
    proposal = RelationProposal(RelationKey(left.group_id, right.group_id, RelationType.REFINES), "terra", evidence(0.85))
    out = RelationCompiler(policy=RelationPolicy(review_threshold=0.8)).compile(normalized(left, right), proposals=(proposal,))
    assert out.relations[0].disposition == RelationDisposition.REVIEW_REQUIRED


def test_unknown_group_is_rejected():
    left = group("left")
    proposal = RelationProposal(RelationKey(left.group_id, "semgroupv0_unknown", RelationType.SUPPORTS), "terra", evidence())
    with pytest.raises(ValueError, match="unknown semantic group"):
        RelationCompiler().compile(normalized(left), proposals=(proposal,))


def test_directed_relation_preserves_endpoint_order():
    left = group("left")
    right = group("right", epistemic_type=EpistemicType.USER_STATEMENT)
    forward = RelationKey(left.group_id, right.group_id, RelationType.SUPERSEDES)
    reverse = RelationKey(right.group_id, left.group_id, RelationType.SUPERSEDES)
    assert forward.relation_key_id != reverse.relation_key_id


def test_compilation_is_deterministic_under_proposal_order():
    left = group("left")
    right = group("right", epistemic_type=EpistemicType.USER_STATEMENT)
    p1 = RelationProposal(RelationKey(left.group_id, right.group_id, RelationType.SUPPORTS), "terra", evidence(0.6, "one"))
    p2 = RelationProposal(RelationKey(left.group_id, right.group_id, RelationType.SUPPORTS), "sol", evidence(0.7, "two"))
    compiler = RelationCompiler()
    one = compiler.compile(normalized(left, right), proposals=(p1, p2))
    two = compiler.compile(normalized(left, right), proposals=(p2, p1))
    assert one.relations == two.relations
    assert one.output_hash == two.output_hash
