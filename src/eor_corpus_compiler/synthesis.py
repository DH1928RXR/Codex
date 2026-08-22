from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
from typing import Sequence

from .build import BuildIdentity, canonical_json
from .conflict_model import ConflictCompilationResult
from .entity_model import EntityResolutionResult, EntityStatus, HypothesisDisposition
from .relation_model import RelationCompilationResult
from .semantic_model import ArgumentKind, SemanticNormalizationResult
from .temporal import compare_source_times
from .temporal_model import Chronology, TemporalCompilationResult
from .projection_model import (
    EntityProjectionCard,
    ProjectionDiagnostic,
    ProjectionRole,
    PropositionProjection,
    SynthesisProjectionResult,
)


class SynthesisProjector:
    """K09 deterministic, lossless synthesis/navigation projection.

    Cards are rebuildable views over K04-K08 outputs. They never assert current truth.
    `latest_observed_occurrence_ids` is a maximal set under known source chronology;
    incomparable or tied observations are retained together rather than arbitrarily ranked.
    """

    def __init__(self, *, compiler_version: str = "0.1.0"):
        self.compiler_version = compiler_version

    def compile(
        self,
        entity_resolution: EntityResolutionResult,
        normalized: SemanticNormalizationResult,
        relations: RelationCompilationResult,
        temporal: TemporalCompilationResult,
        conflicts: ConflictCompilationResult,
    ) -> SynthesisProjectionResult:
        payload = {
            "entity_resolution": entity_resolution,
            "normalized": normalized,
            "relations": relations,
            "temporal": temporal,
            "conflicts": conflicts,
        }
        input_hash = sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        config_hash = sha256(canonical_json({"projection": "lossless_entity_navigation_v0"}).encode("utf-8")).hexdigest()
        build = BuildIdentity(
            "K09.synthesis_projection",
            self.compiler_version,
            "eor.corpus_synthesis_projection.v0",
            config_hash,
            input_hash,
        )

        diagnostics: list[ProjectionDiagnostic] = []
        groups = {g.group_id: g for g in normalized.groups}
        assertions = {a.normalized_id: a for a in normalized.assertions}
        assertion_group: dict[str, str] = {}
        candidate_statement: dict[str, str] = {}
        for assertion in normalized.assertions:
            candidate_statement[assertion.candidate_id] = assertion.statement
        for group in normalized.groups:
            for assertion_id in group.normalized_assertion_ids:
                if assertion_id in assertion_group and assertion_group[assertion_id] != group.group_id:
                    raise ValueError("normalized assertion belongs to more than one semantic group")
                assertion_group[assertion_id] = group.group_id

        occurrences_by_group: dict[str, list] = defaultdict(list)
        occurrence_by_id = {o.occurrence_id: o for o in temporal.occurrences}
        for occurrence in temporal.occurrences:
            if occurrence.semantic_group_id not in groups:
                diagnostics.append(ProjectionDiagnostic(
                    "occurrence_unknown_group",
                    "temporal occurrence references a semantic group outside K09 inputs",
                    ref_id=occurrence.occurrence_id,
                ))
                continue
            occurrences_by_group[occurrence.semantic_group_id].append(occurrence)

        relation_ids_by_group: dict[str, set[str]] = defaultdict(set)
        for relation in relations.relations:
            for group_id in (relation.key.source_group_id, relation.key.target_group_id):
                if group_id not in groups:
                    diagnostics.append(ProjectionDiagnostic(
                        "relation_unknown_group",
                        "relation references a semantic group outside K09 inputs",
                        ref_id=relation.relation_id,
                    ))
                    continue
                relation_ids_by_group[group_id].add(relation.relation_id)

        conflict_ids_by_group: dict[str, set[str]] = defaultdict(set)
        for conflict in conflicts.conflicts:
            for group_id in (conflict.left_group_id, conflict.right_group_id):
                if group_id not in groups:
                    diagnostics.append(ProjectionDiagnostic(
                        "conflict_unknown_group",
                        "conflict references a semantic group outside K09 inputs",
                        ref_id=conflict.conflict_id,
                    ))
                    continue
                conflict_ids_by_group[group_id].add(conflict.conflict_id)

        supersession_ids_by_group: dict[str, set[str]] = defaultdict(set)
        for supersession in temporal.supersessions:
            endpoint_groups = []
            for assertion_id in (supersession.predecessor_assertion_id, supersession.successor_assertion_id):
                group_id = assertion_group.get(assertion_id)
                if group_id is None:
                    diagnostics.append(ProjectionDiagnostic(
                        "supersession_unknown_assertion",
                        "supersession references a normalized assertion outside K09 inputs",
                        ref_id=supersession.supersession_id,
                    ))
                    continue
                endpoint_groups.append(group_id)
            for group_id in endpoint_groups:
                supersession_ids_by_group[group_id].add(supersession.supersession_id)

        active_entities = {
            e.entity_id: e for e in entity_resolution.registry.entities if e.status == EntityStatus.ACTIVE
        }

        entity_groups: dict[str, set[str]] = defaultdict(set)
        roles: dict[tuple[str, str], set[ProjectionRole]] = defaultdict(set)
        for group in normalized.groups:
            signature = group.signature
            if signature.subject.kind == ArgumentKind.ENTITY and signature.subject.value in active_entities:
                entity_groups[signature.subject.value].add(group.group_id)
                roles[(signature.subject.value, group.group_id)].add(ProjectionRole.SUBJECT)
            if signature.object.kind == ArgumentKind.ENTITY and signature.object.value in active_entities:
                entity_groups[signature.object.value].add(group.group_id)
                roles[(signature.object.value, group.group_id)].add(ProjectionRole.OBJECT)

        hypotheses_by_entity: dict[str, set[str]] = defaultdict(set)
        for hypothesis in entity_resolution.hypotheses:
            if hypothesis.disposition == HypothesisDisposition.BLOCKED:
                continue
            if hypothesis.candidate_entity_id in active_entities:
                hypotheses_by_entity[hypothesis.candidate_entity_id].add(hypothesis.hypothesis_id)

        def latest_maximal(occurrences: Sequence) -> tuple[str, ...]:
            """Return all occurrences not proven strictly before another occurrence."""
            maximal = []
            for candidate in occurrences:
                proven_before = False
                for other in occurrences:
                    if candidate.occurrence_id == other.occurrence_id:
                        continue
                    comparison = compare_source_times(
                        candidate.source_occurrence_times,
                        other.source_occurrence_times,
                    )
                    if comparison == Chronology.BEFORE:
                        proven_before = True
                        break
                if not proven_before:
                    maximal.append(candidate.occurrence_id)
            return tuple(sorted(maximal))

        cards: list[EntityProjectionCard] = []
        for entity_id, entity in sorted(active_entities.items()):
            group_ids = sorted(entity_groups.get(entity_id, set()))
            proposition_views: list[PropositionProjection] = []
            all_occurrences = []
            relation_ids: set[str] = set()
            conflict_ids: set[str] = set()
            supersession_ids: set[str] = set()
            card_diagnostics: list[str] = []

            for group_id in group_ids:
                group = groups[group_id]
                role_set = roles[(entity_id, group_id)]
                role = ProjectionRole.BOTH if len(role_set) == 2 else next(iter(role_set))
                statement = candidate_statement.get(group.representative_candidate_id)
                if statement is None:
                    diagnostics.append(ProjectionDiagnostic(
                        "missing_representative_statement",
                        "semantic group representative candidate has no normalized assertion statement",
                        entity_id,
                        group_id,
                    ))
                    statement = f"[missing representative statement: {group.representative_candidate_id}]"
                    card_diagnostics.append("missing_representative_statement")

                group_occurrences = tuple(sorted(occurrences_by_group.get(group_id, []), key=lambda o: o.occurrence_id))
                all_occurrences.extend(group_occurrences)
                proposition_views.append(PropositionProjection(
                    group.group_id,
                    group.signature.signature_id,
                    role,
                    group.representative_candidate_id,
                    statement,
                    group.signature.epistemic_type,
                    group.signature.memory_class,
                    group.signature.polarity,
                    tuple(sorted(group.normalized_assertion_ids)),
                    tuple(o.occurrence_id for o in group_occurrences),
                ))
                relation_ids.update(relation_ids_by_group.get(group_id, set()))
                conflict_ids.update(conflict_ids_by_group.get(group_id, set()))
                supersession_ids.update(supersession_ids_by_group.get(group_id, set()))

            latest_ids = latest_maximal(all_occurrences)
            if len(latest_ids) > 1:
                card_diagnostics.append("latest_observed_not_unique")
            if not latest_ids and all_occurrences:
                card_diagnostics.append("latest_observed_unresolved")

            aliases = set()
            for alias in entity.aliases:
                aliases.add(alias.normalized)
                aliases.update(alias.display_forms)
            aliases.discard(entity.canonical_name)

            cards.append(EntityProjectionCard(
                entity.entity_id,
                entity.entity_type,
                entity.canonical_name,
                tuple(sorted(aliases, key=str.casefold)),
                tuple(sorted(proposition_views, key=lambda p: p.proposition_projection_id)),
                tuple(sorted(relation_ids)),
                tuple(sorted(conflict_ids)),
                tuple(sorted(supersession_ids)),
                tuple(sorted(hypotheses_by_entity.get(entity_id, set()))),
                latest_ids,
                tuple(sorted(set(card_diagnostics))),
            ))

        return SynthesisProjectionResult(
            build,
            tuple(sorted(cards, key=lambda c: c.entity_id)),
            tuple(sorted(diagnostics, key=lambda d: d.diagnostic_id)),
        )
