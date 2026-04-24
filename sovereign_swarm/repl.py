from .config import *
from .infra import *
from .intelligence import *
from .agents import *
from .protocols import *
from .safety import *


class SwarmREPL:
    def __init__(self):
        self.bus = SwarmBus(DATA_DIR / "bus.db")
        self.meta = MetaOrchestrator()
        self.safety = SafetyCouncil()
        self.memory = SwarmMemory(DATA_DIR / "memory.db")
        self.llm = LLMClient()
        self.agents: Dict[str, Any] = {}
        self.running = True
        self.platform = PlatformDetector()
        self.battery = BatteryMonitor()
        self.thermal = ThermalMonitor()
        self.audit = AuditTrail(DATA_DIR)
        self.backup = BackupManager(DATA_DIR)
        self.alert = AlertDispatcher()
        self.observe = ObservabilityLayer()
        self.hermes = HermesMessenger()
        self.mcp = MCPServer()
        self.a2a = A2ACardServer()
        self.openclaw = OpenClawGateway()
        self.bridge = SwarmBridge()
        self.scheduler = SwarmScheduler(self.battery)
        self.hitl = HITLCouncil()
        self.reputation = ReputationEngine()
        self.heal = HealEngine()
        self.econ = EconomicEngine()
        self.evo = EvolutionEngine()
        self.schema = ToolSchema()
        self.budget = BudgetController()
        self.costctl = CostController()
        self.qwen3 = Qwen3Router()

    async def seed(self):
        await self.bus.init(); await self.memory.init()
        for s in SpecialistFactory.SPECIALTIES:
            self.meta.register(AgentProfile(f"{s}_0", [s], trust=0.7))
        print("[seed] Bus + Memory + Meta initialized. 10 specialist profiles registered.")

    async def cmd_spawn(self, name: str):
        agent_id = f"{name}_{len(self.agents)}"
        self.agents[agent_id] = {"name": name, "status": "idle", "tasks": 0}
        await self.bus.publish("agent.spawned", {"id": agent_id, "name": name})
        self.audit.log("agent.spawn", {"agent_id": agent_id, "name": name}, agent_id)
        print(f"[spawn] Agent {agent_id} created.")

    async def cmd_hermes(self, sub: str = "status"):
        if sub == "status": print(json.dumps(self.hermes.status(), indent=2))
        else: print(f"[hermes] Protocol messenger: {sub}")

    async def cmd_oc(self, sub: str = "status"):
        if sub == "status": print(json.dumps(self.openclaw.report(), indent=2))
        else: print(f"[openclaw] Gateway :18789 — {sub}")

    async def cmd_ollama(self, sub: str = "status"):
        if sub == "status": print(json.dumps(await self.llm.healthcheck(), indent=2))
        else: print(f"[ollama] {sub}")

    async def cmd_metrics(self):
        print(f"[metrics] Agents: {len(self.agents)} | Bus msgs: {await self.bus.count()}")
        print(json.dumps(self.observe.report(), indent=2))

    async def cmd_mcp_tools(self):
        for t in self.mcp.TOOLS: print(f"  • {t}")

    async def cmd_memory_search(self, query: str):
        results = await self.memory.search(query)
        for r in results: print(f"  → {r['key']}: {r['value']}")

    async def cmd_audit(self, scope: str = "today"):
        print(f"[audit] Scope: {scope}")
        print(json.dumps(self.audit.report(), indent=2))

    async def cmd_alert_test(self):
        result = await self.alert.send("Test alert from Sovereign Swarm v2.0", "info")
        print(json.dumps(result, indent=2))

    async def cmd_kill(self):
        print("[kill] ARMED. Pausing all non-exempt agents.")
        for aid, a in self.agents.items(): a["status"] = "killed"
        self.audit.log("kill_switch.armed", {"agents_affected": list(self.agents.keys())}, "system")
        self.running = False

    async def cmd_platform(self):
        print(json.dumps(self.platform.report(), indent=2))

    async def cmd_battery(self):
        self.battery.refresh(); print(json.dumps(self.battery.report(), indent=2))

    async def cmd_thermal(self):
        print(json.dumps(self.thermal.report(), indent=2))

    async def cmd_reputation(self):
        print(json.dumps(self.reputation.report(), indent=2))

    async def cmd_economics(self):
        print(json.dumps(self.econ.report(), indent=2))

    async def cmd_backup(self):
        print(json.dumps(self.backup.create(), indent=2))

    async def cmd_specialists(self):
        specs = SpecialistFactory.spawn_all()
        for s in specs:
            result = await s.run({})
            print(f"  {s.agent_id}: {result}")

    async def repl_loop(self):
        print("\n🕸️  Sovereign Swarm v2.0 REPL — Modular Multi-Agent OS")
        print("   Type 'help' for commands, 'exit' to quit.\n")
        try:
            while self.running:
                try:
                    line = input("swarm> ").strip()
                    if not line: continue
                    parts = line.split(); cmd = parts[0].lower(); args = parts[1:]
                    if cmd in ("exit", "quit"): break
                    elif cmd == "help":
                        print("""
Commands:
  spawn <name>          Spawn specialist agent
  hermes [status]       Universal protocol messenger
  oc [status]           OpenClaw gateway
  ollama [status]       Ollama lifecycle
  metrics               Swarm metrics + observability
  mcp tools             List 12 MCP tools
  memory search <q>     Semantic memory search
  audit [today]         Audit trail
  alert test            Test alert channels
  platform              Detect platform + recommend model
  battery               Battery status + mode
  thermal               Thermal status + tier
  reputation            Agent reputation scores
  economics             Cost predictions + ROI
  backup                Create backup snapshot
  specialists           Run all 10 specialists once
  kill                  Arm kill switch
""")
                    elif cmd == "spawn" and args: await self.cmd_spawn(args[0])
                    elif cmd == "hermes": await self.cmd_hermes(args[0] if args else "status")
                    elif cmd == "oc": await self.cmd_oc(args[0] if args else "status")
                    elif cmd == "ollama": await self.cmd_ollama(args[0] if args else "status")
                    elif cmd == "metrics": await self.cmd_metrics()
                    elif cmd == "mcp" and args and args[0] == "tools": await self.cmd_mcp_tools()
                    elif cmd == "memory" and len(args) >= 2 and args[0] == "search": await self.cmd_memory_search(" ".join(args[1:]))
                    elif cmd == "audit": await self.cmd_audit(args[0] if args else "today")
                    elif cmd == "alert" and args and args[0] == "test": await self.cmd_alert_test()
                    elif cmd == "platform": await self.cmd_platform()
                    elif cmd == "battery": await self.cmd_battery()
                    elif cmd == "thermal": await self.cmd_thermal()
                    elif cmd == "reputation": await self.cmd_reputation()
                    elif cmd == "economics": await self.cmd_economics()
                    elif cmd == "backup": await self.cmd_backup()
                    elif cmd == "specialists": await self.cmd_specialists()
                    elif cmd == "kill": await self.cmd_kill()
                    else: print(f"[!] Unknown command: {cmd}")
                except EOFError: break
                except Exception as e: print(f"[error] {e}")
        except KeyboardInterrupt:
            print("\n[repl] Interrupted")
        print("\n[repl] Exited.")

    async def shutdown(self):
        await self.bus.close(); await self.memory.close()


