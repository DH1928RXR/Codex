from __future__ import annotations

"""Pure adapter from a captured W18 native worker result into K01 candidates.

This module does not invoke a model, choose a provider, persist data, or write memory.
The bounded model call remains owned by the existing W09/W15/W18 capability chain.
A trusted caller supplies ModelLineage from independently verified execution evidence;
worker-controlled text is never allowed to self-assert lineage.
"""

import json
from dataclasses import dataclass
from typing import Any, Sequence

from .extractor import PROMPT_CONTRACT
from .ir import (
    CandidateAssertion,
    CorpusChunk,
    EntityMention,
    EpistemicType,
    EvidenceSpan,
    MemoryClass,
    ModelLineage,
    TemporalAnchor,
    TemporalPrecision,
)


NATIVE_SUMMARY = "K01_CANDIDATE_BATCH_V1"
_NATIVE_KEYS = {"verdict", "summary", "findings"}
_CANDIDATE_REQUIRED = {
    "statement",
    "subject",
    "predicate",
    "object",
    "epistemic_type",
    "memory_class",
    "evidence",
    "temporal",
    "entity_mentions",
    "tags",
    "extractor_confidence",
    "source_origin_probability",
    "importance",
    "durability",
}
_CANDIDATE_OPTIONAL = {"fidelity", "notes"}
_EVIDENCE_REQUIRED = {"source_id", "source_type", "exact_text"}
_EVIDENCE_OPTIONAL = {
    "conversation_id",
    "message_id",
    "chunk_id",
    "speaker",
    "start_offset",
    "end_offset",
    "source_sha256",
}
_TEMPORAL_REQUIRED = {"precision"}
_TEMPORAL_OPTIONAL = {
    "start",
    "end",
    "timezone",
    "is_proxy",
    "proxy_reason",
    "original_expression",
}
_MENTION_REQUIRED = {"mention_text", "evidence_index"}
_MENTION_OPTIONAL = {"entity_type_hint", "canonical_hint", "confidence"}


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValueError(f"{label} must be an object")
    return value


def _require_keys(
    value: dict[str, Any],
    *,
    required: set[str],
    optional: set[str],
    label: str,
) -> None:
    keys = set(value)
    missing = required - keys
    unknown = keys - required - optional
    if missing:
        raise ValueError(f"{label} missing required keys: {sorted(missing)}")
    if unknown:
        raise ValueError(f"{label} has unknown keys: {sorted(unknown)}")


