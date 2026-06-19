import json
from dataclasses import asdict
from backend.models.paper import Paper, Section, Figure, Reference
from backend.models.state import Evidence, EvidenceLevel, QualityScore, AgentState, RetrievedChunk


def test_paper_defaults():
    p = Paper()
    assert p.paper_id
    assert p.language == "en"
    assert p.sections == []
    assert p.figures == []


def test_paper_with_sections():
    s = Section(heading="3. Method", content="We propose...", page_start=3, page_end=8)
    p = Paper(title="Test", sections=[s], raw_text="full text")
    assert len(p.sections) == 1
    assert p.sections[0].heading == "3. Method"


def test_paper_serializable():
    p = Paper(title="Test", authors=["Alice", "Bob"])
    d = asdict(p)
    assert json.dumps(d)
    assert d["title"] == "Test"
    assert d["authors"] == ["Alice", "Bob"]


def test_evidence_r0_creation():
    e = Evidence(
        evidence_id="ev-1",
        claim="The model was trained on 8xA100 for 72 hours",
        level=EvidenceLevel.R0,
        sentence_index=0,
        char_start=0,
        char_end=52,
        page=4,
        quote="We train our model on 8 NVIDIA A100 GPUs for 72 hours",
        section_heading="4. Experimental Setup",
        confidence=0.95
    )
    assert e.level == EvidenceLevel.R0
    assert e.page == 4
    assert e.quote is not None


def test_evidence_r2_with_chain():
    e = Evidence(
        evidence_id="ev-5",
        claim="This direction is likely to converge with diffusion priors",
        level=EvidenceLevel.R2,
        sentence_index=2,
        reasoning="Based on ev-3 showing transformer scaling + ev-4 showing diffusion results",
        based_on_evidence_ids=["ev-3", "ev-4"],
        confidence=0.6
    )
    assert e.level == EvidenceLevel.R2
    assert len(e.based_on_evidence_ids) == 2


def test_quality_score_total():
    q = QualityScore(relevance=3, consistency=4, completeness=2)
    assert q.total == 9


def test_agent_state_defaults():
    s = AgentState()
    assert s.retrieved_chunks == []
    assert s.evidence_list == []
    assert s.trace == []
    assert s.rewrite_count == 0


def test_evidence_external_result_id():
    from backend.models.state import Evidence, EvidenceLevel
    e = Evidence(evidence_id="e1", claim="test", level=EvidenceLevel.R1)
    assert e.external_result_id is None
    e2 = Evidence(evidence_id="e2", claim="test", level=EvidenceLevel.R1, external_result_id="ext-123")
    assert e2.external_result_id == "ext-123"


def test_agent_state_external_fields():
    from backend.models.state import AgentState
    state = AgentState()
    assert state.external_retriever is None
    assert state.external_results == []
    assert state.external_search_error is None


def test_paper_default_import_source():
    from backend.models.paper import Paper
    p = Paper(title="test")
    assert p.import_source == "upload"


def test_paper_file_path_none():
    from backend.models.paper import Paper
    p = Paper(title="test", file_path=None)
    assert p.file_path is None


def test_paper_arxiv_id_optional():
    from backend.models.paper import Paper
    p = Paper(title="test")
    assert p.arxiv_id is None


def test_paper_arxiv_pdf_url_optional():
    from backend.models.paper import Paper
    p = Paper(title="test", arxiv_id="2401.12345", arxiv_pdf_url="https://arxiv.org/pdf/2401.12345.pdf")
    assert p.arxiv_id == "2401.12345"
    assert p.arxiv_pdf_url == "https://arxiv.org/pdf/2401.12345.pdf"


def test_paper_import_source_bib():
    from backend.models.paper import Paper
    p = Paper(title="test", import_source="bib_import")
    assert p.import_source == "bib_import"


def test_paper_import_source_external_save():
    from backend.models.paper import Paper
    p = Paper(title="test", import_source="external_save")
    assert p.import_source == "external_save"
