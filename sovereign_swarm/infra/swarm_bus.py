"""
Sovereign Swarm — Async Message Bus (P2P)
No central broker. Every agent is a peer. Messages persisted for audit.
Enhanced with gossip propagation and heartbeat mesh.
"""
import asyncio
import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Callable, Any, Set
from enum import Enum

class MessageType(Enum):
    BROADCAST = "broadcast"
    DIRECT = "direct"
    SYSTEM = "system"
    ACTION = "action"
    MEMORY = "memory"
    EVOLUTION = "evolution"
    KILL = "kill"
    HEARTBEAT = "heartbeat"
    GOSSIP = "gossip"
    REALTIME = "realtime"
    REVIEW_REQUEST = "review_request"
    REVIEW_VERDICT = "review_verdict"

@dataclass
class Message:
    id: str
    sender: str
    recipient: Optional[str]
    type: MessageType
    payload: Dict[str, Any]
    timestamp: float
    priority: int = 0
    ttl: int = 5

class SwarmBus:
    def __init__(self, db_path: str = "swarm_memory.db"):
        self.db_path = db_path
        self.subscribers: Dict[str, Callable[[Message], Any]] = {}
        self._lock = asyncio.Lock()
        self._running = True
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._gossip_seen: Set[str] = set()
        self._init_db()
        asyncio.create_task(self._queue_processor())
    
    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            sender TEXT,
            recipient TEXT,
            type TEXT,
            payload TEXT,
            timestamp REAL,
            priority INTEGER,
            ttl INTEGER
        )""")
        c.execute("""CREATE INDEX IF NOT EXISTS idx_msg_time ON messages(timestamp)""")
        c.execute("""CREATE INDEX IF NOT EXISTS idx_msg_type ON messages(type)""")
        conn.commit()
        conn.close()
    
    async def register(self, agent_id: str, handler: Callable[[Message], Any]):
        async with self._lock:
            self.subscribers[agent_id] = handler
            print(f"[BUS] Agent '{agent_id}' registered")
    
    async def unregister(self, agent_id: str):
        async with self._lock:
            self.subscribers.pop(agent_id, None)
            print(f"[BUS] Agent '{agent_id}' unregistered")
    
    async def send(self, msg: Message):
        if not self._running:
            return
        
        # Gossip deduplication
        if msg.type == MessageType.GOSSIP:
            if msg.id in self._gossip_seen:
                return
            self._gossip_seen.add(msg.id)
            if len(self._gossip_seen) > 10000:
                self._gossip_seen = set(list(self._gossip_seen)[-5000:])
        
        await self._message_queue.put(msg)
    
    async def _queue_processor(self):
        while self._running:
            try:
                msg = await asyncio.wait_for(self._message_queue.get(), timeout=1.0)
                await self._persist_and_route(msg)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f"[BUS PROCESSOR ERROR] {e}")
    
    async def _persist_and_route(self, msg: Message):
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("""INSERT OR IGNORE INTO messages VALUES (?,?,?,?,?,?,?,?)""",
                (msg.id, msg.sender, msg.recipient, msg.type.value, 
                 json.dumps(msg.payload), msg.timestamp, msg.priority, msg.ttl))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[BUS PERSIST ERROR] {e}")
        
        async with self._lock:
            if msg.recipient is None:
                for agent_id, handler in list(self.subscribers.items()):
                    if agent_id != msg.sender:
                        try:
                            if asyncio.iscoroutinefunction(handler):
                                asyncio.create_task(handler(msg))
                            else:
                                handler(msg)
                        except Exception as e:
                            print(f"[BUS ERROR] {agent_id}: {e}")
            else:
                handler = self.subscribers.get(msg.recipient)
                if handler:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            asyncio.create_task(handler(msg))
                        else:
                            handler(msg)
                    except Exception as e:
                        print(f"[BUS ERROR] {msg.recipient}: {e}")
    
    async def broadcast_system(self, payload: Dict[str, Any], priority: int = 10):
        msg = Message(
            id=str(uuid.uuid4()),
            sender="system",
            recipient=None,
            type=MessageType.SYSTEM,
            payload=payload,
            timestamp=time.time(),
            priority=priority
        )
        await self.send(msg)
    
    async def gossip(self, agent_id: str, payload: Dict[str, Any], ttl: int = 5):
        msg = Message(
            id=str(uuid.uuid4()),
            sender=agent_id,
            recipient=None,
            type=MessageType.GOSSIP,
            payload=payload,
            timestamp=time.time(),
            ttl=ttl
        )
        await self.send(msg)
    
    def shutdown(self):
        self._running = False
        print("[BUS] Shutdown signal sent")
    
    def get_stats(self) -> Dict[str, Any]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM messages")
        total = c.fetchone()[0]
        c.execute("SELECT type, COUNT(*) FROM messages GROUP BY type")
        by_type = {r[0]: r[1] for r in c.fetchall()}
        conn.close()
        return {"total_messages": total, "by_type": by_type, "subscribers": len(self.subscribers)}
