from backend.models.paper import Section
from backend.utils.text_splitter import split_text

def test_split_preserves_sections():
    sections = [
        Section(heading="1. Intro", content="This is the introduction.\n\nIt has two paragraphs.", page_start=1, page_end=1),
        Section(heading="2. Method", content="We propose a method.", page_start=2, page_end=2),
    ]
    chunks = split_text("", sections, chunk_size=1000, overlap=200)
    assert len(chunks) == 2
    assert chunks[0]["section_heading"] == "1. Intro"
    assert chunks[1]["section_heading"] == "2. Method"

def test_split_respects_chunk_size():
    sections = [Section(heading="1. Intro", content="A" * 1500, page_start=1, page_end=1)]
    chunks = split_text("", sections, chunk_size=1000, overlap=200)
    assert len(chunks) >= 2

def test_empty_sections():
    assert split_text("", [], chunk_size=1000) == []

def test_fallback_no_sections():
    chunks = split_text("First paragraph.\n\nSecond paragraph.", [])
    assert len(chunks) == 1
    assert "First paragraph" in chunks[0]["text"]
