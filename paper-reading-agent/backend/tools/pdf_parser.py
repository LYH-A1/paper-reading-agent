import re
import time
from pathlib import Path
from backend.models.paper import Paper, Section
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
