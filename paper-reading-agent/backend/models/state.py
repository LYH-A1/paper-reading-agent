from dataclasses import dataclass, field
from enum import Enum
from typing import Any

class EvidenceLevel(str, Enum):
    R0 = "R0"
    R1 = "R1"
    R2 = "R2"

@dataclass
class Evidence:
    evidence_id: str
    claim: str
    level: EvidenceLevel
    sentence_index: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    # R0
    page: int | None = None
    quote: str | None = None
    quote_span: tuple[int, int] | None = None
    section_heading: str | None = None
    # R1
    source_title: str | None = None
    source_url: str | None = None
    source_venue: str | None = None
    source_year: int | None = None
    # R2
    reasoning: str | None = None
    based_on_evidence_ids: list[str] = field(default_factory=list)
    # General
    confidence: float = 0.0
    claim_group_id: str | None = None
    external_result_id: str | None = None  # Phase 4b: links to ExternalResult.result_id
    paper_id: str | None = None  # Phase 5: R0 evidence source paper ID (compare reports)

@dataclass
class QualityScore:
    relevance: int = 0      # 0-3
    consistency: int = 0    # 0-4
    completeness: int = 0   # 0-3

    @property
    def total(self) -> int:
        return self.relevance + self.consistency + self.completeness

@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    page: int
    section_heading: str = ""
    source: str = ""          # "bm25" | "dense" | "rerank"
    scores: dict[str, float] = field(default_factory=dict)

@dataclass
class AgentState:
    paper: Any | None = None
    report: dict | None = None
    retriever: Any | None = None

    user_query: str = ""
    intent: str = ""

    plan: dict | None = None
    plan_feedback: str | None = None
    observation: dict | None = None

    retrieved_chunks: list[RetrievedChunk] = field(default_factory=list)
    answer: str = ""
    evidence_list: list[Evidence] = field(default_factory=list)

    quality_score: QualityScore | None = None
    rewrite_count: int = 0

    trace: list[str] = field(default_factory=list)
    error: str | None = None
    reasoning_log: list[dict] = field(default_factory=list)

    session_id: str = ""
    followup_questions: list[str] = field(default_factory=list)

    # Phase 4b: external search
    external_retriever: Any | None = None
    external_results: list = field(default_factory=list)
    external_search_error: str | None = None


@dataclass
class CompareState:
    paper_ids: list[str] = field(default_factory=list)
    papers: list = field(default_factory=list)           # list[Paper]
    reports: list[dict] = field(default_factory=list)
    comparison_aspects: list[str] | None = None
    user_query: str = ""
    answer: str = ""
    evidence_list: list[Evidence] = field(default_factory=list)
    quality_score: QualityScore | None = None
    rewrite_count: int = 0
    trace: list[str] = field(default_factory=list)
    error: str | None = None
    session_id: str = ""
