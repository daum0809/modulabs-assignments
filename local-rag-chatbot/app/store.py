"""SQLite 저장소: 문서, 문서 조각(청크), 임베딩."""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR", "./data")).resolve()
DB_PATH = DATA_DIR / "rag.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    text TEXT NOT NULL,
    embedding BLOB
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with conn() as c:
        c.executescript(SCHEMA)


def add_document(title, chunk_texts, embeddings=None):
    with conn() as c:
        doc_id = c.execute("INSERT INTO documents (title) VALUES (?)", (title,)).lastrowid
        c.executemany(
            "INSERT INTO chunks (doc_id, idx, text, embedding) VALUES (?, ?, ?, ?)",
            [(doc_id, i, t, embeddings[i] if embeddings else None) for i, t in enumerate(chunk_texts)])
        return doc_id


def list_documents():
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT d.id, d.title, d.created_at, COUNT(ch.id) AS chunks FROM documents d "
            "LEFT JOIN chunks ch ON ch.doc_id = d.id GROUP BY d.id ORDER BY d.id DESC")]


def find_document(title):
    with conn() as c:
        row = c.execute("SELECT id FROM documents WHERE title = ?", (title,)).fetchone()
        return row[0] if row else None


def delete_document(doc_id):
    with conn() as c:
        c.execute("DELETE FROM documents WHERE id = ?", (doc_id,))


def all_chunks():
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT ch.id, ch.doc_id, ch.text, ch.embedding, d.title "
            "FROM chunks ch JOIN documents d ON d.id = ch.doc_id ORDER BY ch.id")]


def set_chunk_embedding(chunk_id, emb):
    with conn() as c:
        c.execute("UPDATE chunks SET embedding = ? WHERE id = ?", (emb, chunk_id))


def clear_embeddings():
    with conn() as c:
        c.execute("UPDATE chunks SET embedding = NULL")


def get_meta(key):
    with conn() as c:
        row = c.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None


def set_meta(key, value):
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))
