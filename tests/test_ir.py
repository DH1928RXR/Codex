from eor_corpus_compiler import *
from eor_corpus_compiler.extractor import ExtractionCompiler


def sample_candidate(chunk_id="c1"):
    ev = EvidenceSpan(source_id="s1", source_type="chat_message", conversation_id="conv1", message_id="m1", chunk_id=chunk_id, speaker="Dan", exact_text="I decided to build the corpus compiler.")
    mention = EntityMention("corpus compiler", "project", ev.evidence_id, "EOR Corpus Compiler", 0.9)
    return CandidateAssertion(statement="Dan decided to build the corpus compiler.", subject="Dan", predicate="decided_to_build", object="EOR Corpus Compiler", epistemic_type=EpistemicType.DECISION, memory_class=MemoryClass.DECISION, evidence=(ev,), temporal=TemporalAnchor("2026-08-22T09:45:00-04:00", None, TemporalPrecision.EXACT, "America/Toronto"), entity_mentions=(mention,), tags=("EOR", "Compiler", "eor"), lineage=ModelLineage("test", "test-model", "extractor", "eor.corpus_extraction_prompt.v0", "0"), extractor_confidence=0.95, source_origin_probability=1.0, importance=0.8, durability=0.8)


def test_candidate_id_stable_and_tags_normalized():
    a = sample_candidate(); b = sample_candidate()
    assert a.candidate_id == b.candidate_id
    assert a.tags == ("compiler", "eor")
    assert a.candidate_id.startswith("cirv0_")


def test_evidence_id_changes_with_exact_text():
    a = EvidenceSpan("s", "chat", "c", "m", "x", "Dan", "alpha")
    b = EvidenceSpan("s", "chat", "c", "m", "x", "Dan", "beta")
    assert a.evidence_id != b.evidence_id


def test_temporal_proxy_requires_reason():
    import pytest
    with pytest.raises(ValueError): TemporalAnchor("2026-08-22", None, TemporalPrecision.DAY, "America/Toronto", is_proxy=True)


def test_compiler_rejects_out_of_input_evidence():
    class Backend:
        provider = "test"; model = "test"
        def extract(self, chunks): return [sample_candidate("other")]
    chunk = CorpusChunk("c1", "s1", "conv1", "title", "Dan", "2026-08-22T09:45:00-04:00", "text")
    import pytest
    with pytest.raises(ValueError): ExtractionCompiler(Backend()).compile([chunk])


def test_compiler_build_identity_is_repeatable():
    class Backend:
        provider = "test"; model = "test"
        def extract(self, chunks): return [sample_candidate("c1")]
    chunk = CorpusChunk("c1", "s1", "conv1", "title", "Dan", "2026-08-22T09:45:00-04:00", "text")
    compiler = ExtractionCompiler(Backend(), config={"mode":"test"})
    one = compiler.compile([chunk]); two = compiler.compile([chunk])
    assert one.build.build_id == two.build.build_id
    assert one.output_hash == two.output_hash


def test_c02_accepts_exact_evidence_and_quarantines_mismatch():
    from eor_corpus_compiler.validator import CandidateValidator
    good_chunk = CorpusChunk("c1", "s1", "conv1", "title", "Dan", "2026-08-22T09:45:00-04:00", "I decided to build the corpus compiler.")
    good = sample_candidate("c1")
    result = CandidateValidator().validate([good_chunk], [good])
    assert len(result.accepted) == 1
    assert len(result.quarantined) == 0
    bad_chunk = CorpusChunk("c1", "s1", "conv1", "title", "Dan", "2026-08-22T09:45:00-04:00", "different text")
    result2 = CandidateValidator().validate([bad_chunk], [good])
    assert len(result2.accepted) == 0
    assert any(d.code == "evidence_text_mismatch" for d in result2.diagnostics)


def test_c03_groups_mentions_without_resolving_entities():
    from eor_corpus_compiler.mentions import EntityMentionCompiler
    a = sample_candidate("c1")
    idx = EntityMentionCompiler().compile([a])
    assert len(idx.buckets) == 1
    assert idx.buckets[0].key.normalized_text == "corpus compiler"
    assert idx.buckets[0].canonical_hints == ("EOR Corpus Compiler",)
