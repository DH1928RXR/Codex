from eor_corpus_compiler.ir import (
    CandidateAssertion,
    CorpusChunk,
    EpistemicType,
    EvidenceSpan,
    MemoryClass,
    ModelLineage,
    TemporalAnchor,
    TemporalPrecision,
)
from eor_corpus_compiler.validator import CandidateValidator


def chunk(*, speaker="ASSISTANT"):
    return CorpusChunk(
        chunk_id="c1",
        source_id="s1",
        conversation_id="conv1",
        title="Speaker provenance regression",
        speaker=speaker,
        occurred_at="2026-08-22T09:45:00-04:00",
        text="I recommend keeping the current architecture.",
    )


def candidate(*, evidence_speaker):
    evidence = EvidenceSpan(
        source_id="s1",
        source_type="chat_message",
        conversation_id="conv1",
        message_id="m1",
        chunk_id="c1",
        speaker=evidence_speaker,
        exact_text="I recommend keeping the current architecture.",
    )
    return CandidateAssertion(
        statement="The assistant recommended keeping the current architecture.",
        subject="assistant",
        predicate="recommended",
        object="keep current architecture",
        epistemic_type=EpistemicType.ASSISTANT_PROPOSAL,
        memory_class=MemoryClass.PROJECT,
        evidence=(evidence,),
        temporal=TemporalAnchor(None, None, TemporalPrecision.UNKNOWN, "America/Toronto"),
        entity_mentions=(),
        tags=("architecture",),
        lineage=ModelLineage("test", "test-model", "extractor", "contract", "1"),
        extractor_confidence=0.9,
        source_origin_probability=1.0,
        importance=0.5,
        durability=0.5,
    )


def test_matching_speaker_is_accepted():
    result = CandidateValidator().validate([chunk()], [candidate(evidence_speaker="ASSISTANT")])
    assert len(result.accepted) == 1
    assert not any(d.code == "speaker_mismatch" for d in result.diagnostics)


def test_wrong_speaker_is_quarantined_even_when_text_source_and_conversation_match():
    result = CandidateValidator().validate([chunk()], [candidate(evidence_speaker="Dan")])
    assert len(result.accepted) == 0
    assert len(result.quarantined) == 1
    assert any(d.code == "speaker_mismatch" for d in result.diagnostics)


def test_unspecified_speaker_preserves_existing_optional_semantics():
    result = CandidateValidator().validate([chunk()], [candidate(evidence_speaker=None)])
    assert len(result.accepted) == 1
    assert not any(d.code == "speaker_mismatch" for d in result.diagnostics)
