"""FastAPI entry point for the local travel planning RAG assistant."""

import hashlib
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import db
from app.rag.chunker import chunk_text
from app.rag.document_loader import detect_destination, extract_document
from app.rag.embeddings import embed_texts
from app.rag.generator import generate_answer
from app.rag.retriever import retrieve
from app.rag.vector_store import add_chunks, destinations, status as vector_status
from app.schemas import ChatRequest, ChatResponse, ItineraryRequest, ItineraryResponse, TripCreate, TripRecord
from app.services.itinerary_service import generate_itinerary
from app.services.ollama_service import OllamaError, check_status, list_models

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
logger = logging.getLogger("travel_rag")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.documents_path.mkdir(parents=True, exist_ok=True)
    db.initialize()
    yield


app = FastAPI(
    title="Travel Planning RAG Assistant",
    description="Local travel planning powered by Ollama, ChromaDB, and your travel documents.",
    version="1.0.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=settings.frontend_path), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(settings.frontend_path / "index.html")


@app.get("/health")
def health():
    ollama = check_status()
    try:
        vector = vector_status()
    except Exception as exc:
        logger.exception("Vector database health check failed.")
        vector = {"available": False, "error": "Vector database is unavailable; check local application logs."}
    return {"backend": "ok", "ollama": ollama, "vector_database": vector}


@app.get("/api/models")
def models():
    try:
        installed = list_models()
    except OllamaError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    known = ["qwen2.5:3b", "llama3.2:latest"]
    return {
        "models": [name for name in known if name in installed],
        "available_models": installed,
        "default_model": settings.ollama_model,
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest):
    try:
        passages = retrieve(request.question)
        result = generate_answer(request.question, passages, request.model)
    except OllamaError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Chat retrieval or generation failed.")
        raise HTTPException(
            status_code=500,
            detail="Could not retrieve or generate an answer. Check local application logs.",
        ) from exc
    conversation_id = request.conversation_id or str(uuid.uuid4())
    db.save_chat(conversation_id, request.question, result["answer"], result["citations"])
    return {**result, "conversation_id": conversation_id}


@app.get("/api/conversations/{conversation_id}")
def conversation_history(conversation_id: str):
    return {"conversation_id": conversation_id, "messages": db.get_chat(conversation_id)}


@app.post("/api/itinerary/generate", response_model=ItineraryResponse)
def itinerary_endpoint(request: ItineraryRequest):
    try:
        return generate_itinerary(request)
    except OllamaError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Itinerary generation failed.")
        raise HTTPException(
            status_code=502,
            detail="Could not generate itinerary. Check local application logs.",
        ) from exc


@app.post("/api/documents/ingest")
def ingest_documents(
    files: list[UploadFile] = File(...),
    destination: str | None = Form(default=None),
):
    indexed_files = []
    all_chunks = []
    for upload in files:
        content = upload.file.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f"'{upload.filename}' exceeds the 15 MB upload limit.")
        filename = Path(upload.filename or "upload.txt").name
        try:
            pages = extract_document(filename, content)
        except (ValueError, UnicodeDecodeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        destination_name = (destination or "").strip() or detect_destination(
            filename, "\n".join(p["text"] for p in pages)
        )
        page_chunks = []
        for page in pages:
            for item in chunk_text(page["text"], settings.chunk_size, settings.chunk_overlap):
                page_chunks.append(
                    {
                        "id": hashlib.sha256(
                            f"{filename}:{page['page']}:{item['section']}:{item['text']}".encode("utf-8")
                        ).hexdigest(),
                        "text": item["text"],
                        "metadata": {
                            "destination": destination_name,
                            "source": filename,
                            "section": item["section"],
                            "page": page["page"] or 0,
                        },
                    }
                )
        if not page_chunks:
            raise HTTPException(status_code=400, detail=f"No indexable text found in '{filename}'.")
        all_chunks.extend(page_chunks)
        indexed_files.append({"filename": filename, "destination": destination_name, "chunks": len(page_chunks)})

    try:
        for offset in range(0, len(all_chunks), 32):
            batch = all_chunks[offset : offset + 32]
            add_chunks(batch, embed_texts([item["text"] for item in batch]))
    except OllamaError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Document indexing failed.")
        raise HTTPException(
            status_code=500,
            detail=(
                "Could not index documents. If the embedding model changed, remove the local Chroma data "
                "and re-ingest all documents; otherwise check local application logs."
            ),
        ) from exc
    return {"indexed": indexed_files, "total_chunks": len(all_chunks)}


@app.get("/api/destinations")
def destination_list():
    try:
        return {"destinations": destinations()}
    except Exception as exc:
        logger.exception("Could not list indexed destinations.")
        raise HTTPException(
            status_code=500,
            detail="Could not list indexed destinations. Check local application logs.",
        ) from exc


@app.post("/api/trips", response_model=TripRecord)
def create_trip(request: TripCreate):
    return db.save_trip(request.title, request.destination, request.itinerary)


@app.get("/api/trips", response_model=list[TripRecord])
def trips():
    return db.list_trips()


@app.get("/api/trips/{trip_id}", response_model=TripRecord)
def trip(trip_id: int):
    saved = db.get_trip(trip_id)
    if saved is None:
        raise HTTPException(status_code=404, detail="Saved trip not found.")
    return saved


@app.delete("/api/trips/{trip_id}")
def remove_trip(trip_id: int):
    if not db.delete_trip(trip_id):
        raise HTTPException(status_code=404, detail="Saved trip not found.")
    return {"deleted": True}


@app.get("/api/search")
def search_documents(q: str):
    if len(q.strip()) < 3:
        raise HTTPException(status_code=422, detail="Search query must contain at least three characters.")
    try:
        passages = retrieve(q, limit=5)
        return {
            "results": [
                {
                    "text": item["text"],
                    "source": item["metadata"].get("source"),
                    "destination": item["metadata"].get("destination"),
                    "section": item["metadata"].get("section"),
                    "page": item["metadata"].get("page") or None,
                    "distance": item["distance"],
                }
                for item in passages
            ]
        }
    except OllamaError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
