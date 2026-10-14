"""Small synchronous client for the local Ollama HTTP API."""

import httpx

from app.config import settings


class OllamaError(RuntimeError):
    """An actionable error returned by or while connecting to Ollama."""


def _post(endpoint: str, payload: dict, timeout: float | None = None) -> dict:
    try:
        response = httpx.post(
            f"{settings.ollama_base_url}{endpoint}",
            json=payload,
            timeout=timeout or settings.ollama_timeout_seconds,
        )
        if response.status_code >= 400:
            detail = response.text[:500]
            raise OllamaError(f"Ollama request failed ({response.status_code}): {detail}")
        return response.json()
    except httpx.TimeoutException as exc:
        raise OllamaError("Ollama timed out. Check the local model and try again.") from exc
    except httpx.HTTPError as exc:
        raise OllamaError(
            f"Cannot connect to Ollama at {settings.ollama_base_url}. Start Ollama and try again."
        ) from exc
    except ValueError as exc:
        raise OllamaError("Ollama returned an invalid JSON response.") from exc


def list_models() -> list[str]:
    try:
        response = httpx.get(
            f"{settings.ollama_base_url}/api/tags",
            timeout=min(settings.ollama_timeout_seconds, 10),
        )
        response.raise_for_status()
        return [item["name"] for item in response.json().get("models", []) if item.get("name")]
    except (httpx.HTTPError, ValueError) as exc:
        raise OllamaError(
            f"Cannot connect to Ollama at {settings.ollama_base_url}. Start Ollama and try again."
        ) from exc


def chat(messages: list[dict[str, str]], model: str | None = None, json_mode: bool = False) -> str:
    payload = {
        "model": model or settings.ollama_model,
        "messages": messages,
        "stream": False,
    }
    if json_mode:
        payload["format"] = "json"
    response = _post("/api/chat", payload)
    try:
        return response["message"]["content"]
    except (KeyError, TypeError) as exc:
        raise OllamaError("Ollama returned a response without message content.") from exc


def embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    response = _post(
        "/api/embed",
        {"model": settings.ollama_embed_model, "input": texts},
        timeout=settings.ollama_timeout_seconds,
    )
    embeddings = response.get("embeddings")
    if not isinstance(embeddings, list) or len(embeddings) != len(texts):
        raise OllamaError(
            f"Embedding model '{settings.ollama_embed_model}' returned an unexpected response."
        )
    if any(not isinstance(vector, list) or not vector for vector in embeddings):
        raise OllamaError(f"Embedding model '{settings.ollama_embed_model}' returned an empty vector.")
    return embeddings


def check_status() -> dict:
    try:
        models = list_models()
    except OllamaError as exc:
        return {"available": False, "error": str(exc), "models": []}
    return {
        "available": True,
        "models": models,
        "chat_model_installed": settings.ollama_model in models,
        "embedding_model_installed": settings.ollama_embed_model in models,
    }
