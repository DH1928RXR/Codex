import copy
import json

import pytest

from eor_corpus_compiler.extractor import ExtractionCompiler
from eor_corpus_compiler.ir import CorpusChunk, ModelLineage
from eor_corpus_compiler.validator import CandidateValidator
from eor_corpus_compiler.w18_native_backend import NATIVE_SUMMARY, W18NativeExtractionBackend


def chunk(*, text="I decided to build the corpus compiler.", chunk_id="c1"):
    return CorpusChunk(
        chunk_id=chunk_id,
        source_id="s1",
        conversation_id="conv1",
        title="Private calibration conversation",
        speaker="Dan",
        occurred_at="2026-08-22T09:45:00-04:00",
        text=text,
    )


def lineage():
    return ModelLineage(
        provider="eor-trusted-runtime",
        model="bounded-worker",
        role="extractor",
        prompt_contract="eor.corpus_extraction_prompt.v0",
        prompt_version="0",
        invocation_id="w18-invocation-001",
    )


def candidate_payload(*, chunk_id="c1", exact_text="I decided to build the corpus compiler."):
    return {
        "statement": "Dan decided to build the corpus compiler.",
        "subject": "Dan",
        "predicate": "decided_to_build",
        "object": "EOR Corpus Compiler",
        "epistemic_type": "decision",
        "memory_class": "decision",
        "evidence": [
            {
                "source_id": "s1",
                "source_type": "chat_message",
                "conversation_id": "conv1",
                "message_id": "m1",
                "chunk_id": chunk_id,
                "speaker": "Dan",
                "exact_text": exact_text,
            }
        ],
        "temporal": {
            "start": "2026-08-22T09:45:00-04:00",
            "end": None,
            "precision": "exact",
            "timezone": "America/Toronto",
            "is_proxy": False,
            "proxy_reason": None,
            "original_expression": None,
        },
        "entity_mentions": [
            {
                "mention_text": "corpus compiler",
                "entity_type_hint": "project",
                "evidence_index": 0,
                "canonical_hint": "EOR Corpus Compiler",
                "confidence": 0.9,
            }
        ],
        "tags": ["EOR", "Compiler", "eor"],
        "extractor_confidence": 0.95,
        "source_origin_probability": 1.0,
        "importance": 0.8,
        "durability": 0.8,
    }


def native(*payloads):
    return {
        "verdict": "approve",
        "summary": NATIVE_SUMMARY,
        "findings": [json.dumps(payload, sort_keys=True, separators=(",", ":")) for payload in payloads],
    }


def compile_one(payload=None, source_chunk=None):
    payload = candidate_payload() if payload is None else payload
    source_chunk = chunk() if source_chunk is None else source_chunk
    backend = W18NativeExtractionBackend(native(payload), lineage())
    return ExtractionCompiler(backend, config={"mode": "w18-native-v1"}).compile([source_chunk])


def test_valid_native_result_compiles_and_injects_trusted_lineage():
    result = compile_one()
    assert len(result.candidates) == 1
    item = result.candidates[0]
    assert item.lineage == lineage()
    assert item.tags == ("compiler", "eor")
    assert item.entity_mentions[0].evidence_id == item.evidence[0].evidence_id


def test_valid_candidate_passes_existing_k02_exact_evidence_validation():
    result = compile_one()
    validation = CandidateValidator().validate([chunk()], result.candidates)
    assert len(validation.accepted) == 1
    assert len(validation.quarantined) == 0


def test_evidence_text_mismatch_is_left_for_existing_k02_to_quarantine():
    payload = candidate_payload(exact_text="different text")
    result = compile_one(payload)
    validation = CandidateValidator().validate([chunk()], result.candidates)
    assert len(validation.accepted) == 0
    assert any(d.code == "evidence_text_mismatch" for d in validation.diagnostics)


def test_out_of_input_chunk_is_rejected_by_existing_k01_compiler():
    payload = candidate_payload(chunk_id="outside")
    with pytest.raises(ValueError, match="outside compiler input"):
        compile_one(payload)


def test_worker_cannot_self_assert_lineage():
    payload = candidate_payload()
    payload["lineage"] = {"provider": "worker-controlled"}
    with pytest.raises(ValueError, match="unknown keys"):
        compile_one(payload)


def test_native_schema_drift_rejects_before_candidate_parse():
    result = native(candidate_payload())
    result["extra"] = True
    backend = W18NativeExtractionBackend(result, lineage())
    with pytest.raises(ValueError, match="keys must be exactly"):
        ExtractionCompiler(backend).compile([chunk()])


def test_native_verdict_and_summary_are_fixed():
    bad_verdict = native(candidate_payload())
    bad_verdict["verdict"] = "reject"
    with pytest.raises(ValueError, match="verdict must be approve"):
        ExtractionCompiler(W18NativeExtractionBackend(bad_verdict, lineage())).compile([chunk()])

    bad_summary = native(candidate_payload())
    bad_summary["summary"] = "near-match"
    with pytest.raises(ValueError, match="summary must equal"):
        ExtractionCompiler(W18NativeExtractionBackend(bad_summary, lineage())).compile([chunk()])


def test_invalid_json_finding_fails_closed():
    result = {"verdict": "approve", "summary": NATIVE_SUMMARY, "findings": ["{not-json"]}
    with pytest.raises(ValueError, match="not valid JSON"):
        ExtractionCompiler(W18NativeExtractionBackend(result, lineage())).compile([chunk()])


def test_bool_is_not_accepted_as_probability():
    payload = candidate_payload()
    payload["extractor_confidence"] = True
    with pytest.raises(ValueError, match="must be a number"):
        compile_one(payload)


def test_entity_mention_evidence_index_must_resolve():
    payload = candidate_payload()
    payload["entity_mentions"][0]["evidence_index"] = 3
    with pytest.raises(ValueError, match="out of range"):
        compile_one(payload)


def test_empty_candidate_batch_is_valid_and_deterministic():
    backend = W18NativeExtractionBackend(native(), lineage())
    compiler = ExtractionCompiler(backend, config={"mode": "w18-native-v1"})
    first = compiler.compile([chunk()])
    second = compiler.compile([chunk()])
    assert first.candidates == ()
    assert first.output_hash == second.output_hash
    assert first.build.build_id == second.build.build_id


def test_backend_provider_and_model_come_from_trusted_lineage():
    backend = W18NativeExtractionBackend(native(), lineage())
    assert backend.provider == "eor-trusted-runtime"
    assert backend.model == "bounded-worker"
