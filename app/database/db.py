"""SQLite persistence for saved itineraries and chat history."""

import json
import sqlite3

from app.config import settings


def connect() -> sqlite3.Connection:
    settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.sqlite_path, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def initialize() -> None:
    with connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS trips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                destination TEXT NOT NULL,
                itinerary_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                citations_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_conversation ON chat_history(conversation_id, id)"
        )


def save_chat(conversation_id: str, question: str, answer: str, citations: list[dict]) -> None:
    with connect() as connection:
        connection.execute(
            "INSERT INTO chat_history (conversation_id, question, answer, citations_json) VALUES (?, ?, ?, ?)",
            (conversation_id, question, answer, json.dumps(citations, ensure_ascii=False)),
        )


def get_chat(conversation_id: str) -> list[dict]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT question, answer, citations_json, created_at FROM chat_history "
            "WHERE conversation_id = ? ORDER BY id",
            (conversation_id,),
        ).fetchall()
    return [
        {
            "question": row["question"],
            "answer": row["answer"],
            "citations": json.loads(row["citations_json"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def save_trip(title: str, destination: str, itinerary: dict) -> dict:
    with connect() as connection:
        cursor = connection.execute(
            "INSERT INTO trips (title, destination, itinerary_json) VALUES (?, ?, ?)",
            (title, destination, json.dumps(itinerary, ensure_ascii=False)),
        )
        row = connection.execute("SELECT * FROM trips WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return _trip_record(row)


def list_trips() -> list[dict]:
    with connect() as connection:
        rows = connection.execute("SELECT * FROM trips ORDER BY id DESC").fetchall()
    return [_trip_record(row) for row in rows]


def get_trip(trip_id: int) -> dict | None:
    with connect() as connection:
        row = connection.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
    return _trip_record(row) if row else None


def delete_trip(trip_id: int) -> bool:
    with connect() as connection:
        cursor = connection.execute("DELETE FROM trips WHERE id = ?", (trip_id,))
    return cursor.rowcount > 0


def _trip_record(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "destination": row["destination"],
        "itinerary": json.loads(row["itinerary_json"]),
        "created_at": row["created_at"],
    }
