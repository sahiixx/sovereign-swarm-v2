from ..config import *

class BaseAgent:
    def __init__(self, agent_id: str, role: str):
        self.agent_id = agent_id; self.role = role; self.status = "idle"; self.memory: List[Dict] = []

    async def observe(self, context: Dict) -> Dict:
        self.status = "observing"; return {"agent_id": self.agent_id, "observation": context}

    async def plan(self, objective: str) -> List[str]:
        self.status = "planning"; return [f"step_1: analyze {objective}", f"step_2: execute {objective}", f"step_3: verify {objective}"]

    async def execute(self, task: str, tools: Dict[str, Callable]) -> Dict:
        self.status = "executing"; return {"agent_id": self.agent_id, "task": task, "result": "done", "timestamp": time.time()}

    async def critique(self, result: Dict) -> Dict:
        self.status = "critiquing"; return {"agent_id": self.agent_id, "score": random.uniform(0.5, 1.0), "feedback": "OK"}


