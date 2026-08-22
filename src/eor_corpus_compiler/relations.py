from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from hashlib import sha256
from typing import Sequence

from .build import BuildIdentity, canonical_json
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
from .semantic_model import Polarity, SemanticGroup, SemanticNormalizationResult


def _fuse_scores(evidence: Sequence[RelationEvidence]) -> float:
    """Fuse positive/negative bounded evidence without allowing one weak vote to dominate."""
    positive_product = 1.0
    negative_product = 1.0
    for item in evidence:
        if item.score >= 0:
            positive_product *= 1.0 - item.score
        else:
            negative_product *= 1.0 - abs(item.score)
    positive = 1.0 - positive_product
    negative = 1.0 - negative_product
    return max(0.0, min(1.0, positive * (1.0 - negative)))


def _polarity_base(group: SemanticGroup) -> tuple:
    signature = group.signature
    return (
        signature.subject,
        signature.predicate,
        signature.object,
        signature.epistemic_type,
        signature.memory_class,
    )


class RelationCompiler:
    """K06 typed relation compiler.

    Only structurally entailed relations are emitted as STRUCTURAL. External/model
    semantic relations remain scored proposals for downstream review/adjudication.
    """

    def __init__(self, *, compiler_version: str = "0.1.0", policy: RelationPolicy | None = None):
        self.compiler_version = compiler_version
        self.policy = policy or RelationPolicy()

    def compile(
        self,
        normalized: SemanticNormalizationResult,
        *,
        proposals: Sequence[RelationProposal] = (),
    ) -> RelationCompilationResult:
        groups = {group.group_id: group for group in normalized.groups}
        if len(groups) != len(normalized.groups):
            raise ValueError("K06 input contains duplicate semantic group identities")

        input_payload = {"normalization": normalized, "proposals": proposals}
        input_hash = sha256(canonical_json(input_payload).encode("utf-8")).hexdigest()
        config_hash = sha256(canonical_json(self.policy).encode("utf-8")).hexdigest()
        build = BuildIdentity(
            "K06.compile_relations",
            self.compiler_version,
            "eor.corpus_relation_compilation.v0",
            config_hash,
            input_hash,
        )

        aggregated: dict[str, dict] = {}

        def add(
            key: RelationKey,
            evidence: Sequence[RelationEvidence],
            proposer: str,
            disposition: RelationDisposition | None = None,
        ) -> None:
            if key.source_group_id not in groups or key.target_group_id not in groups:
                raise ValueError("relation references unknown semantic group")
            slot = aggregated.setdefault(
                key.relation_key_id,
                {"key": key, "evidence": {}, "proposers": set(), "structural": False},
            )
            if slot["key"] != key:
                raise ValueError("relation key hash collision or normalization mismatch")
            for item in evidence:
                slot["evidence"][item.evidence_id] = item
            slot["proposers"].add(proposer)
            if disposition == RelationDisposition.STRUCTURAL:
                slot["structural"] = True

        # Structural opposition: identical normalized proposition except polarity.
        by_base: dict[tuple, dict[Polarity, list[SemanticGroup]]] = defaultdict(lambda: defaultdict(list))
        for group in normalized.groups:
            by_base[_polarity_base(group)][group.signature.polarity].append(group)
        for polarity_map in by_base.values():
            positives = sorted(polarity_map.get(Polarity.POSITIVE, ()), key=lambda g: g.group_id)
            negatives = sorted(polarity_map.get(Polarity.NEGATIVE, ()), key=lambda g: g.group_id)
            for positive in positives:
                for negative in negatives:
                    key = RelationKey(positive.group_id, negative.group_id, RelationType.POLARITY_OPPOSES)
                    evidence = RelationEvidence(
                        "structural_polarity_opposition",
                        f"{positive.signature.signature_id}:{negative.signature.signature_id}",
                        self.policy.structural_polarity_score,
                        "semantic signatures are identical except for polarity",
                        "K06.rule",
                    )
                    add(key, (evidence,), "K06.rule", RelationDisposition.STRUCTURAL)

        for proposal in sorted(proposals, key=lambda p: p.proposal_id):
            add(proposal.key, proposal.evidence, proposal.proposer)

        compiled: list[CompiledRelation] = []
        for relation_key_id in sorted(aggregated):
            slot = aggregated[relation_key_id]
            evidence = tuple(sorted(slot["evidence"].values(), key=lambda e: e.evidence_id))
            score = _fuse_scores(evidence)
            if slot["structural"]:
                disposition = RelationDisposition.STRUCTURAL
            elif score >= self.policy.review_threshold:
                disposition = RelationDisposition.REVIEW_REQUIRED
            else:
                disposition = RelationDisposition.SUGGESTED
            compiled.append(
                CompiledRelation(
                    slot["key"],
                    score,
                    evidence,
                    tuple(sorted(slot["proposers"])),
                    disposition,
                )
            )

        return RelationCompilationResult(build, tuple(sorted(compiled, key=lambda r: r.relation_id)))
