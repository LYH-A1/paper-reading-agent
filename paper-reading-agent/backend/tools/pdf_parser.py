import re
import time
from pathlib import Path
from backend.models.paper import Paper, Section, Reference
from backend.utils.logger import logger

class PDFParseError(Exception):
    pass

class PDFParser:
    """Dual-engine PDF parser: PyMuPDF primary, pdfplumber fallback."""

    def parse(self, file_path: str) -> Paper:
        path = Path(file_path)
        if not path.suffix.lower().endswith(".pdf"):
            raise PDFParseError(f"Not a PDF file: {file_path}")

        t0 = time.monotonic()
        paper = Paper(file_path=str(path.resolve()))

        try:
            paper = self._parse_pymupdf(path, paper)
        except Exception as e:
            logger.warning(f"PyMuPDF failed: {e}, falling back to pdfplumber")
            try:
                paper = self._parse_pdfplumber(path, paper)
            except Exception as e2:
                raise PDFParseError(f"Both engines failed. PyMuPDF: {e}, pdfplumber: {e2}")

        elapsed = time.monotonic() - t0
        if elapsed > 60:
            logger.warning(f"PDF parse took {elapsed:.1f}s, exceeded 60s budget")

        if len(paper.raw_text) < 100:
            logger.warning(f"Very short text ({len(paper.raw_text)} chars) — may be scanned PDF")

        paper.parsed_at = time.strftime("%Y-%m-%dT%H:%M:%S")

        # Extract references from raw text
        paper.references = self._extract_references(paper.raw_text)

        return paper

    def _parse_pymupdf(self, path: Path, paper: Paper) -> Paper:
        import fitz  # PyMuPDF — lazy import

        doc = fitz.open(str(path))
        if doc.page_count > 30:
            logger.info(f"Long paper ({doc.page_count} pages), parsing first 30 pages")
            doc = doc[:30]

        full_text_parts = []
        sections = []
        current_section: dict | None = None

        for page_num, page in enumerate(doc):
            text = page.get_text("text")
            full_text_parts.append(text)

            blocks = page.get_text("blocks")
            for block in blocks:
                block_text = block[4].strip() if len(block) > 4 else ""
                bbox = block[:4]
                if self._is_heading(block_text):
                    if current_section:
                        sections.append(Section(**current_section))
                    current_section = {"heading": block_text, "content": "", "page_start": page_num + 1, "page_end": page_num + 1, "bbox": bbox}
                elif current_section:
                    current_section["content"] += block_text + "\n"
                    current_section["page_end"] = page_num + 1

        if current_section:
            sections.append(Section(**current_section))

        raw_text = "\n".join(full_text_parts)
        paper.raw_text = raw_text
        paper.sections = sections
        paper.title, paper.authors, paper.abstract = self._extract_metadata(raw_text)
        return paper

    def _parse_pdfplumber(self, path: Path, paper: Paper) -> Paper:
        import pdfplumber  # lazy import

        full_text_parts = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages[:30]:
                text = page.extract_text()
                if text:
                    full_text_parts.append(text)

        raw_text = "\n".join(full_text_parts)
        paper.raw_text = raw_text
        paper.title, paper.authors, paper.abstract = self._extract_metadata(raw_text)
        return paper

    def _is_heading(self, text: str) -> bool:
        text = text.strip()
        if not text or len(text) > 120:
            return False
        patterns = [
            r"^Abstract$",
            r"^[IVX]+\.\s",
            r"^\d+\.\s+\w",
            r"^\d+\.\d+\.\s+\w",
            r"^(Introduction|Background|Method|Experiment|Result|Discussion|Conclusion|Related Work|References|Acknowledgments)",
        ]
        return any(re.match(p, text, re.IGNORECASE) for p in patterns)

    def _extract_references(self, text: str) -> list[Reference]:
        """Extract references from paper text using regex patterns.

        Looks for:
        1. DOIs (10.XXXX/XXXX)
        2. arXiv IDs (arXiv:XXXX.XXXXX)
        3. Structured citation lines in [N] Author, "Title", Venue, Year format

        Returns list of Reference objects.
        """
        refs: list[Reference] = []
        seen_dois: set[str] = set()

        # Pattern 1: DOI — 10.XXXX/XXXX
        doi_pattern = r'\b(10\.\d{4,}/[^\s\]\)\},;]+)'
        for match in re.finditer(doi_pattern, text):
            doi = match.group(1).rstrip('.,;')
            if doi in seen_dois:
                continue
            seen_dois.add(doi)
            refs.append(Reference(title="", doi=doi))

        # Pattern 2: arXiv ID — arXiv:XXXX.XXXXX or arXiv:XXXX.XXXXXvN
        arxiv_pattern = r'(?:arXiv:\s*)(\d{4}\.\d{4,}(?:v\d+)?)'
        for match in re.finditer(arxiv_pattern, text, re.IGNORECASE):
            arxiv_id = match.group(1)
            refs.append(Reference(
                title="",
                url=f"https://arxiv.org/abs/{arxiv_id}",
            ))

        # Pattern 3: Bracketed references — [1] Author. "Title". Venue, Year.
        bracket_ref = re.finditer(
            r'\[(\d+)\]\s+(.+?)\.\s*"([^"]+)"\.\s*(?:In\s+)?([^,.]+(?:,\s*\d{4})?)',
            text,
        )
        for match in bracket_ref:
            authors_str = match.group(2)
            title = match.group(3)
            venue_year = match.group(4).strip() if match.group(4) else ""
            # Extract year from venue_year if present (e.g. "Proceedings of CVPR, 2016")
            year = None
            venue = venue_year
            year_match = re.search(r',\s*(\d{4})\s*$', venue_year)
            if year_match:
                year = int(year_match.group(1))
                venue = venue_year[:year_match.start()].rstrip(',').strip()
            authors = [a.strip() for a in authors_str.split(" and ")]
            refs.append(Reference(
                title=title,
                authors=authors,
                year=year,
                venue=venue if venue else None,
            ))

        return refs

    def _extract_metadata(self, text: str) -> tuple[str, list[str], str]:
        title = ""
        authors = []
        abstract = ""

        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if lines:
            title = lines[0]
            if len(title) > 200:
                title = title[:200]

        abstract_match = re.search(r"Abstract\s*\n+(.+?)(?=\n\s*(?:\d+\.|[IVX]+\.)\s)", text, re.DOTALL | re.IGNORECASE)
        if abstract_match:
            abstract = abstract_match.group(1).strip()[:2000]

        return title, authors, abstract
