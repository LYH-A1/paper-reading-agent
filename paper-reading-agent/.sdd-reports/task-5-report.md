# Task 5 Report: PDF Parser Tool

## Status: Complete

### Commit
- `a032dcd` — Task 5: Add PDF parser tool with dual-engine (PyMuPDF/pdfplumber)

### Files Created
| File | Purpose |
|------|---------|
| `backend/tools/pdf_parser.py` | Dual-engine PDF parser (PyMuPDF primary, pdfplumber fallback) |
| `tests/fixtures/generate_sample.py` | Script to generate sample PDF for test fixture |
| `tests/fixtures/sample.pdf` | Generated test PDF with title, abstract, and sections |
| `tests/test_pdf_parser.py` | Unit tests for the PDF parser |

### Test Results (2/2 PASS)
```
tests/test_pdf_parser.py::test_rejects_non_pdf PASSED      [ 50%]
tests/test_pdf_parser.py::test_parses_sample_pdf PASSED     [100%]
```

### Key Design Decisions
1. **Dual-engine architecture**: PyMuPDF (`fitz`) is attempted first; on any exception, pdfplumber is used as a fallback. Both are lazy-imported.
2. **Pagination safety**: Papers longer than 30 pages are truncated to the first 30 pages with a log warning.
3. **Heading detection**: Uses regex patterns for common academic section headers (Abstract, Roman numerals, numeric sections, named sections like Introduction/Method/Conclusion).
4. **Metadata extraction**: Title is taken as the first non-empty line; abstract is extracted via regex between an "Abstract" heading and the next section heading.
5. **PDFParseError**: Custom exception used for non-PDF rejection and dual-engine failure.
6. **Performance monitoring**: Logs a warning if parsing exceeds 60 seconds or if the extracted text is very short (<100 chars, indicating a possible scanned PDF).

### Concerns
- **Metadata extraction is heuristic**: The title extraction (first line) and abstract extraction (regex between Abstract and next heading) are basic heuristics. Real academic papers with multi-line titles, author blocks, or unusual layouts may yield incomplete results. This is acceptable for an MVP but should be noted.
- **Generated sample PDF uses basic text insertion**: The `generate_sample.py` script uses `page.insert_text()` which produces a simple PDF without proper font embedding. For more realistic testing, a fixture with actual paper formatting would be useful.
- **`__init__.py` in `tools/` is empty**: The `tools/` directory only has an empty `__init__.py`. It may need to export `PDFParser` for cleaner imports depending on project conventions.
