from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
from typing import Sequence

from .build import BuildIdentity, canonical_json
from .conflict_model import ConflictCompilationResult, ConflictDisposition, EffectiveRelation
from .entity_model import EntityResolutionResult, HypothesisDisposition
from .projection_model import SynthesisProjectionResult
from .relation_model import RelationCompilationResult, RelationDisposition
from .review_model import (
    AdjudicationDisposition,
    AdjudicationRecord,
    AdjudicationResult,
    ReviewAuthority,
    ReviewDecision,
    ReviewItem,
    ReviewKind,
    ReviewPolicy,
    ReviewQueue,
    ReviewResponse,
)
from .semantic_model import ArgumentKind, SemanticNormalizationResult
from .temporal_model import Chronology, SupersessionDisposition, TemporalCompilationResult


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


class ReviewRouter:
    """K10 deterministic unresolved-item routing.

    The router never adjudicates upstream claims. It converts unresolved compiler state
    into review items and assigns the minimum authority needed by policy.
    """

    def __init__(self, *, compiler_version: str = "0.1.0", policy: ReviewPolicy | None = None):
        self.compiler_version = compiler_version
        self.policy = policy or ReviewPolicy()

    def compile(
        self,
        entity_resolution: EntityResolutionResult,
        normalized: SemanticNormalizationResult,
        relations: RelationCompilationResult,
        temporal: TemporalCompilationResult,
        conflicts: ConflictCompilationResult,
        projections: SynthesisProjectionResult,
    ) -> ReviewQueue:
        payload = {
            "entity_resolution": entity_resolution,
            "normalized": normalized,
            "relations": relations,
            "temporal": temporal,
            "conflicts": conflicts,
            "projections": projections,
        }
        input_hash = sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        config_hash = sha256(canonical_json(self.policy).encode("utf-8")).hexdigest()
        build = BuildIdentity(
            "K10.review_router",
            self.compiler_version,
            "eor.corpus_review_queue.v0",
            config_hash,
            input_hash,
        )

        assertion_by_id = {a.normalized_id: a for a in normalized.assertions}
        group_by_id = {g.group_id: g for g in normalized.groups}
        assertion_group: dict[str, str] = {}
        group_impact: dict[str, float] = {}
        group_entities: dict[str, set[str]] = defaultdict(set)
        for group in normalized.groups:
            values = []
            for assertion_id in group.normalized_assertion_ids:
                assertion_group[assertion_id] = group.group_id
                assertion = assertion_by_id.get(assertion_id)
                if assertion is not None:
                    values.append(0.6 * assertion.importance + 0.4 * assertion.durability)
            group_impact[group.group_id] = max(values) if values else 0.0
            for argument in (group.signature.subject, group.signature.object):
                if argument.kind == ArgumentKind.ENTITY:
                    group_entities[group.group_id].add(argument.value)

        card_by_entity = {card.entity_id: card for card in projections.cards}

        def entity_impact(entity_id: str) -> float:
            card = card_by_entity.get(entity_id)
            if card is None:
                return 0.0
            centrality = min(1.0, len(card.propositions) / self.policy.high_centrality_proposition_count)
            proposition_impact = max(
                (group_impact.get(p.group_id, 0.0) for p in card.propositions),
                default=0.0,
            )
            return _clamp(0.55 * proposition_impact + 0.45 * centrality)

        def groups_impact(group_ids: Sequence[str]) -> float:
            return max((group_impact.get(g, 0.0) for g in group_ids), default=0.0)

        def related_entities(group_ids: Sequence[str]) -> tuple[str, ...]:
            ids = set()
            for group_id in group_ids:
                ids.update(group_entities.get(group_id, set()))
            return tuple(sorted(ids))

        severity = {
            ReviewKind.ENTITY_RESOLUTION: 0.58,
            ReviewKind.RELATION: 0.46,
            ReviewKind.SUPERSESSION: 0.76,
            ReviewKind.CONFLICT: 0.86,
            ReviewKind.PROJECTION_DIAGNOSTIC: 0.34,
        }

        def route(kind: ReviewKind, impact: float, ambiguity: float, reason_codes: list[str]) -> tuple[float, ReviewAuthority]:
            priority = _clamp(0.45 * impact + 0.25 * ambiguity + 0.30 * severity[kind])
            high_consequence = kind in {
                ReviewKind.ENTITY_RESOLUTION,
                ReviewKind.SUPERSESSION,
                ReviewKind.CONFLICT,
            }
            if high_consequence and impact >= self.policy.dan_impact_threshold:
                reason_codes.append("high_consequence_high_impact")
                return priority, ReviewAuthority.DAN
            if priority >= self.policy.dan_priority_threshold:
                reason_codes.append("priority_exceeds_dan_threshold")
                return priority, ReviewAuthority.DAN
            if kind in {ReviewKind.SUPERSESSION, ReviewKind.CONFLICT} or priority >= self.policy.sol_priority_threshold:
                reason_codes.append("semantic_adjudication_required")
                return priority, ReviewAuthority.SOL
            return priority, ReviewAuthority.TERRA

        items: list[ReviewItem] = []

        for hypothesis in entity_resolution.hypotheses:
            if hypothesis.disposition == HypothesisDisposition.BLOCKED:
                continue
            impact = entity_impact(hypothesis.candidate_entity_id)
            ambiguity = _clamp(1.0 - hypothesis.score)
            reasons = ["unresolved_entity_identity", f"hypothesis_{hypothesis.disposition.value}"]
            priority, authority = route(ReviewKind.ENTITY_RESOLUTION, impact, ambiguity, reasons)
            items.append(ReviewItem(
                ReviewKind.ENTITY_RESOLUTION,
                hypothesis.hypothesis_id,
                hypothesis.score,
                ambiguity,
                impact,
                priority,
                authority,
                tuple(reasons),
                (hypothesis.candidate_entity_id,),
                (),
            ))

        for relation in relations.relations:
            if relation.disposition == RelationDisposition.STRUCTURAL:
                continue
            group_ids = (relation.key.source_group_id, relation.key.target_group_id)
            impact = groups_impact(group_ids)
            ambiguity = _clamp(1.0 - relation.score)
            reasons = ["semantic_relation_unresolved", f"relation_{relation.disposition.value}"]
            priority, authority = route(ReviewKind.RELATION, impact, ambiguity, reasons)
            items.append(ReviewItem(
                ReviewKind.RELATION,
                relation.relation_id,
                relation.score,
                ambiguity,
                impact,
                priority,
                authority,
                tuple(reasons),
                related_entities(group_ids),
                tuple(sorted(group_ids)),
            ))

        for supersession in temporal.supersessions:
            if supersession.disposition not in {SupersessionDisposition.SUGGESTED, SupersessionDisposition.REVIEW_REQUIRED}:
                continue
            group_ids = tuple(sorted({
                assertion_group.get(supersession.predecessor_assertion_id, ""),
                assertion_group.get(supersession.successor_assertion_id, ""),
            } - {""}))
            impact = groups_impact(group_ids)
            ambiguity = _clamp(1.0 - supersession.score)
            reasons = ["supersession_unresolved", f"supersession_{supersession.disposition.value}"]
            if supersession.chronology == Chronology.UNKNOWN:
                ambiguity = _clamp(ambiguity + 0.25)
                reasons.append("chronology_unknown")
            priority, authority = route(ReviewKind.SUPERSESSION, impact, ambiguity, reasons)
            items.append(ReviewItem(
                ReviewKind.SUPERSESSION,
                supersession.supersession_id,
                supersession.score,
                ambiguity,
                impact,
                priority,
                authority,
                tuple(reasons),
                related_entities(group_ids),
                group_ids,
            ))

        for conflict in conflicts.conflicts:
            if conflict.disposition == ConflictDisposition.TEMPORALLY_DISJOINT:
                continue
            group_ids = (conflict.left_group_id, conflict.right_group_id)
            impact = groups_impact(group_ids)
            ambiguity = _clamp(1.0 - conflict.score)
            reasons = ["conflict_unresolved", f"conflict_{conflict.disposition.value}"]
            if conflict.effective_relation == EffectiveRelation.UNKNOWN:
                ambiguity = _clamp(ambiguity + 0.25)
                reasons.append("effective_time_unknown")
            priority, authority = route(ReviewKind.CONFLICT, impact, ambiguity, reasons)
            items.append(ReviewItem(
                ReviewKind.CONFLICT,
                conflict.conflict_id,
                conflict.score,
                ambiguity,
                impact,
                priority,
                authority,
                tuple(reasons),
                related_entities(group_ids),
                tuple(sorted(group_ids)),
            ))

        for diagnostic in projections.diagnostics:
            entity_ids = (diagnostic.entity_id,) if diagnostic.entity_id else ()
            impact = max((entity_impact(e) for e in entity_ids), default=0.0)
            ambiguity = 0.70
            reasons = ["projection_diagnostic", diagnostic.code]
            priority, authority = route(ReviewKind.PROJECTION_DIAGNOSTIC, impact, ambiguity, reasons)
            items.append(ReviewItem(
                ReviewKind.PROJECTION_DIAGNOSTIC,
                diagnostic.diagnostic_id,
                0.50,
                ambiguity,
                impact,
                priority,
                authority,
                tuple(reasons),
                entity_ids,
                (),
            ))

        for card in projections.cards:
            for code in card.diagnostics:
                impact = entity_impact(card.entity_id)
                ambiguity = 0.65 if code == "latest_observed_not_unique" else 0.50
                reasons = ["entity_projection_diagnostic", code]
                priority, authority = route(ReviewKind.PROJECTION_DIAGNOSTIC, impact, ambiguity, reasons)
                items.append(ReviewItem(
                    ReviewKind.PROJECTION_DIAGNOSTIC,
                    f"{card.card_id}:{code}",
                    0.50,
                    ambiguity,
                    impact,
                    priority,
                    authority,
                    tuple(reasons),
                    (card.entity_id,),
                    (),
                ))

        dedup = {item.review_item_id: item for item in items}
        return ReviewQueue(build, tuple(sorted(dedup.values(), key=lambda item: (-item.priority, item.review_item_id))))


