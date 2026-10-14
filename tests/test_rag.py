import json

import fitz
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.rag import generator
from app.rag.chunker import chunk_text
from app.rag.citations import citations_for
from app.rag.document_loader import extract_document
from app.rag import retriever
from app.rag import vector_store
from app.services import budget_service, ollama_service


def test_text_document_extraction_and_destination():
    pages = extract_document("guide.md", b"# Munnar\n\nTea gardens and hill trails.")
    assert len(pages) == 1
    assert pages[0]["text"] == "# Munnar\n\nTea gardens and hill trails."


def test_pdf_text_extraction_includes_page_numbers():
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Tirupati temple visitor guidance")
    content = document.tobytes()
    document.close()
    pages = extract_document("guide.pdf", content)
    assert pages == [{"text": "Tirupati temple visitor guidance", "page": 1}]


def test_empty_unsupported_and_invalid_utf8_documents_are_rejected():
    with pytest.raises(ValueError, match="Unsupported"):
        extract_document("guide.docx", b"text")
    with pytest.raises(ValueError, match="No readable text"):
        extract_document("empty.txt", b" \n ")
    with pytest.raises(UnicodeDecodeError):
        extract_document("broken.txt", b"\xff")
    with pytest.raises(ValueError, match="Could not read PDF"):
        extract_document("broken.pdf", b"not a pdf")


def test_chunking_respects_size_overlap_and_section_metadata():
    chunks = chunk_text("# Places\n\n" + ("historic temple garden " * 30), chunk_size=80, overlap=12)
    assert len(chunks) > 1
    assert all(len(item["text"]) <= 80 for item in chunks)
    assert all(item["section"] == "Places" for item in chunks)
    assert all(item["text"] for item in chunks)


def test_invalid_chunk_sizes_are_rejected():
    with pytest.raises(ValueError):
        chunk_text("text", chunk_size=10, overlap=10)


def test_embedding_generation_uses_configured_embedding_endpoint(monkeypatch):
    seen = {}

    def fake_post(endpoint, payload, timeout=None):
        seen["endpoint"] = endpoint
        seen["payload"] = payload
        return {"embeddings": [[0.1, 0.2]]}

    monkeypatch.setattr(ollama_service, "_post", fake_post)
    assert ollama_service.embed(["travel"]) == [[0.1, 0.2]]
    assert seen["endpoint"] == "/api/embed"
    assert seen["payload"]["model"] == ollama_service.settings.ollama_embed_model
    assert seen["payload"]["input"] == ["travel"]


def test_embedding_model_malformed_response_is_reported(monkeypatch):
    monkeypatch.setattr(ollama_service, "_post", lambda *args, **kwargs: {"embeddings": []})
    with pytest.raises(ollama_service.OllamaError, match="unexpected response"):
        ollama_service.embed(["travel"])


def test_retrieval_skips_embedding_when_no_documents(monkeypatch):
    monkeypatch.setattr(retriever, "has_chunks", lambda: False)
    monkeypatch.setattr(retriever, "embed_texts", lambda _: pytest.fail("embedding should not be called"))
    assert retriever.retrieve("question about an empty index") == []


def test_retrieval_embeds_question_and_queries_vector_store(monkeypatch):
    monkeypatch.setattr(retriever, "has_chunks", lambda: True)
    monkeypatch.setattr(retriever, "embed_texts", lambda texts: [[0.1, 0.2]])
    monkeypatch.setattr(retriever, "query", lambda vector, limit: [{"text": "source", "metadata": {}, "distance": 0.1}])
    assert retriever.retrieve("query", limit=2)[0]["text"] == "source"


def test_retrieval_drops_weak_cosine_matches(monkeypatch):
    monkeypatch.setattr(retriever, "has_chunks", lambda: True)
    monkeypatch.setattr(retriever, "embed_texts", lambda texts: [[0.1, 0.2]])
    monkeypatch.setattr(
        retriever,
        "query",
        lambda vector, limit: [
            {"text": "relevant", "metadata": {}, "distance": 0.2},
            {"text": "weak match", "metadata": {}, "distance": 0.9},
        ],
    )
    assert [item["text"] for item in retriever.retrieve("query")] == ["relevant"]


def test_chroma_persistence_query_and_destination_listing(monkeypatch, tmp_path):
    monkeypatch.setattr(vector_store.settings, "chroma_path", tmp_path / "chroma")
    monkeypatch.setattr(vector_store, "_client", None)
    monkeypatch.setattr(vector_store, "_collection", None)
    vector_store.add_chunks(
        [
            {
                "id": "sample-chunk",
                "text": "Tirupati temple access guidance.",
                "metadata": {
                    "destination": "Tirupati",
                    "source": "guide.md",
                    "section": "Temples",
                    "page": 1,
                },
            }
        ],
        [[1.0, 0.0]],
    )
    matches = vector_store.query([1.0, 0.0], limit=2)
    assert matches[0]["text"] == "Tirupati temple access guidance."
    assert matches[0]["metadata"]["source"] == "guide.md"
    assert vector_store.status()["indexed_chunks"] == 1
    assert vector_store.destinations() == ["Tirupati"]


