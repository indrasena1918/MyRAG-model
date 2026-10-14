"""Extract text and page/section metadata from supported travel documents."""

import re
from pathlib import Path

import fitz
from bs4 import BeautifulSoup


SUPPORTED_SUFFIXES = {".pdf", ".txt", ".md", ".markdown"}


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_document(filename: str, content: bytes) -> list[dict]:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"Unsupported file type '{suffix}'. Upload PDF, TXT, or Markdown.")
    if suffix == ".pdf":
        try:
            with fitz.open(stream=content, filetype="pdf") as pdf:
                pages = [
                    {"text": clean_text(page.get_text()), "page": index + 1}
                    for index, page in enumerate(pdf)
                ]
        except (fitz.FileDataError, RuntimeError) as exc:
            raise ValueError(f"Could not read PDF '{filename}': {exc}") from exc
        if not any(page["text"] for page in pages):
            raise ValueError(f"No readable text found in '{filename}'. Scanned PDFs need OCR first.")
        return pages
    decoded = content.decode("utf-8-sig")
    if suffix in {".md", ".markdown"}:
        decoded = BeautifulSoup(decoded, "html.parser").get_text("\n")
    text = clean_text(decoded)
    if not text:
        raise ValueError(f"No readable text found in '{filename}'.")
    return [{"text": text, "page": None}]


def detect_destination(filename: str, text: str) -> str:
    for line in text.splitlines():
        heading = re.match(r"^\s{0,3}#{1,3}\s+(.+?)\s*#*\s*$", line)
        if heading:
            return heading.group(1).strip()
    return Path(filename).stem.replace("_", " ").replace("-", " ").title()
