"""Split extracted documents into overlapping, section-aware text chunks."""

import re


def chunk_text(text: str, chunk_size: int = 900, overlap: int = 150) -> list[dict]:
    if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("chunk_size must be positive and overlap must be between zero and chunk_size.")
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    result: list[dict] = []
    current = ""
    section = "General"

    def emit(value: str, heading: str):
        value = value.strip()
        if value:
            result.append({"text": value, "section": heading})

    for paragraph in paragraphs:
        heading_match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", paragraph)
        if heading_match:
            emit(current, section)
            current = paragraph
            section = heading_match.group(1).strip()
            continue
        if len(paragraph) > chunk_size:
            if current:
                emit(current, section)
                current = ""
            start = 0
            while start < len(paragraph):
                end = min(start + chunk_size, len(paragraph))
                if end < len(paragraph):
                    boundary = paragraph.rfind(" ", start, end)
                    if boundary > start:
                        end = boundary
                emit(paragraph[start:end], section)
                if end == len(paragraph):
                    break
                start = max(end - overlap, start + 1)
            continue
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) > chunk_size:
            emit(current, section)
            overlap_text = current[-overlap:] if overlap else ""
            current = f"{overlap_text}\n\n{paragraph}".strip() if overlap_text else paragraph
            if len(current) > chunk_size:
                current = paragraph
        else:
            current = candidate
    emit(current, section)
    return result
