# Wayfarer — Local Travel Planning RAG Assistant

A beginner-friendly travel planner powered by your local Ollama models. It indexes travel guides in ChromaDB, answers questions with document citations, creates date-constrained itineraries, and stores trips and chat history in SQLite. Requests and documents are processed locally; there are no paid model APIs.

## Requirements

- Windows 10/11
- Python 3.11 or newer
- Ollama for Windows, running at `http://localhost:11434`
- Microsoft Visual C++ Build Tools with the C++ build tools workload (required on Windows to compile ChromaDB's HNSW extension when no compatible wheel is available)
- Existing chat models: `qwen2.5:3b` (default) and optionally `llama3.2:latest`
- Embedding model: `nomic-embed-text`

The chat model and embedding model are separate. Changing the chat model does not change the embedding model.

## Windows Command Prompt setup

Run these commands from the project folder in **Command Prompt** (`cmd.exe`):

```bat
py --version
ollama --version
ollama list
curl http://localhost:11434/api/tags

py -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
```

If `pip install -r requirements.txt` reports that Microsoft Visual C++ 14.0 or newer is required, install **Visual Studio Build Tools 2022** and select the **Desktop development with C++** workload, then retry the installation.

Confirm `ollama list` includes `qwen2.5:3b` and `llama3.2:latest`. The app defaults to `qwen2.5:3b`. To use Llama instead, edit `.env` and set `OLLAMA_MODEL=llama3.2:latest`; no application code changes are needed. The frontend also lets you select either model when it is installed.

Check whether the embedding model is present in `ollama list`. Only if it is missing, install it:

```bat
ollama pull nomic-embed-text
```

Ollama itself can be started from the Start menu. If you need to start its local server manually, open a separate Command Prompt and run `ollama serve` (do not start a second server when the Ollama desktop app is already running).

## Add documents and run the app

The included starter guides are in `data\travel_documents\` (Hyderabad, Kerala, Tirupati). Add your own PDF, TXT, or Markdown travel guides to this same folder. PDFs should contain selectable text; scanned-image PDFs need OCR before ingestion.

```bat
call .venv\Scripts\activate.bat
python scripts\ingest_documents.py
python -m uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000** in your browser. The frontend is served by FastAPI; do not open the HTML file directly. API documentation is available at **http://127.0.0.1:8000/docs**.

To index more documents while the app is running, use the upload panel or:

```bat
curl -X POST http://127.0.0.1:8000/api/documents/ingest -F "files=@data\travel_documents\hyderabad.md"
```

An optional `destination` form field can override the destination metadata for all uploaded files:

```bat
curl -X POST http://127.0.0.1:8000/api/documents/ingest -F "files=@my_guide.pdf" -F "destination=Coorg"
```

## Tests

Ollama does not need to be running for the automated unit/API tests; model calls are mocked.

```bat
call .venv\Scripts\activate.bat
python -m pytest -q
```

`data\evaluation_questions.txt` contains 20 example questions for manual grounding checks. No retrieval-quality or answer-quality score is claimed: meaningful quality evaluation requires running the actual local embedding and chat models against a labeled relevance/answer dataset.

## API overview

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Backend, Ollama/model, and ChromaDB status |
| `GET` | `/api/models` | Installed models and selectable chat models |
| `POST` | `/api/chat` | Grounded question answering with source citations |
| `GET` | `/api/conversations/{conversation_id}` | Retrieve persisted conversation messages |
| `POST` | `/api/itinerary/generate` | Personalized itinerary and deterministic budget allocation |
| `POST` | `/api/documents/ingest` | Upload and index PDF/TXT/Markdown documents |
| `GET` | `/api/destinations` | Destinations found in indexed metadata |
| `POST` | `/api/trips` | Save an itinerary |
| `GET` | `/api/trips` | List saved trips |
| `GET` | `/api/trips/{trip_id}` | Retrieve a saved trip |
| `DELETE` | `/api/trips/{trip_id}` | Delete a saved trip |

The chat request accepts `question`, plus optional `model` and `conversation_id`. The itinerary request accepts starting city, destination, inclusive start/end dates, travelers, total INR budget, interests, travel mode, accommodation preference, pace, optional dietary/accessibility requirements, and optional model.

## How it works

1. The loader extracts PDF text page by page or decodes TXT/Markdown. Chunks keep destination, filename, section, and page metadata.
2. Chunks are embedded by the configured Ollama **embedding** model and saved in persistent ChromaDB.
3. Each user question is embedded with that same embedding model. Retrieved passages are passed to the selected local **chat** model with instructions to use evidence and cite supplied source labels.
4. If no documents or enough evidence are available, chat returns a clear limitation instead of asking the LLM to answer from general knowledge alone. Current prices, schedules, hours, and availability are never represented as verified.
5. Itinerary generation uses the selected model for the day plans but validates the number of days and generates the actual date sequence in Python. A reproducible 25/35/25/remaining percentage budget allocation is calculated in Python, sums exactly to the requested ceiling, and is explicitly a planning allocation—not a price quote.
6. SQLite stores saved trips and chat turns under `data\travel.db`; ChromaDB persists under `data\chroma`.

Uploaded document text is reference material and is explicitly treated as untrusted by the answer prompt. Files are limited to 15 MB per upload. Document data, the vector index, and trip/chat history are local application data.

## Configuration

Edit `.env` (created from `.env.example`):

```dotenv
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b
OLLAMA_EMBED_MODEL=nomic-embed-text
OLLAMA_TIMEOUT_SECONDS=120
CHROMA_PATH=data/chroma
SQLITE_PATH=data/travel.db
DOCUMENTS_PATH=data/travel_documents
CHUNK_SIZE=900
CHUNK_OVERLAP=150
RETRIEVAL_RESULTS=5
RETRIEVAL_DISTANCE_THRESHOLD=0.65
```

Keep `OLLAMA_EMBED_MODEL` the same when ingesting and searching. Changing embedding models can change vector dimensions or vector space; if you change it, clear the local Chroma data folder and re-ingest the entire document collection. Do not mix embeddings from different models in one collection.

## Troubleshooting

- **`model not found` / chat model missing:** run `ollama list`; install only the requested existing model if necessary (`ollama pull qwen2.5:3b` or `ollama pull llama3.2:latest`), then restart the app. Select a model that appears in the model selector.
- **Ollama connection refused:** start the Ollama desktop app or run `ollama serve` in its own terminal; test `curl http://localhost:11434/api/tags`. Confirm `.env` has the correct `OLLAMA_BASE_URL`.
- **Embedding model missing:** check `ollama list`, then run `ollama pull nomic-embed-text`. The app health endpoint reports chat and embedding model availability separately.
- **Embedding dimension mismatch after changing embedding model:** stop the app, remove only the generated `data\chroma` folder, re-index every travel document with the newly configured embedding model, and restart. Do not remove `data\travel.db` unless you intentionally want to erase saved trips/chat history.
- **Empty or irrelevant retrieval:** confirm `GET /api/destinations` lists the expected destination, upload a text-based document with useful headings and destination details, and ask a specific question. Retrieval omits weak cosine matches above `RETRIEVAL_DISTANCE_THRESHOLD` (default `0.65`); lower it cautiously if good matches are being filtered. Scanned PDFs need OCR. Current/live facts are not in the sample documents and cannot be inferred reliably.
- **PDF upload says no readable text:** it is likely image-only; OCR it with a trusted local tool and upload a text-searchable PDF or TXT/Markdown export.
- **Port 8000 is busy:** use `python -m uvicorn app.main:app --reload --port 8001` and open `http://127.0.0.1:8001`.

## Project layout

```text
app/
  main.py                 FastAPI routes and upload handling
  config.py               .env-backed local settings
  schemas.py              Pydantic API schemas
  database/db.py          SQLite trip and conversation history
  rag/                    Extraction, chunking, embeddings, Chroma, retrieval, citations
  services/               Ollama client and itinerary/budget services
frontend/                 Responsive vanilla HTML, CSS, and JavaScript
data/
  travel_documents/       Bundled and user-provided travel guides
  evaluation_questions.txt 20 manual evaluation prompts
scripts/                  Local document-ingestion command
tests/                    Pytest coverage; does not require Ollama
```
