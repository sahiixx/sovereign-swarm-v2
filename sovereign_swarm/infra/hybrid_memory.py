"""Hybrid vector memory — SQLite fallback with optional ChromaDB."""
from ..config import *

class HybridMemory:
    def __init__(self, db_path: Path, vector_db_path: Optional[Path] = None):
        self.db_path = Path(db_path)
        self.vector_db_path = vector_db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._chroma = None

    async def init(self):
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.execute("CREATE TABLE IF NOT EXISTS memories (id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT UNIQUE, value TEXT, tags TEXT, timestamp REAL)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_key ON memories(key)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_tags ON memories(tags)")
        self._conn.commit()
        # Optional ChromaDB
        if self.vector_db_path:
            try:
                import chromadb
                self._chroma = chromadb.PersistentClient(path=str(self.vector_db_path))
                self._col = self._chroma.get_or_create_collection(name="swarm_mem")
            except ImportError:
                pass

    async def store(self, key: str, value: Any, tags: str = "", vector: Optional[List[float]] = None):
        ts = time.time()
        self._conn.execute(
            "INSERT OR REPLACE INTO memories (key, value, tags, timestamp) VALUES (?, ?, ?, ?)",
            (key, json.dumps(value), tags, ts)
        )
        self._conn.commit()
        if self._chroma and vector:
            try:
                self._col.add(ids=[key], embeddings=[vector], metadatas=[{"tags": tags, "ts": ts}])
            except Exception:
                pass

    async def search(self, query: str, limit: int = 10, vector: Optional[List[float]] = None) -> List[Dict]:
        # Text search fallback
        cur = self._conn.execute(
            "SELECT key, value, tags, timestamp FROM memories WHERE key LIKE ? OR value LIKE ? OR tags LIKE ? ORDER BY timestamp DESC LIMIT ?",
            (f"%{query}%", f"%{query}%", f"%{query}%", limit)
        )
        text_results = [{"key": r[0], "value": json.loads(r[1]), "tags": r[2], "timestamp": r[3]} for r in cur.fetchall()]

        # Vector search if available
        if self._chroma and vector:
            try:
                chroma_results = self._col.query(query_embeddings=[vector], n_results=min(limit, 10))
                for ids, distances in zip(chroma_results.get("ids", []), chroma_results.get("distances", [])):
                    for mem_id, dist in zip(ids, distances):
                        if mem_id not in {r["key"] for r in text_results}:
                            cur = self._conn.execute("SELECT key, value, tags, timestamp FROM memories WHERE key = ?", (mem_id,))
                            row = cur.fetchone()
                            if row:
                                text_results.append({"key": row[0], "value": json.loads(row[1]), "tags": row[2], "timestamp": row[3], "vector_dist": round(dist, 4)})
            except Exception:
                pass
        return text_results[:limit]

    async def close(self):
        if self._conn:
            self._conn.close(); self._conn = None

    def count(self) -> int:
        if not self._conn: return 0
        return self._conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
