from ..config import *

class SwarmBus:
    def __init__(self, db_path: Path):
        self.db_path = str(db_path)
        self._subs: Dict[str, List[Callable]] = {}
        self._lock = asyncio.Lock()
        self._conn: Optional[sqlite3.Connection] = None

    async def init(self):
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("CREATE TABLE IF NOT EXISTS bus_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT NOT NULL, payload TEXT NOT NULL, timestamp REAL NOT NULL)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_topic ON bus_messages(topic)")
        self._conn.commit()

    async def publish(self, topic: str, payload: dict):
        ts = time.time()
        async with self._lock:
            if self._conn:
                self._conn.execute("INSERT INTO bus_messages (topic, payload, timestamp) VALUES (?, ?, ?)", (topic, json.dumps(payload), ts))
                self._conn.commit()
        for cb in self._subs.get(topic, []):
            try:
                if asyncio.iscoroutinefunction(cb):
                    task = asyncio.create_task(cb(payload))
                    task.add_done_callback(self._on_callback_done)
                else:
                    cb(payload)
            except Exception:
                logger.exception("Bus callback error")

    @staticmethod
    def _on_callback_done(task: asyncio.Task):
        if task.cancelled():
            return
        if exc := task.exception():
            logger.exception("Bus async callback error: %s", exc)

    async def subscribe(self, topic: str, callback: Callable):
        async with self._lock:
            self._subs.setdefault(topic, []).append(callback)

    async def history(self, topic: str, limit: int = 100) -> List[dict]:
        async with self._lock:
            cur = self._conn.execute("SELECT payload FROM bus_messages WHERE topic = ? ORDER BY timestamp DESC LIMIT ?", (topic, limit))
            rows = cur.fetchall()
        return [json.loads(r[0]) for r in rows]

    async def count(self) -> int:
        async with self._lock:
            cur = self._conn.execute("SELECT COUNT(*) FROM bus_messages")
            return cur.fetchone()[0]

    async def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None


