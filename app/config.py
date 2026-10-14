"""Application settings loaded from environment variables and an optional .env file."""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class Settings:
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
    ollama_embed_model = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    ollama_timeout_seconds = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))
    chroma_path = Path(os.getenv("CHROMA_PATH", str(PROJECT_ROOT / "data" / "chroma")))
    sqlite_path = Path(os.getenv("SQLITE_PATH", str(PROJECT_ROOT / "data" / "travel.db")))
    documents_path = Path(os.getenv("DOCUMENTS_PATH", str(PROJECT_ROOT / "data" / "travel_documents")))
    frontend_path = PROJECT_ROOT / "frontend"
    chunk_size = int(os.getenv("CHUNK_SIZE", "900"))
    chunk_overlap = int(os.getenv("CHUNK_OVERLAP", "150"))
    retrieval_results = int(os.getenv("RETRIEVAL_RESULTS", "5"))
    retrieval_distance_threshold = float(os.getenv("RETRIEVAL_DISTANCE_THRESHOLD", "0.65"))


settings = Settings()
