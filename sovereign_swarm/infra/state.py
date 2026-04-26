"""StateManager — persistent agent/ecosystem state with SQLite atomicity."""

from ..config import *


class StateManager:
    """Persistent key-value state with async I/O, snapshot, and rollback.

    All SQLite operations are wrapped in run_in_executor for async safety.
    LIKE queries use ESCAPE clause to prevent SQL injection.
    """

    def __init__(self, db_path: Path):
        self.db_path = str(db_path)
        self._conn: Optional[sqlite3.Connection] = None

    async def init(self):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._init_sync)

    def _init_sync(self):
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated REAL NOT NULL)"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, snapshot TEXT NOT NULL, created REAL NOT NULL)"
        )
        self._conn.commit()

    async def set(self, key: str, value: Any) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._set_sync, key, value)

    def _set_sync(self, key: str, value: Any) -> None:
        if not self._conn:
            return
        self._conn.execute(
            "INSERT OR REPLACE INTO state (key, value, updated) VALUES (?, ?, ?)",
            (key, json.dumps(value), time.time()),
        )
        self._conn.commit()

    async def get(self, key: str, default: Any = None) -> Any:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._get_sync, key, default)

    def _get_sync(self, key: str, default: Any = None) -> Any:
        if not self._conn:
            return default
        cur = self._conn.execute("SELECT value FROM state WHERE key = ?", (key,))
        row = cur.fetchone()
        if row:
            return json.loads(row[0])
        return default

    @staticmethod
    def _escape_like(s: str) -> str:
        """Escape special LIKE characters with ESCAPE '\\' clause."""
        return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    async def search(self, query: str, limit: int = 50) -> List[Dict]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._search_sync, query, limit)

    def _search_sync(self, query: str, limit: int) -> List[Dict]:
        if not self._conn:
            return []
        escaped = self._escape_like(query)
        cur = self._conn.execute(
            "SELECT key, value, updated FROM state WHERE key LIKE ? ESCAPE '\\' ORDER BY updated DESC LIMIT ?",
            (f"%{escaped}%", limit),
        )
        return [{"key": r[0], "value": json.loads(r[1]), "updated": r[2]} for r in cur.fetchall()]

    async def snapshot(self, name: str) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._snapshot_sync, name)

    def _snapshot_sync(self, name: str) -> None:
        if not self._conn:
            return
        cur = self._conn.execute("SELECT key, value FROM state")
        rows = cur.fetchall()
        snap = {r[0]: json.loads(r[1]) for r in rows}
        self._conn.execute(
            "INSERT INTO snapshots (name, snapshot, created) VALUES (?, ?, ?)",
            (name, json.dumps(snap), time.time()),
        )
        self._conn.commit()

    async def list_snapshots(self) -> List[Dict]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._list_snapshots_sync)

    def _list_snapshots_sync(self) -> List[Dict]:
        if not self._conn:
            return []
        cur = self._conn.execute(
            "SELECT name, created FROM snapshots ORDER BY created DESC LIMIT 20"
        )
        return [{"name": r[0], "created": r[1]} for r in cur.fetchall()]

    async def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
