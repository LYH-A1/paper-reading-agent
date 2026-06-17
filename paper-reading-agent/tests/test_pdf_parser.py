from pathlib import Path
from backend.tools.pdf_parser import PDFParser, PDFParseError

def test_rejects_non_pdf():
    parser = PDFParser()
    try:
        parser.parse("tests/test_models.py")
        assert False, "Should have raised"
    except PDFParseError as e:
        assert "Not a PDF" in str(e)

def test_parses_sample_pdf():
    parser = PDFParser()
    paper = parser.parse("tests/fixtures/sample.pdf")
    assert paper.title == "Sample Paper Title"
    assert len(paper.raw_text) > 50
    assert len(paper.sections) >= 2
    assert paper.parsed_at != ""
