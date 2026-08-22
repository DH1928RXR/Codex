import pytest

from eor_corpus_compiler.build import BuildIdentity
from eor_corpus_compiler.entity_model import (
    EntityResolutionPolicy,
    EntityStatus,
    FullRebuildRequired,
    HypothesisDisposition,
    ResolutionAction,
    ResolutionDecision,
    ResolutionEvidence,
    ResolutionProposal,
)
from eor_corpus_compiler.ir import EntityMention
from eor_corpus_compiler.mentions import MentionBucket, MentionIndex, MentionKey, MentionOccurrence
from eor_corpus_compiler.resolver import EntityResolver


def bucket(name: str, entity_type: str = "person", hints=()) -> MentionBucket:
    key = MentionKey(name.casefold(), entity_type)
    mention = EntityMention(name, entity_type, f"evidence:{name}", hints[0] if hints else None, 0.9)
    return MentionBucket(key, (MentionOccurrence(f"candidate:{name}", mention),), tuple(hints))


def index(*buckets: MentionBucket) -> MentionIndex:
    build = BuildIdentity("test", "0", "test", "0" * 64, "1" * 64)
    return MentionIndex(build, tuple(buckets))


def evidence(reason: str = "verified"):
    return (ResolutionEvidence("review", "review:1", 1.0, reason, "test"),)


def test_provisional_entity_identity_is_stable():
    one = EntityResolver().compile(index(bucket("Moa")))
    two = EntityResolver().compile(index(bucket("Moa")))
    assert one.registry.entities[0].entity_id == two.registry.entities[0].entity_id
    assert one.output_hash == two.output_hash


def test_prior_verified_alias_is_reused():
    first = EntityResolver().compile(index(bucket("Moa")))
    second = EntityResolver().compile(index(bucket("Moa")), prior=first.registry)
    assert second.registry.bindings[0].entity_id == first.registry.entities[0].entity_id


def test_canonical_hint_generates_hypothesis_without_silent_merge():
    base = EntityResolver().compile(index(bucket("Moa")))
    new = EntityResolver().compile(index(bucket("my wife", hints=("Moa",))), prior=base.registry)
    assert len([e for e in new.registry.entities if e.status == EntityStatus.ACTIVE]) == 2
    assert any(h.candidate_entity_id == base.registry.entities[0].entity_id for h in new.hypotheses)


def test_explicit_link_binds_mention_to_existing_entity():
    base = EntityResolver().compile(index(bucket("Moa")))
    target = base.registry.entities[0].entity_id
    new_bucket = bucket("my wife", hints=("Moa",))
    decision = ResolutionDecision(
        ResolutionAction.LINK_MENTION,
        new_bucket.key.mention_key_id,
        target,
        "human",
        evidence(),
    )
    new = EntityResolver().compile(index(new_bucket), prior=base.registry, decisions=(decision,))
    assert new.registry.bindings[-1].entity_id == target
    assert decision.decision_id in new.registry.applied_decision_ids


def test_merge_preserves_redirect_and_rebinds_mentions():
    first = EntityResolver().compile(index(bucket("Moa"), bucket("my wife")))
    active = [e for e in first.registry.entities if e.status == EntityStatus.ACTIVE]
    source, target = active[0].entity_id, active[1].entity_id
    decision = ResolutionDecision(
        ResolutionAction.MERGE_ENTITY,
        source,
        target,
        "human",
        evidence(),
    )
    second = EntityResolver().compile(
        index(bucket("Moa"), bucket("my wife")),
        prior=first.registry,
        decisions=(decision,),
    )
    assert any(r.source_entity_id == source and r.target_entity_id == target for r in second.registry.redirects)
    assert {binding.entity_id for binding in second.registry.bindings} == {target}


def test_keep_distinct_constraint_blocks_soft_hypothesis():
    first = EntityResolver().compile(index(bucket("Moa"), bucket("Moa Hebb")))
    active = [e for e in first.registry.entities if e.status == EntityStatus.ACTIVE]
    decision = ResolutionDecision(
        ResolutionAction.KEEP_DISTINCT,
        active[0].entity_id,
        active[1].entity_id,
        "human",
        evidence(),
    )
    policy = EntityResolutionPolicy(fuzzy_candidate_threshold=0.1, review_threshold=0.1)
    second = EntityResolver(policy=policy).compile(
        index(bucket("Moa"), bucket("Moa Hebb")),
        prior=first.registry,
        decisions=(decision,),
    )
    assert any(h.disposition == HypothesisDisposition.BLOCKED for h in second.hypotheses)


def test_entity_type_conflict_prevents_alias_auto_link():
    first = EntityResolver().compile(index(bucket("Arc", "person")))
    second = EntityResolver().compile(index(bucket("Arc", "project")), prior=first.registry)
    assert len([e for e in second.registry.entities if e.status == EntityStatus.ACTIVE]) == 2


def test_delta_compile_preserves_prior_aliases():
    first = EntityResolver().compile(index(bucket("Moa")))
    second = EntityResolver().compile(index(bucket("my wife", hints=("Moa",))), prior=first.registry)
    old = next(e for e in second.registry.entities if e.entity_id == first.registry.entities[0].entity_id)
    assert any(alias.normalized == "moa" for alias in old.aliases)


def test_external_context_proposal_is_fused_but_not_auto_merged():
    base = EntityResolver().compile(index(bucket("Moa")))
    new_bucket = bucket("my wife")
    proposal = ResolutionProposal(
        new_bucket.key.mention_key_id,
        base.registry.entities[0].entity_id,
        "terra",
        (ResolutionEvidence("context_coreference", "candidate:ctx", 0.85, "context strongly indicates same person", "terra"),),
    )
    out = EntityResolver().compile(index(new_bucket), prior=base.registry, proposals=(proposal,))
    assert any(h.score >= 0.85 for h in out.hypotheses)
    assert len([e for e in out.registry.entities if e.status == EntityStatus.ACTIVE]) == 2


def test_retracting_projected_decision_requires_full_rebuild():
    base = EntityResolver().compile(index(bucket("Moa")))
    target = base.registry.entities[0].entity_id
    new_bucket = bucket("my wife")
    decision = ResolutionDecision(
        ResolutionAction.LINK_MENTION,
        new_bucket.key.mention_key_id,
        target,
        "human",
        evidence(),
    )
    projected = EntityResolver().compile(index(new_bucket), prior=base.registry, decisions=(decision,))
    retract = ResolutionDecision(
        ResolutionAction.RETRACT_DECISION,
        decision.decision_id,
        None,
        "human",
        evidence("retract"),
    )
    with pytest.raises(FullRebuildRequired):
        EntityResolver().compile(index(new_bucket), prior=projected.registry, decisions=(retract,))
