from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
from typing import Sequence
import re
import unicodedata

from .build import BuildIdentity, canonical_json
from .entity_model import EntityRegistrySnapshot, EntityStatus
from .ir import CandidateAssertion
from .mentions import EntityMentionCompiler, MentionKey
from .semantic_model import (
    ArgumentKind,
    ArgumentResolutionDecision,
    ArgumentRole,
    NormalizationDiagnostic,
    NormalizedAssertion,
    Polarity,
    PredicateOntology,
    SemanticArgument,
    SemanticGroup,
    SemanticNormalizationResult,
    SemanticSignature,
)


def normalize_semantic_text(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).casefold().strip()
    return " ".join(value.split())


def _predicate_token(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).casefold().strip()
    value = re.sub(r"[^\w]+", "_", value, flags=re.UNICODE)
    return value.strip("_")


_NEGATIVE_PREFIXES = (
    "does_not_",
    "did_not_",
    "do_not_",
    "is_not_",
    "was_not_",
    "were_not_",
    "has_not_",
    "have_not_",
    "had_not_",
    "cannot_",
    "can_not_",
    "not_",
    "never_",
)


class SemanticNormalizer:
    """K05 ontology-preserving normalization and exact semantic deduplication.

    The stage groups equivalent semantic signatures while retaining every source
    occurrence. It never treats repetition as temporal persistence and never uses
    fuzzy/model similarity to merge propositions silently.
    """

    def __init__(
        self,
        *,
        compiler_version: str = "0.1.0",
        predicate_ontology: PredicateOntology | None = None,
    ):
        self.compiler_version = compiler_version
        self.predicate_ontology = predicate_ontology or PredicateOntology()
        alias_map: dict[str, str] = {}
        for rule in self.predicate_ontology.aliases:
            alias = _predicate_token(rule.alias)
            canonical = _predicate_token(rule.canonical)
            if not alias or not canonical:
                raise ValueError("predicate aliases must normalize to non-empty tokens")
            existing = alias_map.get(alias)
            if existing is not None and existing != canonical:
                raise ValueError("predicate ontology contains conflicting alias rules")
            alias_map[alias] = canonical
        self._predicate_aliases = alias_map

    def _normalize_predicate(self, predicate: str) -> tuple[str, Polarity]:
        token = _predicate_token(predicate)
        polarity = Polarity.POSITIVE
        for prefix in _NEGATIVE_PREFIXES:
            if token.startswith(prefix) and len(token) > len(prefix):
                token = token[len(prefix):]
                polarity = Polarity.NEGATIVE
                break
        token = self._predicate_aliases.get(token, token)
        if not token:
            raise ValueError("predicate normalized to empty token")
        return token, polarity

    def compile(
        self,
        candidates: Sequence[CandidateAssertion],
        registry: EntityRegistrySnapshot,
        *,
        argument_decisions: Sequence[ArgumentResolutionDecision] = (),
    ) -> SemanticNormalizationResult:
        input_payload = {
            "candidates": candidates,
            "registry": registry,
            "argument_decisions": argument_decisions,
        }
        input_hash = sha256(canonical_json(input_payload).encode("utf-8")).hexdigest()
        config_hash = sha256(canonical_json(self.predicate_ontology).encode("utf-8")).hexdigest()
        build = BuildIdentity(
            "K05.normalize_semantics",
            self.compiler_version,
            "eor.corpus_semantic_normalization.v0",
            config_hash,
            input_hash,
        )

        active_entities = {e.entity_id: e for e in registry.entities if e.status == EntityStatus.ACTIVE}
        redirects = {r.source_entity_id: r.target_entity_id for r in registry.redirects}

        def active(entity_id: str) -> str:
            seen: set[str] = set()
            current = entity_id
            while current in redirects:
                if current in seen:
                    raise ValueError("entity redirect cycle detected during K05")
                seen.add(current)
                current = redirects[current]
            return current

        bindings = {b.mention_key_id: active(b.entity_id) for b in registry.bindings}
        alias_index: dict[str, set[str]] = defaultdict(set)
        for entity in active_entities.values():
            alias_index[normalize_semantic_text(entity.canonical_name)].add(entity.entity_id)
            for alias in entity.aliases:
                alias_index[normalize_semantic_text(alias.normalized)].add(entity.entity_id)
                for display in alias.display_forms:
                    alias_index[normalize_semantic_text(display)].add(entity.entity_id)

        decisions: dict[tuple[str, ArgumentRole], ArgumentResolutionDecision] = {}
        for decision in sorted(argument_decisions, key=lambda d: d.decision_id):
            key = (decision.candidate_id, decision.role)
            if key in decisions:
                raise ValueError("multiple argument decisions target the same candidate role")
            target = active(decision.entity_id)
            if target not in active_entities:
                raise ValueError("argument decision targets unknown/inactive entity")
            decisions[key] = decision

        diagnostics: list[NormalizationDiagnostic] = []

        def resolve_argument(candidate: CandidateAssertion, role: ArgumentRole, raw: str) -> SemanticArgument:
            explicit = decisions.get((candidate.candidate_id, role))
            if explicit is not None:
                target = active(explicit.entity_id)
                return SemanticArgument(ArgumentKind.ENTITY, target, raw, "explicit_argument_decision")

            wanted = normalize_semantic_text(raw)
            mention_targets: set[str] = set()
            for mention in candidate.entity_mentions:
                mention_text = normalize_semantic_text(mention.mention_text)
                hint = normalize_semantic_text(mention.canonical_hint) if mention.canonical_hint else None
                if wanted not in {mention_text, hint}:
                    continue
                key = MentionKey(EntityMentionCompiler.normalize(mention.mention_text), mention.entity_type_hint)
                target = bindings.get(key.mention_key_id)
                if target in active_entities:
                    mention_targets.add(target)

            if len(mention_targets) == 1:
                return SemanticArgument(ArgumentKind.ENTITY, next(iter(mention_targets)), raw, "candidate_entity_mention")
            if len(mention_targets) > 1:
                diagnostics.append(NormalizationDiagnostic(
                    "ambiguous_candidate_argument",
                    "candidate argument matches mentions bound to multiple entities; preserving literal",
                    candidate.candidate_id,
                    role,
                ))
                return SemanticArgument(ArgumentKind.LITERAL, wanted, raw, "ambiguous_literal")

            direct = {active(eid) for eid in alias_index.get(wanted, set()) if active(eid) in active_entities}
            if len(direct) == 1:
                return SemanticArgument(ArgumentKind.ENTITY, next(iter(direct)), raw, "verified_entity_alias")
            if len(direct) > 1:
                diagnostics.append(NormalizationDiagnostic(
                    "ambiguous_registry_alias",
                    "argument matches multiple active entity aliases; preserving literal",
                    candidate.candidate_id,
                    role,
                ))
                return SemanticArgument(ArgumentKind.LITERAL, wanted, raw, "ambiguous_literal")

            diagnostics.append(NormalizationDiagnostic(
                "unresolved_literal_argument",
                "argument does not resolve to a verified entity and remains a literal",
                candidate.candidate_id,
                role,
            ))
            return SemanticArgument(ArgumentKind.LITERAL, wanted, raw, "literal")

        normalized: list[NormalizedAssertion] = []
        candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
        if len(candidate_by_id) != len(candidates):
            raise ValueError("K05 input contains duplicate candidate identities")

        for candidate in sorted(candidates, key=lambda c: c.candidate_id):
            subject = resolve_argument(candidate, ArgumentRole.SUBJECT, candidate.subject)
            object_arg = resolve_argument(candidate, ArgumentRole.OBJECT, candidate.object)
            predicate, polarity = self._normalize_predicate(candidate.predicate)
            signature = SemanticSignature(
                subject.identity,
                predicate,
                object_arg.identity,
                polarity,
                candidate.epistemic_type,
                candidate.memory_class,
            )
            normalized.append(NormalizedAssertion(
                candidate.candidate_id,
                signature,
                subject,
                object_arg,
                candidate.statement,
                tuple(sorted(e.evidence_id for e in candidate.evidence)),
                candidate.temporal,
                candidate.extractor_confidence,
                candidate.source_origin_probability,
                candidate.importance,
                candidate.durability,
            ))

        grouped: dict[str, list[NormalizedAssertion]] = defaultdict(list)
        for assertion in normalized:
            grouped[assertion.signature.signature_id].append(assertion)

        groups: list[SemanticGroup] = []
        for signature_id in sorted(grouped):
            members = sorted(grouped[signature_id], key=lambda a: a.normalized_id)
            representative = min(
                members,
                key=lambda a: (
                    -a.source_origin_probability,
                    -a.extractor_confidence,
                    -a.importance,
                    -a.durability,
                    a.candidate_id,
                ),
            )
            groups.append(SemanticGroup(
                members[0].signature,
                tuple(a.normalized_id for a in members),
                tuple(sorted(a.candidate_id for a in members)),
                representative.candidate_id,
            ))

        return SemanticNormalizationResult(
            build,
            tuple(sorted(normalized, key=lambda a: a.normalized_id)),
            tuple(sorted(groups, key=lambda g: g.group_id)),
            tuple(sorted(diagnostics, key=lambda d: d.diagnostic_id)),
        )
