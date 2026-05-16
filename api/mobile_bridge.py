#!/usr/bin/env python3
"""Hermes Mobile Bridge — REST API for React Native app integration.

Endpoints:
    POST /api/v1/mission    → Submit a new mission
    GET  /api/v1/status     → DSL daemon health
    GET  /api/v1/missions   → List recent missions (from bus DB)
    POST /api/v1/chat       → Chat-style mission (streaming stub)
"""

import asyncio, json, time
from pathlib import Path
from typing import Optional

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

from sovereign_swarm.dsl import DeterministicSovereignLoop
from sovereign_swarm.dsl.mission import Mission
from sovereign_swarm.infra.bus import SwarmBus
from sovereign_swarm.config import DATA_DIR

app = FastAPI(title="Hermes Mobile Bridge", version="1.0.0")

_loop: Optional[DeterministicSovereignLoop] = None
_bus: Optional[SwarmBus] = None


class MissionRequest(BaseModel):
    goal: str
    domain: Optional[str] = None
    max_tokens: Optional[int] = 100000
    max_time_sec: Optional[int] = 300
    max_cost_usd: Optional[float] = 5.0
    allow_self_modify: Optional[bool] = False
    user_id: Optional[str] = "anonymous"


class ChatMessage(BaseModel):
    message: str
    user_id: Optional[str] = "anonymous"
    history: Optional[list] = []


@app.on_event("startup")
async def startup():
    global _loop, _bus
    _bus = SwarmBus(DATA_DIR / "mobile_bus.db")
    await _bus.init()
    _loop = DeterministicSovereignLoop(bus=_bus)
    print("[Mobile Bridge] Started")


@app.on_event("shutdown")
async def shutdown():
    if _bus:
        await _bus.close()
    print("[Mobile Bridge] Stopped")


@app.get("/api/v1/status")
async def status():
    return {
        "ok": True,
        "service": "hermes-mobile-bridge",
        "dsl_ready": _loop is not None,
        "timestamp": time.time(),
    }


@app.post("/api/v1/mission")
async def create_mission(req: MissionRequest):
    if not _loop:
        raise HTTPException(status_code=503, detail="DSL not initialized")
    result = await _loop.run(req.goal, requester_id=req.user_id)
    return {
        "ok": result.ok,
        "state": result.state,
        "data": result.data,
        "checkpoint_id": result.checkpoint_id,
        "error_code": result.error_code,
        "error_message": result.error_message,
        "elapsed_sec": result.elapsed_sec,
    }


@app.get("/api/v1/missions")
async def list_missions(limit: int = 20):
    if not _bus:
        raise HTTPException(status_code=503, detail="Bus not initialized")
    rows = await _bus.history("dsl.state_change", limit=limit)
    return {"missions": rows, "count": len(rows)}


@app.post("/api/v1/chat")
async def chat(req: ChatMessage):
    if not _loop:
        raise HTTPException(status_code=503, detail="DSL not initialized")
    goal = req.message
    result = await _loop.run(goal, requester_id=req.user_id)
    return {
        "reply": result.data.get("outputs", {}).get("step_000", "[No output]"),
        "ok": result.ok,
        "state": result.state,
        "mission_id": result.data.get("mission_id", "") if result.data else "",
    }


def main():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
