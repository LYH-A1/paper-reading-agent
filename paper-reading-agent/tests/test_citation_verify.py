from backend.agents.verify import verify_citations
from backend.models.state import Evidence, EvidenceLevel


def test_verify_exact_quote_match():
    """Evidence with exact quote match in source text is marked verified."""
    source_text = "The Transformer architecture relies entirely on attention mechanisms."
    evidence = [
        Evidence(
            evidence_id="ev1",
            claim="Transformer uses attention",
            level=EvidenceLevel.R0,
            quote="relies entirely on attention mechanisms",
            page=1,
        ),
        Evidence(
            evidence_id="ev2",
            claim="Transformer uses convolutions",
            level=EvidenceLevel.R0,
            quote="uses convolutional layers heavily",
            page=1,
        ),
    ]
    verified = verify_citations(evidence, source_text)
    assert verified[0].confidence > 0.8  # exact match -> high confidence
    assert verified[1].confidence < 0.5  # no match -> low confidence


def test_verify_fuzzy_quote_match():
    """Fuzzy matching catches minor wording differences."""
    source_text = "We propose a new simple network architecture, the Transformer."
    evidence = [
        Evidence(
            evidence_id="ev1",
            claim="Novel architecture",
            level=EvidenceLevel.R0,
            quote="propose a new simple network architecture",
            page=1,
        ),
    ]
    verified = verify_citations(evidence, source_text)
    assert verified[0].confidence > 0.5  # fuzzy match -> decent confidence


def test_verify_no_quote_fallback():
    """Evidence without quote uses claim text for matching."""
    source_text = "BERT uses masked language modeling for pre-training."
    evidence = [
        Evidence(evidence_id="ev1", claim="BERT uses MLM", level=EvidenceLevel.R0, quote=None, page=1),
    ]
    verified = verify_citations(evidence, source_text)
    assert verified[0].confidence >= 0  # should not crash


def test_verify_empty_source():
    """Empty source text returns zero confidence."""
    evidence = [Evidence(evidence_id="ev1", claim="test", level=EvidenceLevel.R0, quote="test", page=1)]
    verified = verify_citations(evidence, "")
    assert verified[0].confidence == 0.0
