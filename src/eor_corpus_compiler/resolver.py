from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from typing import Sequence

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
from .entity_similarity import compatible_types, fuse_evidence, normalize_entity_name, similarity_evidence, trigrams
from .mentions import MentionIndex, MentionKey


def _entity_seed_id(key: MentionKey) -> str:
    seed = {"anchor_mention_key_id": key.mention_key_id, "entity_type": key.entity_type_hint}
    return content_id("entityv0", seed)


def _pair(left: str, right: str) -> tuple[str, str]:
    a, b = sorted((left, right))
    return a, b


class EntityResolver:
    """K04 global identity compiler.

    Safe default: only a previously verified alias or an explicit resolution
    decision can alter mention-to-entity identity. Extractor canonical hints,
    fuzzy similarity, and external model proposals remain reviewable hypotheses.
    """

    def __init__(self, *, compiler_version: str = "0.1.0", policy: EntityResolutionPolicy | None = None):
        self.compiler_version = compiler_version
        self.policy = policy or EntityResolutionPolicy()

    def compile(
        self,
        mention_index: MentionIndex,
        *,
        prior: EntityRegistrySnapshot | None = None,
        decisions: Sequence[ResolutionDecision] = (),
        proposals: Sequence[ResolutionProposal] = (),
    ) -> EntityResolutionResult:
        prior = prior or EntityRegistrySnapshot()
        input_payload = {
            "mentions": mention_index.buckets,
            "prior": prior,
            "decisions": decisions,
            "proposals": proposals,
        }
        input_hash = sha256(canonical_json(input_payload).encode("utf-8")).hexdigest()
        config_hash = sha256(canonical_json(self.policy).encode("utf-8")).hexdigest()
        build = BuildIdentity(
            "K04.resolve_entities",
            self.compiler_version,
            "eor.corpus_entity_resolution.v0",
            config_hash,
            input_hash,
        )

        entities = {e.entity_id: e for e in prior.entities}
        bindings = {b.mention_key_id: b for b in prior.bindings}
        redirects = {r.source_entity_id: r for r in prior.redirects}
        constraints = {_pair(c.left_entity_id, c.right_entity_id): c for c in prior.constraints}
        applied = set(prior.applied_decision_ids)
        retracted = set(prior.retracted_decision_ids)
        decision_log = {d.decision_id: d for d in prior.decision_log}
        for decision in decisions:
            decision_log[decision.decision_id] = decision

        newly_retracted = {
            d.subject_id for d in decisions if d.action == ResolutionAction.RETRACT_DECISION
        }
        if prior.entities and newly_retracted & set(prior.applied_decision_ids):
            raise FullRebuildRequired(
                "retracting an already-projected decision requires K04 replay from an empty registry over the full mention index"
            )
        retracted.update(newly_retracted)

        bucket_by_key = {b.key.mention_key_id: b for b in mention_index.buckets}
        if len(bucket_by_key) != len(mention_index.buckets):
            raise ValueError("mention index contains duplicate mention keys")

        def active(entity_id: str) -> str:
            seen: set[str] = set()
            current = entity_id
            while current in redirects:
                if current in seen:
                    raise ValueError("entity redirect cycle detected")
                seen.add(current)
                current = redirects[current].target_entity_id
            return current

        def rebuild_aliases() -> None:
            alias_map: dict[str, dict[str, tuple[set[str], set[str]]]] = {}

            # Preserve aliases from prior delta snapshots and move them through redirects.
            for entity in entities.values():
                target = active(entity.entity_id)
                amap = alias_map.setdefault(target, {})
                for alias in entity.aliases:
                    forms, keys = amap.setdefault(alias.normalized, (set(), set()))
                    forms.update(alias.display_forms)
                    keys.update(alias.mention_key_ids)

            # Add aliases proven by current mention bindings.
            for binding in bindings.values():
                eid = active(binding.entity_id)
                bucket = bucket_by_key.get(binding.mention_key_id)
                if bucket is None:
                    continue
                normalized = normalize_entity_name(bucket.key.normalized_text)
                display_forms = {
                    occurrence.mention.mention_text.strip()
                    for occurrence in bucket.occurrences
                    if occurrence.mention.mention_text.strip()
                }
                amap = alias_map.setdefault(eid, {})
                forms, keys = amap.setdefault(normalized, (set(), set()))
                forms.update(display_forms)
                keys.add(binding.mention_key_id)

            for eid, entity in list(entities.items()):
                if active(eid) != eid:
                    entities[eid] = replace(entity, status=EntityStatus.REDIRECTED)
                    continue
                amap = alias_map.get(eid, {})
                aliases = tuple(
                    EntityAlias(
                        normalized,
                        tuple(sorted(forms, key=str.casefold)),
                        tuple(sorted(keys)),
                    )
                    for normalized, (forms, keys) in sorted(amap.items())
                )
                entities[eid] = replace(entity, aliases=aliases, status=EntityStatus.ACTIVE)

        # Only prior verified aliases are eligible for automatic identity reuse.
        prior_alias_index: dict[str, set[str]] = {}
        for entity in prior.entities:
            if entity.status != EntityStatus.ACTIVE:
                continue
            for alias in entity.aliases:
                prior_alias_index.setdefault(alias.normalized, set()).add(active(entity.entity_id))

        decision_by_mention: dict[str, ResolutionDecision] = {}
        other_decisions: list[ResolutionDecision] = []
        for decision in sorted(decision_log.values(), key=lambda d: d.decision_id):
            if decision.action == ResolutionAction.RETRACT_DECISION or decision.decision_id in retracted:
                continue
            if decision.decision_id in applied:
                continue
            if decision.action == ResolutionAction.LINK_MENTION:
                if decision.subject_id in decision_by_mention:
                    raise ValueError("multiple unresolved link decisions target one mention key")
                decision_by_mention[decision.subject_id] = decision
            else:
                other_decisions.append(decision)

        # Bind every current mention key to either a prior entity or a stable provisional entity.
        for bucket in sorted(mention_index.buckets, key=lambda b: b.key.mention_key_id):
            key_id = bucket.key.mention_key_id
            if key_id in bindings:
                bindings[key_id] = replace(bindings[key_id], entity_id=active(bindings[key_id].entity_id))
                continue

            explicit = decision_by_mention.get(key_id)
            if explicit is not None:
                target = active(explicit.object_id or "")
                if target not in entities:
                    raise ValueError("link decision targets unknown entity")
                if not compatible_types(bucket.key.entity_type_hint, entities[target].entity_type):
                    raise ValueError("link decision crosses incompatible entity types")
                bindings[key_id] = MentionBinding(key_id, target, "explicit_decision", explicit.decision_id)
                applied.add(explicit.decision_id)
                continue

            normalized = normalize_entity_name(bucket.key.normalized_text)
            exact_targets = {
                active(eid)
                for eid in prior_alias_index.get(normalized, set())
                if active(eid) in entities
                and compatible_types(bucket.key.entity_type_hint, entities[active(eid)].entity_type)
            }
            if self.policy.auto_bind_verified_aliases and len(exact_targets) == 1:
                bindings[key_id] = MentionBinding(key_id, next(iter(exact_targets)), "verified_alias")
                continue

            entity_id = _entity_seed_id(bucket.key)
            if entity_id not in entities:
                display_forms = sorted(
                    {
                        occurrence.mention.mention_text.strip()
                        for occurrence in bucket.occurrences
                        if occurrence.mention.mention_text.strip()
                    },
                    key=lambda x: (x.casefold(), x),
                )
                if not display_forms:
                    raise ValueError("mention bucket has no displayable occurrences")
                entities[entity_id] = EntityRecord(
                    entity_id,
                    bucket.key.entity_type_hint,
                    display_forms[0],
                    (),
                    key_id,
                )
            bindings[key_id] = MentionBinding(key_id, entity_id, "provisional_seed")

        rebuild_aliases()

        # Apply auditable identity decisions only after every referenced provisional exists.
        for decision in other_decisions:
            if decision.action == ResolutionAction.MERGE_ENTITY:
                source = active(decision.subject_id)
                target = active(decision.object_id or "")
                if source not in entities or target not in entities:
                    raise ValueError("merge decision references unknown entity")
                if source == target:
                    applied.add(decision.decision_id)
                    continue
                if _pair(source, target) in constraints:
                    raise ValueError("merge decision conflicts with keep-distinct constraint")
                if not compatible_types(entities[source].entity_type, entities[target].entity_type):
                    raise ValueError("merge decision crosses incompatible entity types")
                redirects[source] = EntityRedirect(source, target, decision.decision_id)
                for key_id, binding in list(bindings.items()):
                    if binding.entity_id == source or active(binding.entity_id) == target:
                        bindings[key_id] = replace(
                            binding,
                            entity_id=target,
                            basis="merged_entity",
                            decision_id=decision.decision_id,
                        )
                applied.add(decision.decision_id)

            elif decision.action == ResolutionAction.KEEP_DISTINCT:
                left = active(decision.subject_id)
                right = active(decision.object_id or "")
                if left not in entities or right not in entities:
                    raise ValueError("keep-distinct decision references unknown entity")
                constraints[_pair(left, right)] = EntityPairConstraint(left, right, decision.decision_id)
                applied.add(decision.decision_id)

            elif decision.action == ResolutionAction.SET_CANONICAL_NAME:
                target = active(decision.subject_id)
                if target not in entities:
                    raise ValueError("canonical-name decision references unknown entity")
                entities[target] = replace(
                    entities[target], canonical_name=(decision.canonical_name or "").strip()
                )
                applied.add(decision.decision_id)

            else:
                raise ValueError(f"unsupported decision action: {decision.action.value}")

        for key_id, binding in list(bindings.items()):
            target = active(binding.entity_id)
            if target != binding.entity_id:
                bindings[key_id] = replace(binding, entity_id=target)
        rebuild_aliases()

        # Candidate generation is indexed by exact alias and trigrams, not all-pairs O(N^2).
        active_entities = [e for e in entities.values() if e.status == EntityStatus.ACTIVE]
        alias_index: dict[str, set[str]] = {}
        trigram_index: dict[str, set[str]] = {}
        for entity in active_entities:
            names = {normalize_entity_name(entity.canonical_name)}
            names.update(alias.normalized for alias in entity.aliases)
            for name in names:
                if not name:
                    continue
                alias_index.setdefault(name, set()).add(entity.entity_id)
                for gram in trigrams(name):
                    trigram_index.setdefault(gram, set()).add(entity.entity_id)

        proposal_map: dict[tuple[str, str], list[ResolutionEvidence]] = {}
        for proposal in sorted(proposals, key=lambda p: p.proposal_id):
            if proposal.mention_key_id not in bucket_by_key:
                raise ValueError("resolution proposal references unknown mention key")
            target = active(proposal.candidate_entity_id)
            if target not in entities or entities[target].status != EntityStatus.ACTIVE:
                raise ValueError("resolution proposal references unknown/inactive entity")
            proposal_map.setdefault((proposal.mention_key_id, target), []).extend(proposal.evidence)

        hypotheses: list[EntityHypothesis] = []
        for bucket in mention_index.buckets:
            key_id = bucket.key.mention_key_id
            bound_id = active(bindings[key_id].entity_id)
            query_names = {normalize_entity_name(bucket.key.normalized_text)}
            query_names.update(
                normalize_entity_name(hint)
                for hint in bucket.canonical_hints
                if normalize_entity_name(hint)
            )

            candidate_ids = {eid for (mention_id, eid) in proposal_map if mention_id == key_id}
            for query in query_names:
                candidate_ids.update(alias_index.get(query, set()))
                grams = trigrams(query)
                gram_hits: dict[str, int] = {}
                for gram in grams:
                    for eid in trigram_index.get(gram, set()):
                        gram_hits[eid] = gram_hits.get(eid, 0) + 1
                candidate_ids.update(
                    eid for eid, hits in gram_hits.items() if grams and hits / len(grams) >= 0.35
                )

            for eid in sorted(candidate_ids):
                eid = active(eid)
                if eid == bound_id or eid not in entities:
                    continue
                entity = entities[eid]
                if not compatible_types(bucket.key.entity_type_hint, entity.entity_type):
                    continue

                blocked = _pair(bound_id, eid) in constraints
                evidence = list(proposal_map.get((key_id, eid), ()))
                target_names = {normalize_entity_name(entity.canonical_name)}
                target_names.update(alias.normalized for alias in entity.aliases)

                for hint in bucket.canonical_hints:
                    normalized_hint = normalize_entity_name(hint)
                    if normalized_hint and normalized_hint in target_names:
                        evidence.append(
                            ResolutionEvidence(
                                "canonical_hint_exact",
                                key_id,
                                self.policy.canonical_hint_weight,
                                f"canonical hint {hint!r} exactly matches entity alias",
                                "K04.rule",
                            )
                        )

                for target_name in target_names:
                    item = similarity_evidence(
                        key_id,
                        bucket.key.normalized_text,
                        target_name,
                        self.policy,
                    )
                    if item is not None:
                        evidence.append(item)

                if not evidence:
                    continue
                evidence_tuple = tuple(sorted(evidence, key=lambda item: item.evidence_id))
                score = fuse_evidence(evidence_tuple)
                disposition = (
                    HypothesisDisposition.BLOCKED
                    if blocked
                    else HypothesisDisposition.REVIEW_REQUIRED
                    if score >= self.policy.review_threshold
                    else HypothesisDisposition.SUGGESTED
                )
                hypotheses.append(
                    EntityHypothesis(key_id, eid, score, evidence_tuple, disposition)
                )

        registry = EntityRegistrySnapshot(
            entities=tuple(sorted(entities.values(), key=lambda e: e.entity_id)),
            bindings=tuple(sorted(bindings.values(), key=lambda b: b.mention_key_id)),
            redirects=tuple(sorted(redirects.values(), key=lambda r: r.source_entity_id)),
            constraints=tuple(
                sorted(constraints.values(), key=lambda c: (c.left_entity_id, c.right_entity_id))
            ),
            decision_log=tuple(sorted(decision_log.values(), key=lambda d: d.decision_id)),
            applied_decision_ids=tuple(sorted(applied)),
            retracted_decision_ids=tuple(sorted(retracted)),
        )
        hypotheses_tuple = tuple(sorted(hypotheses, key=lambda h: h.hypothesis_id))
        return EntityResolutionResult(build, registry, hypotheses_tuple)
