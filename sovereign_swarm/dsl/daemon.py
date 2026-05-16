#!/usr/bin/env python3
"""DSL Daemon — systemd-ready mission runner with HTTP API."""

import asyncio, json, signal, sys, time
from pathlib import Path
from typing import Optional

from sovereign_swarm.dsl import DeterministicSovereignLoop
from sovereign_swarm.infra.bus import SwarmBus
from sovereign_swarm.protocols.hermes_v2 import HermesV2
from sovereign_swarm.protocols.hermes_wiring import HermesWiring
from sovereign_swarm.safety import SafetyCouncil
from sovereign_swarm.audit import AuditTrail
from sovereign_swarm.config import DATA_DIR


class DSLDaemon:
    def __init__(self, port: int = 18800, hermes_port: int = 18797):
        self.port = port
        self.hermes_port = hermes_port
        self._shutdown_event = asyncio.Event()
        self.bus = None
        self.hermes = None
        self.wiring = None
        self.loop = None
        self._server = None

    async def start(self):
        self.bus = SwarmBus(DATA_DIR / "dsl_bus.db")
        await self.bus.init()

        safety = SafetyCouncil()
        audit = AuditTrail(DATA_DIR)
        self.hermes = HermesV2(safety=safety, audit=audit, bus=self.bus)
        await self.hermes.start()

        self.loop = DeterministicSovereignLoop(bus=self.bus, on_state_change=self._on_state_change)
        self.wiring = HermesWiring(self.hermes, bus=self.bus)
        self.wiring.register_dsl_loop(self.loop)
        self.wiring.wire_all()

        await self.bus.subscribe("dsl.mission", self._handle_mission)
        await self.bus.subscribe("dsl.status", self._handle_status)

        await self._start_http()
        print(f"[DSL Daemon] Running on port {self.port}")
        await self._shutdown_event.wait()

    async def stop(self):
        print("[DSL Daemon] Shutting down...")
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        if self.hermes:
            await self.hermes.stop()
        if self.bus:
            await self.bus.close()
        self._shutdown_event.set()

    async def _start_http(self):
        try:
            from aiohttp import web
        except ImportError:
            return
        app = web.Application()
        app.router.add_get("/health", self._http_health)
        app.router.add_post("/mission", self._http_mission)
        app.router.add_get("/status", self._http_status)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", self.port)
        await site.start()

    async def _http_health(self, request):
        from aiohttp import web
        return web.json_response({"ok": True, "daemon": "dsl", "hermes_running": self.hermes._running if self.hermes else False, "time": time.time()})

    async def _http_mission(self, request):
        from aiohttp import web
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
        goal = body.get("goal", "")
        requester = body.get("requester_id", "http")
        if not goal:
            return web.json_response({"ok": False, "error": "Missing goal"}, status=400)
        result = await self.loop.run(goal, requester_id=requester)
        return web.json_response(result.to_dict(), default=str)

    async def _http_status(self, request):
        from aiohttp import web
        return web.json_response({"hermes": self.hermes.status() if self.hermes else {}, "dsl_loop_present": self.loop is not None}, default=str)

    async def _handle_mission(self, payload):
        goal = payload.get("goal", "")
        requester = payload.get("requester_id", "bus")
        if goal and self.loop:
            result = await self.loop.run(goal, requester_id=requester)
            await self.bus.publish("dsl.result", {"mission_id": payload.get("mission_id", ""), "ok": result.ok, "state": result.state, "checkpoint_id": result.checkpoint_id})

    async def _handle_status(self, payload):
        await self.bus.publish("dsl.status.reply", {"hermes_running": self.hermes._running if self.hermes else False, "dsl_present": self.loop is not None})

    def _on_state_change(self, mission_id: str, state: str, meta: dict):
        print(f"[DSL] {mission_id} -> {state}")


def main():
    daemon = DSLDaemon()
    def handle_sig(signum, frame):
        asyncio.create_task(daemon.stop())
    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)
    asyncio.run(daemon.start())


if __name__ == "__main__":
    main()
