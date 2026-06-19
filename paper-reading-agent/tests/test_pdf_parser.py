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


def test_extract_doi():
    from backend.tools.pdf_parser import PDFParser
    parser = PDFParser()
    refs = parser._extract_references("Some text with DOI: 10.1234/abcdef.123 and another one.")
    dois = [r.doi for r in refs if r.doi]
    assert "10.1234/abcdef.123" in dois


def test_extract_arxiv():
    from backend.tools.pdf_parser import PDFParser
    parser = PDFParser()
    refs = parser._extract_references("See also arXiv: 2310.12345 for more details.")
    urls = [r.url for r in refs if r.url]
    assert any("2310.12345" in u for u in urls)


def test_extract_empty_text():
    from backend.tools.pdf_parser import PDFParser
    parser = PDFParser()
    assert parser._extract_references("") == []


def test_extract_doi_deduplication():
    from backend.tools.pdf_parser import PDFParser
    parser = PDFParser()
    text = "Ref 1 has DOI: 10.1234/test. Ref 2 also has DOI: 10.1234/test."
    refs = parser._extract_references(text)
    doi_refs = [r for r in refs if r.doi]
    assert len(doi_refs) == 1


def test_extract_bracketed_reference():
    from backend.tools.pdf_parser import PDFParser
    parser = PDFParser()
    text = '[1] Kaiming He and Xiangyu Zhang. "Deep Residual Learning". Proceedings of CVPR, 2016.'
    refs = parser._extract_references(text)
    bracketed = [r for r in refs if r.title == "Deep Residual Learning"]
    assert len(bracketed) == 1
    assert bracketed[0].authors == ["Kaiming He", "Xiangyu Zhang"]
    assert bracketed[0].year == 2016
    assert "CVPR" in (bracketed[0].venue or "")
