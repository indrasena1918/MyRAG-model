"""Index the bundled travel guides (or files in data/travel_documents) locally."""

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


def main() -> int:
    files = [
        path
        for path in settings.documents_path.glob("*")
        if path.is_file() and path.suffix.lower() in {".pdf", ".txt", ".md", ".markdown"}
    ]
    if not files:
        print(f"No PDF, TXT, or Markdown documents found in {settings.documents_path}")
        return 1
    with TestClient(app) as client:
        handles = [path.open("rb") for path in files]
        try:
            response = client.post(
                "/api/documents/ingest",
                files=[("files", (path.name, handle, "application/octet-stream")) for path, handle in zip(files, handles)],
            )
        finally:
            for handle in handles:
                handle.close()
    if response.is_error:
        print(f"Indexing failed ({response.status_code}): {response.json().get('detail', response.text)}")
        return 1
    result = response.json()
    for item in result["indexed"]:
        print(f"Indexed {item['filename']}: {item['chunks']} chunks ({item['destination']})")
    print(f"Done: {result['total_chunks']} chunks in total.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
