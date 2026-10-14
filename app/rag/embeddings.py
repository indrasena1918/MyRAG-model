"""Embedding access kept separate from the selected chat model."""

from app.services.ollama_service import embed


def embed_texts(texts: list[str]) -> list[list[float]]:
    return embed(texts)