class ReviewAdjudicator:
    """K10 authority-aware adjudication over an immutable review queue."""

    def __init__(self, *, compiler_version: str = "0.1.0"):
        self.compiler_version = compiler_version

    def compile(self, queue: ReviewQueue, responses: Sequence[ReviewResponse]) -> AdjudicationResult:
        item_by_id = {item.review_item_id: item for item in queue.items}
        grouped: dict[str, list[ReviewResponse]] = defaultdict(list)
        for response in responses:
            if response.review_item_id not in item_by_id:
                raise ValueError("review response references item outside K10 queue")
            grouped[response.review_item_id].append(response)

        input_hash = sha256(canonical_json({"queue": queue, "responses": responses}).encode("utf-8")).hexdigest()
        config_hash = sha256(canonical_json({"authority_lattice": "terra<sol<dan"}).encode("utf-8")).hexdigest()
        build = BuildIdentity(
            "K10.review_adjudicator",
            self.compiler_version,
            "eor.corpus_adjudication.v0",
            config_hash,
            input_hash,
        )

        records: list[AdjudicationRecord] = []
        for item in queue.items:
            item_responses = sorted(grouped.get(item.review_item_id, []), key=lambda r: (-int(r.authority), r.response_id))
            response_ids = tuple(sorted(r.response_id for r in item_responses))
            eligible_final = [
                r for r in item_responses
                if r.authority >= item.route and r.decision in {ReviewDecision.ACCEPT, ReviewDecision.REJECT}
            ]
            if eligible_final:
                max_authority = max(r.authority for r in eligible_final)
                controlling = [r for r in eligible_final if r.authority == max_authority]
                decisions = {r.decision for r in controlling}
                if len(decisions) > 1:
                    records.append(AdjudicationRecord(
                        item.review_item_id,
                        AdjudicationDisposition.PENDING,
                        None,
                        response_ids,
                        max_authority,
                        "conflicting_same_authority_final_responses",
                    ))
                    continue
                winner = min(controlling, key=lambda r: r.response_id)
                disposition = (
                    AdjudicationDisposition.ACCEPTED
                    if winner.decision == ReviewDecision.ACCEPT
                    else AdjudicationDisposition.REJECTED
                )
                records.append(AdjudicationRecord(
                    item.review_item_id,
                    disposition,
                    winner.response_id,
                    response_ids,
                    winner.authority,
                    winner.reason,
                ))
                continue

            eligible_nonfinal = [r for r in item_responses if r.authority >= item.route]
            if eligible_nonfinal:
                max_authority = max(r.authority for r in eligible_nonfinal)
                controlling = [r for r in eligible_nonfinal if r.authority == max_authority]
                escalations = [r for r in controlling if r.decision == ReviewDecision.ESCALATE]
                if escalations:
                    winner = min(escalations, key=lambda r: r.response_id)
                    records.append(AdjudicationRecord(
                        item.review_item_id,
                        AdjudicationDisposition.ESCALATED,
                        winner.response_id,
                        response_ids,
                        winner.authority,
                        winner.reason,
                    ))
                else:
                    winner = min(controlling, key=lambda r: r.response_id)
                    records.append(AdjudicationRecord(
                        item.review_item_id,
                        AdjudicationDisposition.DEFERRED,
                        winner.response_id,
                        response_ids,
                        winner.authority,
                        winner.reason,
                    ))
                continue

            records.append(AdjudicationRecord(
                item.review_item_id,
                AdjudicationDisposition.PENDING,
                None,
                response_ids,
                None,
                "no_response_with_required_authority",
            ))

        return AdjudicationResult(build, tuple(sorted(records, key=lambda r: r.review_item_id)))
