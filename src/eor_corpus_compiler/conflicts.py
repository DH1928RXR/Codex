from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, datetime
from hashlib import sha256

from .build import BuildIdentity, canonical_json
from .conflict_model import (
    ConflictCase,
    ConflictCompilationResult,
    ConflictDiagnostic,
    ConflictDisposition,
    ConflictKind,
    ConflictPolicy,
    EffectiveRelation,
)
from .ir import TemporalAnchor, TemporalPrecision
from .relation_model import RelationCompilationResult, RelationType
from .temporal_model import SupersessionDisposition, TemporalCompilationResult


def _bound_date(value: str, *, upper: bool) -> date | None:
    try:
        if len(value) == 4:
            year = int(value)
            return date(year, 12 if upper else 1, 31 if upper else 1)
        if len(value) == 7:
            year, month = map(int, value.split("-"))
            day = calendar.monthrange(year, month)[1] if upper else 1
            return date(year, month, day)
        if len(value) == 10:
            return date.fromisoformat(value)
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        return None


def effective_interval(anchor: TemporalAnchor) -> tuple[int, int] | None:
    """Conservative day-level effective interval; proxy/relative/unknown stays unknown."""
    if anchor.is_proxy or anchor.precision in {TemporalPrecision.RELATIVE, TemporalPrecision.UNKNOWN}:
        return None
    if anchor.start is None:
        return None
    start = _bound_date(anchor.start, upper=False)
    if start is None:
        return None
    if anchor.end is not None:
        end = _bound_date(anchor.end, upper=True)
    elif anchor.precision == TemporalPrecision.YEAR:
        end = _bound_date(anchor.start[:4], upper=True)
    elif anchor.precision == TemporalPrecision.MONTH:
        end = _bound_date(anchor.start[:7], upper=True)
    else:
        end = _bound_date(anchor.start, upper=True)
    if end is None or end < start:
        return None
    return start.toordinal(), end.toordinal()


def compare_effective_anchors(left: tuple[TemporalAnchor, ...], right: tuple[TemporalAnchor, ...]) -> EffectiveRelation:
    if not left or not right:
        return EffectiveRelation.UNKNOWN
    unknown = False
    for left_anchor in left:
        left_interval = effective_interval(left_anchor)
        for right_anchor in right:
            right_interval = effective_interval(right_anchor)
            if left_interval is None or right_interval is None:
                unknown = True
                continue
            if left_interval[0] <= right_interval[1] and right_interval[0] <= left_interval[1]:
                return EffectiveRelation.OVERLAP
    return EffectiveRelation.UNKNOWN if unknown else EffectiveRelation.DISJOINT


class ConflictCompiler:
    """K08 conflict classifier over K06 relations and K07 temporal state.

    A structural polarity opposition is evidence of incompatibility, not by itself
    proof of a simultaneous contradiction. K08 checks effective-time overlap and
    preserves possible change-over-time explanations for adjudication.
    """

    def __init__(self, *, compiler_version: str = "0.1.0", policy: ConflictPolicy | None = None):
        self.compiler_version = compiler_version
        self.policy = policy or ConflictPolicy()

    def compile(
        self,
        relations: RelationCompilationResult,
        temporal: TemporalCompilationResult,
    ) -> ConflictCompilationResult:
        input_hash = sha256(canonical_json({"relations": relations, "temporal": temporal}).encode("utf-8")).hexdigest()
        config_hash = sha256(canonical_json(self.policy).encode("utf-8")).hexdigest()
        build = BuildIdentity(
            "K08.compile_conflicts",
            self.compiler_version,
            "eor.corpus_conflict_compilation.v0",
            config_hash,
            input_hash,
        )

        anchors_by_group: dict[str, list[TemporalAnchor]] = defaultdict(list)
        assertion_group: dict[str, str] = {}
        for occurrence in temporal.occurrences:
            anchors_by_group[occurrence.semantic_group_id].append(occurrence.effective_anchor)
            assertion_group[occurrence.normalized_assertion_id] = occurrence.semantic_group_id

        supersession_ids_by_pair: dict[tuple[str, str], set[str]] = defaultdict(set)
        diagnostics: list[ConflictDiagnostic] = []
        for supersession in temporal.supersessions:
            if supersession.disposition != SupersessionDisposition.REVIEW_REQUIRED:
                continue
            left = assertion_group.get(supersession.predecessor_assertion_id)
            right = assertion_group.get(supersession.successor_assertion_id)
            if left is None or right is None:
                diagnostics.append(ConflictDiagnostic(
                    "supersession_missing_group",
                    "reviewable supersession references assertion without temporal group mapping",
                ))
                continue
            if left == right:
                continue
            pair = tuple(sorted((left, right)))
            supersession_ids_by_pair[pair].add(supersession.supersession_id)

        signals: dict[tuple[str, str], list] = defaultdict(list)
        for relation in relations.relations:
            if relation.key.relation_type not in {RelationType.POLARITY_OPPOSES, RelationType.CONTRADICTS}:
                continue
            pair = tuple(sorted((relation.key.source_group_id, relation.key.target_group_id)))
            signals[pair].append(relation)

        conflicts: list[ConflictCase] = []
        for pair, source_relations in sorted(signals.items()):
            left, right = pair
            left_anchors = tuple(anchors_by_group.get(left, ()))
            right_anchors = tuple(anchors_by_group.get(right, ()))
            effective_relation = compare_effective_anchors(left_anchors, right_anchors)
            if not left_anchors or not right_anchors:
                diagnostics.append(ConflictDiagnostic(
                    "missing_temporal_occurrence",
                    "conflict signal lacks temporal occurrences for one or both semantic groups",
                    left,
                    right,
                ))

            kind = (
                ConflictKind.POLARITY_OPPOSITION
                if any(r.key.relation_type == RelationType.POLARITY_OPPOSES for r in source_relations)
                else ConflictKind.SEMANTIC_CONTRADICTION
            )
            score = max(r.score for r in source_relations)
            source_relation_ids = tuple(sorted(r.relation_id for r in source_relations))
            source_supersession_ids = tuple(sorted(supersession_ids_by_pair.get(pair, set())))

            if source_supersession_ids:
                disposition = ConflictDisposition.CHANGE_OVER_TIME_CANDIDATE
            elif effective_relation == EffectiveRelation.DISJOINT:
                disposition = ConflictDisposition.TEMPORALLY_DISJOINT
            elif effective_relation == EffectiveRelation.UNKNOWN:
                disposition = ConflictDisposition.UNKNOWN_TEMPORAL
            elif score >= self.policy.review_threshold:
                disposition = ConflictDisposition.REVIEW_REQUIRED
            else:
                disposition = ConflictDisposition.SUGGESTED

            conflicts.append(ConflictCase(
                left,
                right,
                kind,
                effective_relation,
                score,
                source_relation_ids,
                source_supersession_ids,
                disposition,
            ))

        return ConflictCompilationResult(
            build,
            tuple(sorted(conflicts, key=lambda c: c.conflict_id)),
            tuple(sorted(diagnostics, key=lambda d: d.diagnostic_id)),
        )
