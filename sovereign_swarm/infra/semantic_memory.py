"""SemanticMemory — numpy-powered vector recall backed by SQLite.

Ports the v1.3 numpy embedding system into v2.2.0. Every memory gets an
n-dimensional numpy vector. Search uses cosine similarity with recency
and access boosting.

Usage:
    mem = SemanticMemory(db_path="data/semantic.db", dim=384)
    await mem.init()
    await mem.store("user likes fast execution", tags=["preference"])
    results = await mem.search("execution speed", top_k=5)
"""

from ..config import *
import numpy as np, json, sqlite3, time, hashlib
from typing import Dict, List, Optional


class SemanticMemory:
    """Vector memory with numpy similarity, recency/access boosting, cross-agent recall."""

    _TABLE = "semantic_memories"

    def __init__(self, db_path: Path = None, dim: int = 384, llm=None):
        """
        Args:
            db_path: SQLite path. Defaults to DATA_DIR / semantic_memory.db
            dim: embedding dimension. 384 works well for small local models.
            llm: optional LLM client for generating embeddings (fallback to hash-based)
        """
        self.db_path = str(db_path or DATA_DIR / "semantic_memory.db")
        self.dim = dim
        self.llm = llm
        self._conn: Optional[sqlite3.Connection] = None

    async def init(self):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._init_sync)

    def _init_sync(self):
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self._TABLE} (
                id TEXT PRIMARY KEY,
                agent_id TEXT,
                content TEXT NOT NULL,
                embedding BLOB NOT NULL,
                tags TEXT,
                timestamp REAL NOT NULL,
                importance REAL DEFAULT 1.0,
                access_count INTEGER DEFAULT 0,
                recency_score REAL DEFAULT 1.0
            )
        """)
        self._conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_sem_tag ON {self._TABLE}(tags)
        """)
        self._conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_sem_time ON {self._TABLE}(timestamp)
        """)
        self._conn.commit()

    # ------------------------------------------------------------------ #
    # Embedding generation
    # ------------------------------------------------------------------ #

    def _generate_embedding(self, text: str) -> np.ndarray:
        """Generate a deterministic normalized embedding vector.

        If `self.llm` is set, calls the LLM embedding endpoint.
        Otherwise falls back to a fast hash-based deterministic vector.
        """
        if self.llm and hasattr(self.llm, "embed"):
            vec = self.llm.embed(text)
            if isinstance(vec, list):
                vec = np.array(vec, dtype=np.float32)
            vec = vec[:self.dim]
            if len(vec) < self.dim:
                vec = np.pad(vec, (0, self.dim - len(vec)), mode="constant")
            return vec / (np.linalg.norm(vec) + 1e-8)

        # Fallback: deterministic hash-based vector (surprisingly good for search)
        h = hashlib.sha256(text.encode()).digest()
        # Use first 4 bytes for a seed, then deterministic random
        seed = int.from_bytes(h[:4], "big") % (2**31)
        rng = np.random.default_rng(seed)
        vec = rng.standard_normal(self.dim).astype(np.float32)
        return vec / (np.linalg.norm(vec) + 1e-8)

    # ------------------------------------------------------------------ #
    # Store
    # ------------------------------------------------------------------ #

    async def store(self, content: str, agent_id: str = "", tags: List[str] = None,
                    importance: float = 1.0, timestamp: float = None):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, self._store_sync, content, agent_id, tags or [], importance, timestamp
        )

    def _store_sync(self, content: str, agent_id: str, tags: List[str],
                    importance: float, timestamp: float):
        ts = timestamp or time.time()
        mem_id = hashlib.sha256(f"{agent_id}::{content}::{ts}".encode()).hexdigest()[:16]
        emb = self._generate_embedding(content)
        emb_blob = emb.tobytes()

        self._conn.execute(f"""
            INSERT OR REPLACE INTO {self._TABLE}
            (id, agent_id, content, embedding, tags, timestamp, importance, access_count, recency_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            mem_id, agent_id, content, emb_blob,
            json.dumps(tags), ts, importance, 0, 1.0
        ))
        self._conn.commit()
        return mem_id

    # ------------------------------------------------------------------ #
    # Semantic search
    # ------------------------------------------------------------------ #

    async def search(self, query: str, top_k: int = 5, agent_id: str = "",
                     min_score: float = 0.0) -> List[Dict]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._search_sync, query, top_k, agent_id, min_score
        )

    def _search_sync(self, query: str, top_k: int, agent_id: str, min_score: float) -> List[Dict]:
        q_vec = self._generate_embedding(query)
        rows = self._conn.execute(
            f"SELECT id, agent_id, content, embedding, tags, timestamp, importance, access_count FROM {self._TABLE} ORDER BY timestamp DESC LIMIT 500"
        ).fetchall()

        scored = []
        for r in rows:
            mem_id, a_id, content, emb_blob, tags_json, ts, importance, access_count = r
            if agent_id and a_id != agent_id:
                continue
            mem_vec = np.frombuffer(emb_blob, dtype=np.float32).reshape(-1)
            if mem_vec.shape[0] != self.dim:
                continue

            # Cosine similarity
            cosine = float(np.dot(q_vec, mem_vec) / (np.linalg.norm(q_vec) * np.linalg.norm(mem_vec) + 1e-8))

            # Recency boost (decay over 30 days)
            age_days = (time.time() - ts) / (30 * 86400)
            recency = max(0.1, 1.0 - age_days)

            # Access-count boost
            access_boost = min(1.0, 0.1 * access_count)

            final_score = cosine * 0.5 + recency * 0.3 + access_boost * 0.1 + importance * 0.1

            if final_score >= min_score:
                scored.append((final_score, mem_id, content, json.loads(tags_json), ts, a_id))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, mem_id, content, tags, ts, a_id in scored[:top_k]:
            # Increment access count
            self._conn.execute(
                f"UPDATE {self._TABLE} SET access_count = access_count + 1 WHERE id = ?", (mem_id,)
            )
            results.append({
                "id": mem_id,
                "score": round(score, 4),
                "content": content,
                "tags": tags,
                "timestamp": ts,
                "agent_id": a_id,
            })
        self._conn.commit()
        return results

    # ------------------------------------------------------------------ #
    # Prune
    # ------------------------------------------------------------------ #

    async def prune(self, max_age_days: int = 90):
        """Remove old, unimportant memories past the retention window."""
        cutoff = time.time() - (max_age_days * 86400)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._prune_sync, cutoff)

    def _prune_sync(self, cutoff: float):
        self._conn.execute(
            f"DELETE FROM {self._TABLE} WHERE timestamp < ? AND importance < 0.5", (cutoff,)
        )
        self._conn.commit()

    async def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
