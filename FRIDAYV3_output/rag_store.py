"""
rag_store.py — FRIDAY RAG (Retrieval-Augmented Generation) Store

Allows FRIDAY to ingest documents (PDF, TXT, DOCX) and answer questions
from them using semantic vector search.

How it works:
  1. ingest(source, text)    → splits text into chunks → embeds → stores in SQLite
  2. search(query, top_k)    → embeds query → cosine similarity → returns top chunks
  3. tool_executor.py calls  ingest_document() and query_documents() which use this

Dependencies:
  pip install sentence-transformers numpy

The embedding model (all-MiniLM-L6-v2) is small (~80MB), fast, and runs
fully offline on CPU. It's downloaded once and cached automatically.
"""

import sqlite3
import hashlib
import os
import threading
import numpy as np

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "friday_rag.db")
_lock   = threading.Lock()

# Lazy-loaded embedding model — only imported when first used
_model  = None


# ================= DB SETUP =================

def _conn() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def _init_db():
    with _lock, _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                source  TEXT,
                chunk   TEXT,
                hash    TEXT UNIQUE,
                vector  BLOB,
                added_at TEXT DEFAULT (datetime('now'))
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_source ON chunks(source)")


_init_db()


# ================= EMBEDDING =================

def _get_model():
    """Lazy-load the sentence transformer model."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            print("[RAG] Loading embedding model (first time only)...")
            _model = SentenceTransformer("all-MiniLM-L6-v2")
            print("[RAG] Embedding model ready.")
        except ImportError:
            raise ImportError(
                "sentence-transformers not installed. Run: pip install sentence-transformers"
            )
    return _model


def _embed(texts: list[str]) -> np.ndarray:
    """Embed a list of strings. Returns float32 array of shape (n, dim)."""
    model = _get_model()
    return model.encode(texts, convert_to_numpy=True, show_progress_bar=False).astype(np.float32)


# ================= CHUNKING =================

def _chunk_text(text: str, chunk_size: int = 300, overlap: int = 50) -> list[str]:
    """
    Split text into overlapping word-level chunks.
    chunk_size=300 words (~400 tokens) fits well within Groq context.
    overlap=50 prevents losing context at chunk boundaries.
    """
    words  = text.split()
    chunks = []
    start  = 0

    while start < len(words):
        end   = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end]).strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(words):
            break
        start += chunk_size - overlap  # slide with overlap

    return chunks


# ================= INGEST =================

def ingest(source: str, text: str, chunk_size: int = 300) -> int:
    """
    Ingest a document into the RAG store.

    Args:
        source:     Identifier (e.g. file path or name).
        text:       Full document text.
        chunk_size: Words per chunk (default 300).

    Returns:
        Number of new chunks stored.
    """
    chunks = _chunk_text(text, chunk_size=chunk_size)
    if not chunks:
        print(f"[RAG] No content to ingest from {source}")
        return 0

    # Filter out chunks already stored (by hash)
    new_chunks = []
    new_hashes = []
    for ch in chunks:
        h = hashlib.md5(ch.encode("utf-8")).hexdigest()
        with _conn() as c:
            exists = c.execute(
                "SELECT 1 FROM chunks WHERE hash = ?", (h,)
            ).fetchone()
        if not exists:
            new_chunks.append(ch)
            new_hashes.append(h)

    if not new_chunks:
        print(f"[RAG] All chunks from {source} already stored.")
        return 0

    # Batch embed
    vectors = _embed(new_chunks)

    with _lock, _conn() as c:
        for ch, h, vec in zip(new_chunks, new_hashes, vectors):
            c.execute(
                "INSERT OR IGNORE INTO chunks (source, chunk, hash, vector) VALUES (?, ?, ?, ?)",
                (source, ch, h, vec.tobytes())
            )

    print(f"[RAG] Ingested {len(new_chunks)} new chunks from: {os.path.basename(source)}")
    return len(new_chunks)


# ================= SEARCH =================

def search(query: str, top_k: int = 3, source_filter: str = None) -> list[str]:
    """
    Semantic search over stored chunks.

    Args:
        query:         The search query string.
        top_k:         Number of top results to return.
        source_filter: Optional — restrict search to a specific source.

    Returns:
        List of relevant text chunks, ranked by cosine similarity.
    """
    # Fetch all stored chunks (and their vectors)
    with _conn() as c:
        if source_filter:
            rows = c.execute(
                "SELECT chunk, vector FROM chunks WHERE source = ?",
                (source_filter,)
            ).fetchall()
        else:
            rows = c.execute("SELECT chunk, vector FROM chunks").fetchall()

    if not rows:
        return []

    chunks  = [r[0] for r in rows]
    vectors = np.stack([
        np.frombuffer(r[1], dtype=np.float32) for r in rows
    ])

    # Embed query
    q_vec = _embed([query])[0]

    # Cosine similarity
    norms   = np.linalg.norm(vectors, axis=1) * np.linalg.norm(q_vec) + 1e-9
    scores  = vectors @ q_vec / norms
    top_idx = np.argsort(scores)[-top_k:][::-1]

    # Filter out very low similarity results (< 0.2)
    results = []
    for i in top_idx:
        if scores[i] > 0.2:
            results.append(chunks[i])

    return results


# ================= MANAGEMENT =================

def list_sources() -> list[str]:
    """Return all unique document sources in the store."""
    with _conn() as c:
        rows = c.execute(
            "SELECT DISTINCT source FROM chunks ORDER BY source"
        ).fetchall()
    return [r[0] for r in rows]


def delete_source(source: str) -> int:
    """Remove all chunks from a specific source. Returns number deleted."""
    with _lock, _conn() as c:
        cur = c.execute("DELETE FROM chunks WHERE source = ?", (source,))
    print(f"[RAG] Deleted {cur.rowcount} chunks from: {source}")
    return cur.rowcount


def chunk_count() -> int:
    """Return total number of chunks stored."""
    with _conn() as c:
        row = c.execute("SELECT COUNT(*) FROM chunks").fetchone()
    return row[0] if row else 0
