from __future__ import annotations

from difflib import SequenceMatcher
import unicodedata

from .entity_model import EntityResolutionPolicy, ResolutionEvidence


def normalize_entity_name(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).casefold().strip()
    out: list[str] = []
    for ch in value:
        if ch.isalnum():
            out.append(ch)
        elif ch.isspace() or ch in "-_/:&+":
            out.append(" ")
        elif ch in ".'’`":
            continue
        else:
            out.append(" ")
    return " ".join("".join(out).split())


def trigrams(value: str) -> frozenset[str]:
    compact = f"  {normalize_entity_name(value)}  "
    if not compact.strip():
        return frozenset()
    return frozenset(compact[i : i + 3] for i in range(len(compact) - 2))


def jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def compatible_types(left: str | None, right: str | None) -> bool:
    return left is None or right is None or left.casefold() == right.casefold()


def similarity_evidence(
    mention_key_id: str,
    mention_name: str,
    target_name: str,
    policy: EntityResolutionPolicy,
) -> ResolutionEvidence | None:
    left = normalize_entity_name(mention_name)
    right = normalize_entity_name(target_name)
    if not left or not right:
        return None
    sequence = SequenceMatcher(None, left, right).ratio()
    tri = jaccard(trigrams(left), trigrams(right))
    score = min(1.0, policy.name_similarity_weight * sequence + policy.trigram_weight * tri)
    if score < policy.fuzzy_candidate_threshold:
        return None
    return ResolutionEvidence(
        "name_similarity",
        mention_key_id,
        score,
        f"name similarity against {right!r}: sequence={sequence:.3f}, trigram={tri:.3f}",
        "K04.rule",
    )


def fuse_evidence(evidence: tuple[ResolutionEvidence, ...] | list[ResolutionEvidence]) -> float:
    positive_product = 1.0
    negative_product = 1.0
    for item in evidence:
        if item.score >= 0:
            positive_product *= 1.0 - item.score
        else:
            negative_product *= 1.0 - abs(item.score)
    positive = 1.0 - positive_product
    negative = 1.0 - negative_product
    return positive * (1.0 - negative)
