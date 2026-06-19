"""BibTeX parsing and import into paper library."""

import bibtexparser
from bibtexparser.model import Entry

from backend.models.paper import Paper
from backend.utils.logger import logger


def parse_bibtex(content: str) -> tuple[list[Paper], list[dict]]:
    """Parse .bib content, return (successful papers, error list).

    Each error dict has: {"line": int, "error": str}
    """
    try:
        library = bibtexparser.parse_string(content)
    except Exception as e:
        return [], [{"line": 0, "error": f"Failed to parse BibTeX: {e}"}]

    papers = []
    errors = []

    for entry in library.entries:
        try:
            paper = entry_to_paper(entry)
            papers.append(paper)
        except Exception as e:
            line = getattr(entry, 'start_line', 0) if hasattr(entry, 'start_line') else 0
            errors.append({"line": line, "error": str(e)})

    return papers, errors


def _get_field(entry: Entry, key: str, default: str = "") -> str:
    """Extract a field value as a plain string from a bibtexparser entry.

    In bibtexparser v2 beta, ``entry.get()`` returns a ``Field`` object
    (or ``None``), not a raw string.  This helper unwraps it.
    """
    field = entry.get(key)
    if field is None:
        return default
    value = field.value  # type: ignore[union-attr]
    return str(value) if value is not None else default


def entry_to_paper(entry: Entry) -> Paper:
    """Convert a single BibTeX entry to a Paper object."""
    # Author parsing — bibtexparser v2 provides author as a string
    authors_raw = _get_field(entry, "author")
    authors = [a.strip() for a in authors_raw.split(" and ")] if authors_raw else []

    # Year parsing with fallback for non-numeric values
    year_raw = _get_field(entry, "year")
    year = None
    if year_raw:
        try:
            year = int(year_raw)
        except (ValueError, TypeError):
            year = None  # "to appear", "in press" etc.

    # Title — strip braces
    title = _get_field(entry, "title", "Untitled")
    title = title.replace("{", "").replace("}", "")

    # Abstract — often missing in BibTeX
    abstract = _get_field(entry, "abstract")

    # DOI
    doi = _get_field(entry, "doi").strip() or None

    return Paper(
        title=title,
        authors=authors,
        abstract=abstract,
        raw_text=abstract,
        metadata={
            "year": year,
            "doi": doi,
            "entry_type": entry.entry_type if hasattr(entry, 'entry_type') else "misc",
        },
        file_path=None,
        import_source="bib_import",
    )
