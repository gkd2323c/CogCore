"""M4.1 semantic store.

SQLite stores vector BLOBs; cosine similarity is computed in Python to avoid
sqlite-vec / pgvector / native module dependencies.
"""
from __future__ import annotations

import dataclasses
import json
import math
import os
import sqlite3
import time
from typing import Any

from cogcore.embeddings import EmbeddingProvider, MockEmbeddingProvider


@dataclasses.dataclass
class SemanticResult:
    """A semantic search result."""

    id: int
    text: str
    score: float
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(n))
    na = math.sqrt(sum(x * x for x in a[:n]))
    nb = math.sqrt(sum(x * x for x in b[:n]))
    if na == 0 or nb == 0:
        return 0.0
    return round(dot / (na * nb), 6)


class SemanticStore:
    """SQLite-backed semantic memory."""

    def __init__(
        self,
        path: str = "cogcore_data/semantic.db",
        *,
        provider: EmbeddingProvider | None = None,
    ) -> None:
        self.path = path
        self.provider = provider or MockEmbeddingProvider()
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self.conn = sqlite3.connect(path, timeout=30.0)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "SemanticStore":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def _init_schema(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS semantic_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                vector BLOB NOT NULL,
                metadata TEXT NOT NULL,
                created_ts REAL NOT NULL
            )
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_semantic_memory_created ON semantic_memory(created_ts)"
        )
        self.conn.commit()

    def add(self, text: str, metadata: dict[str, Any] | None = None) -> int:
        vector = self.provider.embed(text)
        cur = self.conn.execute(
            """
            INSERT INTO semantic_memory(text, vector, metadata, created_ts)
            VALUES (?, ?, ?, ?)
            """,
            (
                text,
                _encode_vector(vector),
                json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
                time.time(),
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        threshold: float = 0.7,
    ) -> list[SemanticResult]:
        if top_k <= 0:
            return []
        query_vec = self.provider.embed(query)
        rows = self.conn.execute(
            "SELECT id, text, vector, metadata FROM semantic_memory"
        ).fetchall()
        results = []
        for row in rows:
            score = cosine_similarity(query_vec, _decode_vector(row["vector"]))
            if score < threshold:
                continue
            results.append(
                SemanticResult(
                    id=row["id"],
                    text=row["text"],
                    score=score,
                    metadata=json.loads(row["metadata"]),
                )
            )
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]


class DualStore:
    """HDB + SemanticStore lookup wrapper."""

    def __init__(self, hdb: Any, semantic: SemanticStore) -> None:
        self.hdb = hdb
        self.semantic = semantic

    def lookup_or_search(
        self,
        atoms: list[Any],
        *,
        top_k: int = 5,
        threshold: float = 0.0,
    ) -> dict[str, Any]:
        hdb_report = self.hdb.get_hdb_report() if hasattr(self.hdb, "get_hdb_report") else {}
        query = " ".join(str(getattr(atom, "content", atom)) for atom in atoms)
        semantic_results = self.semantic.search(query, top_k=top_k, threshold=threshold)
        return {
            "hdb": hdb_report,
            "semantic_results": semantic_results,
            "used_semantic_fallback": bool(semantic_results),
        }


def _encode_vector(vector: list[float]) -> bytes:
    return json.dumps(vector, separators=(",", ":")).encode("utf-8")


def _decode_vector(blob: bytes) -> list[float]:
    if isinstance(blob, memoryview):
        blob = blob.tobytes()
    return [float(x) for x in json.loads(blob.decode("utf-8"))]
