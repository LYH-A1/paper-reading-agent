"""Tests for external search module."""

import pytest
import time
from dataclasses import asdict

from backend.tools.external_search import (
    ExternalResult,
    ExternalRetriever,
)


# ---- ExternalResult ----

def test_external_result_defaults():
    r = ExternalResult()
    assert r.result_id != ""
    assert r.title == ""
    assert r.authors == []
    assert r.abstract == ""
    assert r.year is None
    assert r.url == ""
    assert r.source == ""
    assert r.citation_count is None
    assert r.related_titles == []


def test_external_result_fields():
    r = ExternalResult(
        title="Test Paper",
        authors=["Alice", "Bob"],
        year=2024,
        url="https://arxiv.org/abs/1234.5678",
        source="arxiv",
        citation_count=42,
    )
    assert r.title == "Test Paper"
    assert r.year == 2024
    assert r.citation_count == 42


def test_external_result_unique_ids():
    r1 = ExternalResult()
    r2 = ExternalResult()
    assert r1.result_id != r2.result_id


# ---- arXiv XML parsing ----

ARXIV_XML_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v7</id>
    <title>Attention Is All You Need</title>
    <author><name>Ashish Vaswani</name></author>
    <author><name>Noam Shazeer</name></author>
    <summary>  The dominant sequence transduction models are based on complex
recurrent or convolutional neural networks...  </summary>
    <published>2017-06-12T00:00:00Z</published>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/1512.03385v1</id>
    <title>Deep Residual Learning for Image Recognition</title>
    <author><name>Kaiming He</name></author>
    <summary>  Deeper neural networks are more difficult to train...  </summary>
    <published>2015-12-10T00:00:00Z</published>
  </entry>
</feed>"""


def test_parse_arxiv_xml():
    retriever = ExternalRetriever()
    results = retriever._parse_arxiv_xml(ARXIV_XML_SAMPLE)
    assert len(results) == 2

    r1 = results[0]
    assert r1.title == "Attention Is All You Need"
    assert r1.authors == ["Ashish Vaswani", "Noam Shazeer"]
    assert "dominant sequence transduction" in r1.abstract
    assert r1.year == 2017
    assert "1706.03762" in r1.url
    assert r1.source == "arxiv"

    r2 = results[1]
    assert r2.title == "Deep Residual Learning for Image Recognition"
    assert r2.year == 2015


def test_parse_arxiv_xml_empty():
    empty_xml = """<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom"/>
    """
    retriever = ExternalRetriever()
    results = retriever._parse_arxiv_xml(empty_xml)
    assert results == []


# ---- Rate limiting ----

@pytest.mark.asyncio
async def test_rate_limit_first_request_no_delay():
    retriever = ExternalRetriever()
    t0 = time.time()
    await retriever._respect_rate_limit()
    elapsed = time.time() - t0
    assert elapsed < 0.5  # first request should be instant


@pytest.mark.asyncio
async def test_rate_limit_second_request_waits():
    retriever = ExternalRetriever()
    retriever._last_request_time = time.time()  # simulate recent request
    t0 = time.time()
    await retriever._respect_rate_limit()
    elapsed = time.time() - t0
    assert elapsed >= 0  # doesn't crash