def _probability(value: Any, label: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{label} must be a number")
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{label} must be between 0 and 1")
    return result


def _optional_str(value: Any, label: str) -> str | None:
    if value is None:
        return None
    if type(value) is not str:
        raise ValueError(f"{label} must be a string or null")
    return value


def _parse_evidence(raw: Any, candidate_index: int) -> tuple[EvidenceSpan, ...]:
    if type(raw) is not list or not raw:
        raise ValueError(f"candidate[{candidate_index}].evidence must be a nonempty array")
    parsed: list[EvidenceSpan] = []
    for evidence_index, item in enumerate(raw):
        obj = _require_object(item, f"candidate[{candidate_index}].evidence[{evidence_index}]")
        _require_keys(
            obj,
            required=_EVIDENCE_REQUIRED,
            optional=_EVIDENCE_OPTIONAL,
            label=f"candidate[{candidate_index}].evidence[{evidence_index}]",
        )
        parsed.append(
            EvidenceSpan(
                source_id=obj["source_id"],
                source_type=obj["source_type"],
                conversation_id=_optional_str(obj.get("conversation_id"), "conversation_id"),
                message_id=_optional_str(obj.get("message_id"), "message_id"),
                chunk_id=_optional_str(obj.get("chunk_id"), "chunk_id"),
                speaker=_optional_str(obj.get("speaker"), "speaker"),
                exact_text=obj["exact_text"],
                start_offset=obj.get("start_offset"),
                end_offset=obj.get("end_offset"),
                source_sha256=_optional_str(obj.get("source_sha256"), "source_sha256"),
            )
        )
    return tuple(parsed)


def _parse_temporal(raw: Any, candidate_index: int) -> TemporalAnchor:
    obj = _require_object(raw, f"candidate[{candidate_index}].temporal")
    _require_keys(
        obj,
        required=_TEMPORAL_REQUIRED,
        optional=_TEMPORAL_OPTIONAL,
        label=f"candidate[{candidate_index}].temporal",
    )
    is_proxy = obj.get("is_proxy", False)
    if type(is_proxy) is not bool:
        raise ValueError("temporal.is_proxy must be boolean")
    return TemporalAnchor(
        start=_optional_str(obj.get("start"), "temporal.start"),
        end=_optional_str(obj.get("end"), "temporal.end"),
        precision=TemporalPrecision(obj["precision"]),
        timezone=_optional_str(obj.get("timezone"), "temporal.timezone"),
        is_proxy=is_proxy,
        proxy_reason=_optional_str(obj.get("proxy_reason"), "temporal.proxy_reason"),
        original_expression=_optional_str(
            obj.get("original_expression"), "temporal.original_expression"
        ),
    )


def _parse_mentions(
    raw: Any,
    evidence: tuple[EvidenceSpan, ...],
    candidate_index: int,
) -> tuple[EntityMention, ...]:
    if type(raw) is not list:
        raise ValueError(f"candidate[{candidate_index}].entity_mentions must be an array")
    parsed: list[EntityMention] = []
    for mention_index, item in enumerate(raw):
        obj = _require_object(item, f"candidate[{candidate_index}].entity_mentions[{mention_index}]")
        _require_keys(
            obj,
            required=_MENTION_REQUIRED,
            optional=_MENTION_OPTIONAL,
            label=f"candidate[{candidate_index}].entity_mentions[{mention_index}]",
        )
        evidence_index = obj["evidence_index"]
        if type(evidence_index) is not int or type(evidence_index) is bool:
            raise ValueError("entity mention evidence_index must be an integer")
        if evidence_index < 0 or evidence_index >= len(evidence):
            raise ValueError("entity mention evidence_index is out of range")
        parsed.append(
            EntityMention(
                mention_text=obj["mention_text"],
                entity_type_hint=_optional_str(obj.get("entity_type_hint"), "entity_type_hint"),
                evidence_id=evidence[evidence_index].evidence_id,
                canonical_hint=_optional_str(obj.get("canonical_hint"), "canonical_hint"),
                confidence=_probability(obj.get("confidence", 0.0), "mention.confidence"),
            )
        )
    return tuple(parsed)


def _parse_candidate(raw: Any, lineage: ModelLineage, candidate_index: int) -> CandidateAssertion:
    obj = _require_object(raw, f"candidate[{candidate_index}]")
    _require_keys(
        obj,
        required=_CANDIDATE_REQUIRED,
        optional=_CANDIDATE_OPTIONAL,
        label=f"candidate[{candidate_index}]",
    )
    evidence = _parse_evidence(obj["evidence"], candidate_index)
    temporal = _parse_temporal(obj["temporal"], candidate_index)
    mentions = _parse_mentions(obj["entity_mentions"], evidence, candidate_index)
    tags = obj["tags"]
    if type(tags) is not list or not all(type(tag) is str for tag in tags):
        raise ValueError(f"candidate[{candidate_index}].tags must be an array of strings")
    notes = obj.get("notes")
    if notes is not None and type(notes) is not str:
        raise ValueError(f"candidate[{candidate_index}].notes must be a string or null")
    fidelity = obj.get("fidelity", "source_bound")
    if type(fidelity) is not str:
        raise ValueError(f"candidate[{candidate_index}].fidelity must be a string")
    return CandidateAssertion(
        statement=obj["statement"],
        subject=obj["subject"],
        predicate=obj["predicate"],
        object=obj["object"],
        epistemic_type=EpistemicType(obj["epistemic_type"]),
        memory_class=MemoryClass(obj["memory_class"]),
        evidence=evidence,
        temporal=temporal,
        entity_mentions=mentions,
        tags=tuple(tags),
        lineage=lineage,
        extractor_confidence=_probability(obj["extractor_confidence"], "extractor_confidence"),
        source_origin_probability=_probability(
            obj["source_origin_probability"], "source_origin_probability"
        ),
        importance=_probability(obj["importance"], "importance"),
        durability=_probability(obj["durability"], "durability"),
        fidelity=fidelity,
        notes=notes,
    )


@dataclass(frozen=True, slots=True)
class W18NativeExtractionBackend:
    """K01-compatible backend over one already-captured, verified W18 native result.

    The outer runtime must independently verify the W18 receipt and construct
    `lineage` from trusted execution evidence. The worker result may contain only
    candidate content in findings; any worker-supplied lineage key is rejected by
    the strict candidate shape.
    """

    worker_result: dict[str, Any]
    lineage: ModelLineage

    def __post_init__(self) -> None:
        if self.lineage.role != "extractor":
            raise ValueError("lineage role must be extractor")
        if self.lineage.prompt_contract != PROMPT_CONTRACT:
            raise ValueError(f"lineage prompt_contract must equal {PROMPT_CONTRACT}")
        if not (self.lineage.invocation_id or "").strip():
            raise ValueError("lineage invocation_id is required")

    @property
    def provider(self) -> str:
        return self.lineage.provider

    @property
    def model(self) -> str:
        return self.lineage.model

    def extract(self, chunks: Sequence[CorpusChunk]) -> Sequence[CandidateAssertion]:
        del chunks  # K01/K02 own source-membership and evidence-exactness validation.
        native = _require_object(self.worker_result, "worker_result")
        if set(native) != _NATIVE_KEYS:
            raise ValueError("worker_result keys must be exactly verdict, summary, findings")
        if native["verdict"] != "approve":
            raise ValueError("worker_result verdict must be approve")
        if native["summary"] != NATIVE_SUMMARY:
            raise ValueError(f"worker_result summary must equal {NATIVE_SUMMARY}")
        findings = native["findings"]
        if type(findings) is not list or not all(type(item) is str for item in findings):
            raise ValueError("worker_result findings must be an array of JSON strings")

        parsed: list[CandidateAssertion] = []
        for index, finding in enumerate(findings):
            try:
                raw = json.loads(finding)
            except json.JSONDecodeError as exc:
                raise ValueError(f"finding[{index}] is not valid JSON") from exc
            parsed.append(_parse_candidate(raw, self.lineage, index))
        return tuple(parsed)
