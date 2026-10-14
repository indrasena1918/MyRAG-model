"""Retrieve relevant indexed travel passages for a user question."""

from app.config import settings
from app.rag.embeddings import embed_texts
from app.rag.vector_store import has_chunks, query


def retrieve(question: str, limit: int | None = None) -> list[dict]:
    if not has_chunks():
        return []
    vectors = embed_texts([question])
    matches = query(vectors[0], limit or settings.retrieval_results)
    return [
        item
        for item in matches
        if item["distance"] <= settings.retrieval_distance_threshold
    ]
