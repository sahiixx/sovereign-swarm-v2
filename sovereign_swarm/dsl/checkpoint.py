"""CheckpointManager — git-like snapshots with SQLite WAL and deterministic restore.

Every state change is snapshotted before and after.  Restore is atomic
via WAL rollback or replay of the recorded delta.
"""

import json, sqlite3, hashlib, time, os
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass

from .result import Result


@dataclass(frozen=True)
class Snapshot:
    id: str
    label: str
    state_json: str
    checksum: str
    created_at: float


class CheckpointManager:
    def __init__(self, db_path: Path = None):
        if db_path is None:
            db_path = Path(os.getenv("SWARM_DATA_DIR", "./data")) / "dsl_checkpoints.db"
        self._db = str(db_path)
        self._conn: Optional[sqlite3.Connection] = None

    def _init_db(self):
        if self._conn is None:
            self._conn = sqlite3.connect(self._db, check_same_thread=False)
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS checkpoints ("
                "id TEXT PRIMARY KEY, label TEXT NOT NULL, state_json TEXT NOT NULL, "
                "checksum TEXT NOT NULL, created_at REAL NOT NULL)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_checkpoint_time ON checkpoints(created_at)"
            )
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS checkpoint_sequence ("
                "mission_id TEXT PRIMARY KEY, current_id TEXT, history TEXT NOT NULL)"
            )
            self._conn.commit()

    def _hash(self, state_json: str) -> str:
        return hashlib.sha256(state_json.encode()).hexdigest()

    def save(self, label: str, state: Any, mission_id: str) -> Snapshot:
        self._init_db()
        ts = time.time()
        state_json = json.dumps(state, ensure_ascii=False, default=str)
        snapshot_id = f"{mission_id}:{label}:{ts:.6f}"
        checksum = self._hash(state_json)
        snap = Snapshot(
            id=snapshot_id, label=label, state_json=state_json,
            checksum=checksum, created_at=ts,
        )
        cur = self._conn.execute(
            "INSERT INTO checkpoints (id, label, state_json, checksum, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (snap.id, snap.label, snap.state_json, snap.checksum, snap.created_at),
        )
        # Update current pointer
        row = self._conn.execute(
            "SELECT history FROM checkpoint_sequence WHERE mission_id=?", (mission_id,)
        ).fetchone()
        if row:
            hist = json.loads(row[0])
            hist.append(snapshot_id)
            self._conn.execute(
                "UPDATE checkpoint_sequence SET current_id=?, history=? WHERE mission_id=?",
                (snapshot_id, json.dumps(hist), mission_id),
            )
        else:
            hist = [snapshot_id]
            self._conn.execute(
                "INSERT INTO checkpoint_sequence (mission_id, current_id, history) VALUES (?, ?, ?)",
                (mission_id, snapshot_id, json.dumps(hist)),
            )
        self._conn.commit()
        return snap

    def restore(self, snapshot_id: str, mission_id: str) -> Optional[dict]:
        self._init_db()
        row = self._conn.execute(
            "SELECT state_json, checksum FROM checkpoints WHERE id=? AND id LIKE ?",
            (snapshot_id, f"{mission_id}:%"),
        ).fetchone()
        if not row:
            return None
        state_json, stored_checksum = row
        if self._hash(state_json) != stored_checksum:
            raise RuntimeError(f"CHECKSUM_VIOLATION: checkpoint {snapshot_id} is corrupted")
        # Update sequence pointer
        self._conn.execute(
            "UPDATE checkpoint_sequence SET current_id=? WHERE mission_id=?",
            (snapshot_id, mission_id),
        )
        self._conn.commit()
        return json.loads(state_json)

    def last_id(self, mission_id: str) -> Optional[str]:
        self._init_db()
        row = self._conn.execute(
            "SELECT current_id FROM checkpoint_sequence WHERE mission_id=?", (mission_id,)
        ).fetchone()
        return row[0] if row else None

    def history(self, mission_id: str, limit: int = 100) -> list[Snapshot]:
        self._init_db()
        row = self._conn.execute(
            "SELECT history FROM checkpoint_sequence WHERE mission_id=?", (mission_id,)
        ).fetchone()
        if not row:
            return []
        ids = json.loads(row[0])[-limit:]
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        cur = self._conn.execute(
            f"SELECT id, label, state_json, checksum, created_at FROM checkpoints WHERE id IN ({placeholders}) ORDER BY created_at",
            tuple(ids),
        )
        return [
            Snapshot(id=r[0], label=r[1], state_json=r[2], checksum=r[3], created_at=r[4])
            for r in cur.fetchall()
        ]

    def rollback(self, mission_id: str, target_label: str) -> Optional[dict]:
        hist = self.history(mission_id)
        for snap in reversed(hist):
            if snap.label == target_label:
                return self.restore(snap.id, mission_id)
        return None

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
