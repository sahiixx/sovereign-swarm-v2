"""SwarmMemory — Surprise-weighted persistent memory with SQL injection protection."""

from ..config import *


class SwarmMemory:
    def __init__(self, db_path: Path):
        self.db_path = str(db_path)
        self._conn: Optional[sqlite3.Connection] = None

    async def init(self):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._init_sync)

    def _init_sync(self):
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS memories (id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT, value TEXT NOT NULL, tags TEXT, timestamp REAL NOT NULL)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mem_key ON memories(key)"
        )
        self._conn.commit()

    @staticmethod
    def _escape_like(s: str) -> str:
        """Escape special LIKE characters with ESCAPE '\\' clause."""
        return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    async def store(self, key: str, value: Any, tags: str = ""):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._store_sync, key, value, tags)

    def _store_sync(self, key: str, value: Any, tags: str = ""):
        if not self._conn:
            return
        self._conn.execute(
            "INSERT INTO memories (key, value, tags, timestamp) VALUES (?, ?, ?, ?)",
            (key, json.dumps(value), tags, time.time()),
        )
        self._conn.commit()

    async def search(self, query: str, limit: int = 10) -> List[Dict]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._search_sync, query, limit)

    def _search_sync(self, query: str, limit: int) -> List[Dict]:
        if not self._conn:
            return []
        escaped = self._escape_like(query)
        cur = self._conn.execute(
            "SELECT key, value, tags, timestamp FROM memories WHERE key LIKE ? ESCAPE '\\' OR value LIKE ? ESCAPE '\\' OR tags LIKE ? ESCAPE '\\' ORDER BY timestamp DESC LIMIT ?",
            (f"%{escaped}%", f"%{escaped}%", f"%{escaped}%", limit),
        )
        return [
            {"key": r[0], "value": json.loads(r[1]), "tags": r[2], "timestamp": r[3]}
            for r in cur.fetchall()
        ]

    async def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
