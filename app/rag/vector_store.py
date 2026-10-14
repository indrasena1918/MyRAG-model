"""Persistent ChromaDB collection for indexed travel document chunks."""

import shutil

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import settings

COLLECTION_NAME = "travel_documents"
_client = None
_collection = None


def _reset_chroma_store() -> None:
    global _client, _collection
    _client = None
    _collection = None
    if settings.chroma_path.exists():
        shutil.rmtree(settings.chroma_path, ignore_errors=True)
    settings.chroma_path.mkdir(parents=True, exist_ok=True)


def get_collection():
    global _client, _collection
    if _collection is not None:
        return _collection

    try:
        settings.chroma_path.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=str(settings.chroma_path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        _collection = _client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        return _collection
    except Exception as exc:
        message = str(exc).lower()
        if "nothing found on disk" in message or "not found on disk" in message:
            _reset_chroma_store()
            _client = chromadb.PersistentClient(
                path=str(settings.chroma_path),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            _collection = _client.get_or_create_collection(
                name=COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
            return _collection
        raise


def add_chunks(chunks: list[dict], embeddings: list[list[float]]) -> None:
    if len(chunks) != len(embeddings):
        raise ValueError("Each chunk must have exactly one embedding.")
    if not chunks:
        return
    collection = get_collection()
    collection.upsert(
        ids=[item["id"] for item in chunks],
        documents=[item["text"] for item in chunks],
        metadatas=[item["metadata"] for item in chunks],
        embeddings=embeddings,
    )


def query(embedding: list[float], limit: int = 5) -> list[dict]:
    collection = get_collection()
    if collection.count() == 0:
        return []
    result = collection.query(
        query_embeddings=[embedding],
        n_results=min(limit, collection.count()),
        include=["documents", "metadatas", "distances"],
    )
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    return [
        {"text": document, "metadata": metadata, "distance": distance}
        for document, metadata, distance in zip(documents, metadatas, distances)
    ]


def status() -> dict:
    count = get_collection().count()
    return {"available": True, "indexed_chunks": count}


def has_chunks() -> bool:
    return get_collection().count() > 0


def destinations() -> list[str]:
    data = get_collection().get(include=["metadatas"])
    return sorted({item["destination"] for item in data.get("metadatas", []) if item.get("destination")})
