from ..config import *

class ObservabilityLayer:
    def __init__(self, prometheus_port: int = 9091):
        self.prometheus_port = prometheus_port; self.metrics: Dict[str, Any] = {}; self.langfuse_traces: list = []; self._prom_started = False
        if PromCounter:
            self.metrics["agent_runs"] = PromCounter("swarm_agent_runs_total", "Total agent runs", ["specialty"])
            self.metrics["task_latency"] = Histogram("swarm_task_latency_seconds", "Task latency")
            self.metrics["active_agents"] = Gauge("swarm_active_agents", "Currently active agents")
            self.metrics["safety_blocks"] = PromCounter("swarm_safety_blocks_total", "Total safety blocks", ["rule"])

    def start_prometheus(self):
        if start_http_server and not self._prom_started:
            start_http_server(self.prometheus_port); self._prom_started = True; print(f"[observe] Prometheus metrics on :{self.prometheus_port}")

    def record_agent_run(self, specialty: str, latency_seconds: float):
        if "agent_runs" in self.metrics: self.metrics["agent_runs"].labels(specialty=specialty).inc()
        if "task_latency" in self.metrics: self.metrics["task_latency"].observe(latency_seconds)

    def set_active_agents(self, count: int):
        if "active_agents" in self.metrics: self.metrics["active_agents"].set(count)

    def record_safety_block(self, rule: str):
        if "safety_blocks" in self.metrics: self.metrics["safety_blocks"].labels(rule=rule).inc()

    def langfuse_trace(self, name: str, input_data: Dict, output_data: Dict, score: float = 1.0):
        self.langfuse_traces.append({"name": name, "input": input_data, "output": output_data, "score": score, "timestamp": time.time()})

    def report(self) -> Dict:
        return {"prometheus_port": self.prometheus_port, "prom_started": self._prom_started, "langfuse_traces": len(self.langfuse_traces), "metrics_registered": list(self.metrics.keys())}


