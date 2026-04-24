from ..config import *

class SwarmMemory:
    def __init__(self, db_path: Path):
        self.db_path = str(db_path)
        self._conn: Optional[sqlite3.Connection] = None

    async def init(self):
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("CREATE TABLE IF NOT EXISTS memories (id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT, value TEXT NOT NULL, tags TEXT, timestamp REAL NOT NULL)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_key ON memories(key)")
        self._conn.commit()

    async def store(self, key: str, value: Any, tags: str = ""):
        self._conn.execute("INSERT INTO memories (key, value, tags, timestamp) VALUES (?, ?, ?, ?)", (key, json.dumps(value), tags, time.time()))
        self._conn.commit()

    async def search(self, query: str, limit: int = 10) -> List[Dict]:
        cur = self._conn.execute("SELECT key, value, tags, timestamp FROM memories WHERE key LIKE ? OR value LIKE ? OR tags LIKE ? ORDER BY timestamp DESC LIMIT ?", (f"%{query}%", f"%{query}%", f"%{query}%", limit))
        return [{"key": r[0], "value": json.loads(r[1]), "tags": r[2], "timestamp": r[3]} for r in cur.fetchall()]

    async def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None


