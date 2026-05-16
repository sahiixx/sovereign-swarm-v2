"""PersistentAgentState — SQLite-backed agent identity that survives restarts.

Every agent stores its full identity, task history, skill inventory, and current
objective. On init, if the agent_id exists in the DB, state is restored.
If not, a new record is created. On shutdown or heartbeat, state is synced.

Usage:
    state = PersistentAgentState(agent_id="alpha_1", role="executor")
    state.restore()               # if alpha_1 exists, loads previous state
    state.update_objective("audit smart contract")
    state.add_task_result({"task": "scan", "result": "clean", "score": 0.97})
    state.sync()
"""

from ..config import *
from dataclasses import dataclass, field, asdict
import json, sqlite3, time, hashlib


@dataclass
class AgentIdentity:
    agent_id: str
    role: str
    status: str = "idle"
    objective: str = ""
    created_at: float = field(default_factory=time.time)
    last_active_at: float = field(default_factory=time.time)
    task_count: int = 0
    success_rate: float = 1.0
    skills: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)


class PersistentAgentState:
    """SQLite-backed persistent agent identity and resumeable state."""

    TABLE = "agent_states"

    def __init__(self, agent_id: str, role: str, db_path: Optional[Path] = None):
        self.agent_id = agent_id
        self.conn: Optional[sqlite3.Connection] = None

        self.db_path = db_path or DATA_DIR / "agent_states.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_db()
        self._identity = self.restore() or AgentIdentity(agent_id=agent_id, role=role)

    # ------------------------------------------------------------------ #
    # DB layer
    # ------------------------------------------------------------------ #

    def _init_db(self):
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.TABLE} (
                agent_id TEXT PRIMARY KEY,
                role TEXT NOT NULL,
                status TEXT DEFAULT 'idle',
                objective TEXT DEFAULT '',
                created_at REAL NOT NULL,
                last_active_at REAL NOT NULL,
                task_count INTEGER DEFAULT 0,
                success_rate REAL DEFAULT 1.0,
                skills TEXT DEFAULT '[]',
                tags TEXT DEFAULT '[]',
                task_history TEXT DEFAULT '[]',
                checkpoint_blob TEXT DEFAULT '{{}}'
            )
        """)
        self.conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.TABLE}_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                task TEXT NOT NULL,
                result TEXT,
                score REAL,
                timestamp REAL NOT NULL
            )
        """)
        self.conn.commit()

    # ------------------------------------------------------------------ #
    # Restore / load
    # ------------------------------------------------------------------ #

    def restore(self) -> Optional[AgentIdentity]:
        row = self.conn.execute(
            f"SELECT * FROM {self.TABLE} WHERE agent_id = ?", (self.agent_id,)
        ).fetchone()

        if not row:
            return None

        col_names = [desc[0] for desc in row.__class__.__name__ == "sqlite3.Row" and row.__class__ or []]
        # Use cursor description instead
        cur = self.conn.execute(f"PRAGMA table_info({self.TABLE})")
        col_names = [c[1] for c in cur.fetchall()]

        d = dict(zip(col_names, row))
        d["skills"] = json.loads(d.get("skills", "[]"))
        d["tags"] = json.loads(d.get("tags", "[]"))

        return AgentIdentity(
            agent_id=d["agent_id"],
            role=d["role"],
            status=d["status"],
            objective=d["objective"],
            created_at=d["created_at"],
            last_active_at=d["last_active_at"],
            task_count=d["task_count"],
            success_rate=d["success_rate"],
            skills=d["skills"],
            tags=d["tags"],
        )

    # ------------------------------------------------------------------ #
    # Update
    # ------------------------------------------------------------------ #

    def update_objective(self, objective: str):
        self._identity.objective = objective
        self._identity.last_active_at = time.time()

    def set_status(self, status: str):
        self._identity.status = status
        self._identity.last_active_at = time.time()

    def add_skill(self, skill: str):
        if skill not in self._identity.skills:
            self._identity.skills.append(skill)

    def add_tag(self, tag: str):
        if tag not in self._identity.tags:
            self._identity.tags.append(tag)

    # ------------------------------------------------------------------ #
    # Task history
    # ------------------------------------------------------------------ #

    def add_task_result(self, task: str, result: Dict, score: float = 1.0):
        self.conn.execute(
            f"INSERT INTO {self.TABLE}_tasks (agent_id, task, result, score, timestamp) VALUES (?, ?, ?, ?, ?)",
            (self.agent_id, task, json.dumps(result), score, time.time())
        )
        self._identity.task_count += 1
        # Recalculate success rate
        cur = self.conn.execute(
            f"SELECT AVG(score) FROM {self.TABLE}_tasks WHERE agent_id = ?", (self.agent_id,)
        )
        row = cur.fetchone()
        self._identity.success_rate = float(row[0]) if row and row[0] is not None else 1.0
        self._identity.last_active_at = time.time()
        self.sync()

    def get_task_history(self, limit: int = 20) -> List[Dict]:
        rows = self.conn.execute(
            f"SELECT task, result, score, timestamp FROM {self.TABLE}_tasks WHERE agent_id = ? ORDER BY timestamp DESC LIMIT ?",
            (self.agent_id, limit)
        ).fetchall()
        return [
            {"task": r[0], "result": json.loads(r[1]), "score": r[2], "timestamp": r[3]}
            for r in rows
        ]

    # ------------------------------------------------------------------ #
    # Sync / persist
    # ------------------------------------------------------------------ #

    def sync(self):
        """Write current identity to DB. Call after every significant state change."""
        identity = self._identity
        self.conn.execute(f"""
            INSERT INTO {self.TABLE} (agent_id, role, status, objective, created_at, last_active_at,
                                      task_count, success_rate, skills, tags, checkpoint_blob)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(agent_id) DO UPDATE SET
                role=excluded.role,
                status=excluded.status,
                objective=excluded.objective,
                last_active_at=excluded.last_active_at,
                task_count=excluded.task_count,
                success_rate=excluded.success_rate,
                skills=excluded.skills,
                tags=excluded.tags,
                checkpoint_blob=excluded.checkpoint_blob
        """, (
            identity.agent_id, identity.role, identity.status, identity.objective,
            identity.created_at, identity.last_active_at,
            identity.task_count, identity.success_rate,
            json.dumps(identity.skills), json.dumps(identity.tags),
            json.dumps(asdict(identity))
        ))
        self.conn.commit()

    # ------------------------------------------------------------------ #
    # Checkpoint / resume
    # ------------------------------------------------------------------ #

    def checkpoint(self) -> Dict:
        return {
            "agent_id": self._identity.agent_id,
            "role": self._identity.role,
            "status": self._identity.status,
            "objective": self._identity.objective,
            "task_count": self._identity.task_count,
            "success_rate": self._identity.success_rate,
            "skills": self._identity.skills,
            "tags": self._identity.tags,
            "timestamp": time.time(),
        }

    # ------------------------------------------------------------------ #
    # Properties
    # ------------------------------------------------------------------ #

    @property
    def is_new(self) -> bool:
        return self._identity.task_count == 0

    @property
    def identity(self) -> AgentIdentity:
        return self._identity

    def close(self):
        self.sync()
        if self.conn:
            self.conn.close()
            self.conn = None

    def __repr__(self):
        return f"<PersistentAgentState {self.agent_id} role={self._identity.role} tasks={self._identity.task_count}>"
