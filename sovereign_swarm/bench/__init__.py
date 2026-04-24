"""Router benchmark suite — test all routing strategies at scale."""
from ..config import *
from ..intelligence.orchestrator import MetaOrchestrator
from ..intelligence.agent_profile import AgentProfile
import time

class RouterBenchmark:
    STRATEGIES = ["trust", "latency", "cost", "balanced"]

    def __init__(self, agent_count: int = 100):
        self.agent_count = agent_count
        self.results: Dict[str, Dict] = {}

    def setup(self):
        self.meta = MetaOrchestrator()
        for i in range(self.agent_count):
            self.meta.register(AgentProfile(
                f"agent_{i}", skills=["search", "code", "lead"][i % 3],
                trust=0.3 + (i % 70) / 100,
                latency_ms=20 + (i % 500),
                cost_usd=0.005 + (i % 20) * 0.001
            ))

    def run(self, iterations: int = 1000) -> Dict:
        self.setup()
        for strategy in self.STRATEGIES:
            t0 = time.perf_counter()
            route_counts: Dict[str, int] = {}
            for _ in range(iterations):
                choice = self.meta.route("search", strategy=strategy)
                route_counts[choice] = route_counts.get(choice, 0) + 1
            t1 = time.perf_counter()
            self.results[strategy] = {
                "iterations": iterations,
                "total_ms": round((t1 - t0) * 1000, 3),
                "avg_us": round((t1 - t0) * 1e6 / iterations, 3),
                "unique_routes": len(route_counts),
                "top_route": max(route_counts, key=route_counts.get) if route_counts else None,
                "top_count": max(route_counts.values()) if route_counts else 0,
            }
        return self.results

    def report(self) -> str:
        lines = ["\n[ROUTER BENCHMARK]", f"Agents: {self.agent_count}", "-" * 50]
        for strat, res in self.results.items():
            lines.append(f"  {strat:12} {res['total_ms']:>8.2f}ms  avg={res['avg_us']:>8.3f}us  routes={res['unique_routes']}")
        lines.append("-" * 50)
        return "\n".join(lines)
