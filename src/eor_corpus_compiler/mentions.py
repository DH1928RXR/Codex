from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Sequence

from .build import BuildIdentity, canonical_json, content_id
from .ir import CandidateAssertion, EntityMention


@dataclass(frozen=True, slots=True)
class MentionOccurrence:
    candidate_id: str
    mention: EntityMention

    @property
    def occurrence_id(self) -> str:
        return content_id("moccv0", self)


@dataclass(frozen=True, slots=True)
class MentionKey:
    normalized_text: str
    entity_type_hint: str | None

    @property
    def mention_key_id(self) -> str:
        return content_id("mkeyv0", self)


@dataclass(frozen=True, slots=True)
class MentionBucket:
    key: MentionKey
    occurrences: tuple[MentionOccurrence, ...]
    canonical_hints: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MentionIndex:
    build: BuildIdentity
    buckets: tuple[MentionBucket, ...]

    @property
    def output_hash(self) -> str:
        return sha256(canonical_json(self.buckets).encode("utf-8")).hexdigest()


class EntityMentionCompiler:
    """K03 deterministic mention index. Does not merge identities."""

    def __init__(self, *, compiler_version: str = "0.1.0"):
        self.compiler_version = compiler_version

    @staticmethod
    def normalize(text: str) -> str:
        return " ".join(text.casefold().strip().split())

    def compile(self, candidates: Sequence[CandidateAssertion]) -> MentionIndex:
        input_hash = sha256(canonical_json(candidates).encode("utf-8")).hexdigest()
        config_hash = sha256(canonical_json({"normalizer": "casefold_whitespace_v0"}).encode("utf-8")).hexdigest()
        build = BuildIdentity("K03.mentions", self.compiler_version, "eor.corpus_entity_mentions.v0", config_hash, input_hash)
        grouped = {}; hints = {}
        for candidate in sorted(candidates, key=lambda c: c.candidate_id):
            for mention in candidate.entity_mentions:
                key = (self.normalize(mention.mention_text), mention.entity_type_hint)
                grouped.setdefault(key, []).append(MentionOccurrence(candidate.candidate_id, mention))
                if mention.canonical_hint:
                    hints.setdefault(key, set()).add(mention.canonical_hint.strip())
        buckets = []
        for key_tuple in sorted(grouped, key=lambda x: (x[0], x[1] or "")):
            key = MentionKey(*key_tuple)
            occurrences = tuple(sorted(grouped[key_tuple], key=lambda o: o.occurrence_id))
            canonical_hints = tuple(sorted(hints.get(key_tuple, set()), key=str.casefold))
            buckets.append(MentionBucket(key, occurrences, canonical_hints))
        return MentionIndex(build, tuple(buckets))
