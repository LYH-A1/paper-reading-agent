from dataclasses import dataclass, field
import uuid

@dataclass
class Section:
    heading: str
    content: str
    page_start: int
    page_end: int
    bbox: tuple[float, float, float, float] | None = None

@dataclass
class Figure:
    caption: str
    page: int
    bbox: tuple[float, float, float, float]
    image_base64: str | None = None

@dataclass
class Reference:
    """Structured bibliographic reference."""
    title: str
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    url: str | None = None

@dataclass
class Paper:
    paper_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    sections: list[Section] = field(default_factory=list)
    figures: list[Figure] = field(default_factory=list)
    references: list[Reference] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    raw_text: str = ""
    language: str = "en"
    file_path: str = ""
    parsed_at: str = ""