def test_citations_use_retrieved_document_metadata_and_stable_labels():
    passage = {
        "text": "Visitor information",
        "metadata": {"source": "guide.pdf", "section": "Access", "page": 3},
    }
    citations = citations_for([passage, passage])
    assert [citation["label"] for citation in citations] == ["S1", "S2"]
    assert all(citation["source"] == "guide.pdf" for citation in citations)
    assert citations[0]["page"] == 3


def test_grounded_answer_uses_model_and_citations(monkeypatch):
    monkeypatch.setattr(generator, "chat", lambda *args, **kwargs: "Check current access [S1].")
    result = generator.generate_answer(
        "How can I visit?",
        [{"text": "Contact the temple for access.", "metadata": {"source": "temple.md", "page": 1}}],
    )
    assert result["grounded"] is True
    assert "[S1]" in result["answer"]
    assert result["citations"][0]["source"] == "temple.md"


def test_unsupported_model_citation_is_rejected(monkeypatch):
    monkeypatch.setattr(generator, "chat", lambda *args, **kwargs: "There is a fort [S2].")
    with pytest.raises(ValueError, match="unsupported citation labels"):
        generator.generate_answer(
            "Where?",
            [{"text": "The fort is historic.", "metadata": {"source": "guide.md"}}],
        )


def test_insufficient_evidence_does_not_call_llm(monkeypatch):
    monkeypatch.setattr(generator, "chat", lambda *args, **kwargs: pytest.fail("LLM must not answer"))
    result = generator.generate_answer("Question?", [{"text": "Short", "metadata": {"source": "a.txt"}}])
    assert result["grounded"] is False
    assert "not have enough information" in result["answer"]
    assert result["citations"] == []


@pytest.mark.parametrize("budget", [1, 7999, 8000, 250000])
def test_budget_allocation_is_deterministic_and_never_exceeds_budget(budget):
    result = budget_service.allocate_budget(budget)
    assert result["total"] == budget
    assert sum(result[key] for key in ("transport", "accommodation", "food", "activities")) == budget
    assert all(result[key] >= 0 for key in ("transport", "accommodation", "food", "activities"))


def test_invalid_budget_is_rejected():
    with pytest.raises(ValueError):
        budget_service.allocate_budget(0)


def test_ollama_unavailable_has_actionable_error(monkeypatch):
    import httpx

    def unavailable(*args, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(ollama_service.httpx, "get", unavailable)
    with pytest.raises(ollama_service.OllamaError, match="Start Ollama"):
        ollama_service.list_models()


def test_missing_model_response_is_not_hidden(monkeypatch):
    monkeypatch.setattr(
        ollama_service,
        "_post",
        lambda *args, **kwargs: (_ for _ in ()).throw(ollama_service.OllamaError("model not found")),
    )
    with pytest.raises(ollama_service.OllamaError, match="model not found"):
        ollama_service.chat([{"role": "user", "content": "hello"}])


def test_itinerary_generation_respects_dates_budget_and_day_count(monkeypatch):
    from app.schemas import ItineraryRequest
    from app.services import itinerary_service

    monkeypatch.setattr(itinerary_service, "retrieve", lambda *args, **kwargs: [])
    days = [{"morning": "Visit a garden", "afternoon": "Rest", "evening": "Try local food"}] * 2
    monkeypatch.setattr(
        itinerary_service,
        "chat",
        lambda *args, **kwargs: json.dumps(
            {
                "days": days,
                "transport_suggestion": "Check current bus services.",
                "accommodation_suggestion": "Choose a stay matching your preference.",
                "travel_tips": ["Verify current opening hours."],
            }
        ),
    )
    request = ItineraryRequest(
        starting_city="Bengaluru",
        destination="Munnar",
        start_date="2026-11-01",
        end_date="2026-11-02",
        travelers=2,
        budget_inr=8000,
        interests=["nature"],
        travel_preference="bus",
        accommodation_preference="Budget hotel",
        pace="relaxed",
    )
    result = itinerary_service.generate_itinerary(request)
    assert [day["date"] for day in result["days"]] == ["2026-11-01", "2026-11-02"]
    assert result["budget"]["total"] == request.budget_inr
    assert result["limitations"]


def test_itinerary_rejects_model_day_count_that_violates_dates(monkeypatch):
    from app.schemas import ItineraryRequest
    from app.services import itinerary_service

    monkeypatch.setattr(itinerary_service, "retrieve", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        itinerary_service,
        "chat",
        lambda *args, **kwargs: json.dumps(
            {"days": [], "transport_suggestion": "", "accommodation_suggestion": "", "travel_tips": []}
        ),
    )
    request = ItineraryRequest(
        starting_city="Bengaluru",
        destination="Munnar",
        start_date="2026-11-01",
        end_date="2026-11-02",
        travelers=1,
        budget_inr=8000,
        interests=["nature"],
        travel_preference="bus",
        accommodation_preference="Budget",
        pace="relaxed",
    )
    with pytest.raises(ValueError, match="exactly 2 itinerary days"):
        itinerary_service.generate_itinerary(request)


def test_invalid_api_payload_returns_validation_error():
    with TestClient(app) as client:
        response = client.post("/api/itinerary/generate", json={"destination": "Tirupati"})
    assert response.status_code == 422


def test_chat_with_no_indexed_documents_returns_limitation(monkeypatch):
    monkeypatch.setattr("app.main.retrieve", lambda _: [])
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"question": "Where should I go?"})
    assert response.status_code == 200
    assert response.json()["grounded"] is False
