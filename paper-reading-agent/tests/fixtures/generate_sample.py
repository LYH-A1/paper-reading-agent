"""Run once to create sample.pdf for tests."""
import fitz
doc = fitz.open()
page = doc.new_page()
page.insert_text(fitz.Point(72, 72), "Sample Paper Title", fontsize=16)
page.insert_text(fitz.Point(72, 120), "Abstract\nThis paper proposes a novel method for testing PDF parsers.", fontsize=11)
page.insert_text(fitz.Point(72, 200), "1. Introduction\nThis is the introduction section.", fontsize=11)
page.insert_text(fitz.Point(72, 300), "2. Method\nWe describe our approach here.", fontsize=11)
doc.save("tests/fixtures/sample.pdf")
print("Created tests/fixtures/sample.pdf")
