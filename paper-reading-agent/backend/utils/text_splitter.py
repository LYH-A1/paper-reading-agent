import re
import uuid
from backend.models.paper import Section

def split_text(text: str, sections: list[Section], chunk_size: int = 1000, overlap: int = 200) -> list[dict]:
    """Split paper text into overlapping chunks, preserving section boundaries."""
    chunks = []

    for section in sections:
        content = section.content.strip()
        if not content:
            continue
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]
        current_chunk = ""

        for para in paragraphs:
            # If a single paragraph exceeds chunk_size, split it by sentence boundaries,
            # then fall back to hard character split for segments still too large.
            if len(para) > chunk_size:
                sentences = re.split(r"(?<=[.!?])\s+", para)
                for sent in sentences:
                    # If a single sentence/segment still exceeds chunk_size, hard-split it
                    if len(sent) > chunk_size:
                        for i in range(0, len(sent), chunk_size - overlap):
                            segment = sent[i:i + chunk_size]
                            chunks.append({
                                "chunk_id": str(uuid.uuid4()),
                                "text": segment.strip(),
                                "page": section.page_start,
                                "section_heading": section.heading
                            })
                        continue

                    if len(current_chunk) + len(sent) > chunk_size and current_chunk:
                        chunks.append({
                            "chunk_id": str(uuid.uuid4()),
                            "text": current_chunk.strip(),
                            "page": section.page_start,
                            "section_heading": section.heading
                        })
                        overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
                        current_chunk = overlap_text + " " + sent
                    else:
                        if current_chunk:
                            current_chunk += " " + sent
                        else:
                            current_chunk = sent
                continue

            if len(current_chunk) + len(para) > chunk_size and current_chunk:
                chunks.append({
                    "chunk_id": str(uuid.uuid4()),
                    "text": current_chunk.strip(),
                    "page": section.page_start,
                    "section_heading": section.heading
                })
                overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
                current_chunk = overlap_text + "\n\n" + para
            else:
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_chunk = para

        if current_chunk.strip():
            chunks.append({
                "chunk_id": str(uuid.uuid4()),
                "text": current_chunk.strip(),
                "page": section.page_start,
                "section_heading": section.heading
            })

    # Fallback: if no sections, split raw text
    if not chunks and text:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        current_chunk = ""
        for para in paragraphs:
            if len(current_chunk) + len(para) > chunk_size and current_chunk:
                chunks.append({"chunk_id": str(uuid.uuid4()), "text": current_chunk.strip(), "page": 1, "section_heading": ""})
                overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
                current_chunk = overlap_text + "\n\n" + para
            else:
                current_chunk = current_chunk + "\n\n" + para if current_chunk else para
        if current_chunk.strip():
            chunks.append({"chunk_id": str(uuid.uuid4()), "text": current_chunk.strip(), "page": 1, "section_heading": ""})

    return chunks
