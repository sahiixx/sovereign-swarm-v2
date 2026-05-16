"""Tests for SemanticMemory — numpy-powered vector recall."""
import asyncio, tempfile, unittest
from pathlib import Path

from sovereign_swarm.infra.semantic_memory import SemanticMemory


class TestSemanticMemory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "semantic.db"

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_init_creates_schema(self):
        mem = SemanticMemory(db_path=self.db, dim=128)
        self._run(mem.init())
        self.assertTrue(self.db.exists())
        self._run(mem.close())

    def test_store_and_search(self):
        mem = SemanticMemory(db_path=self.db, dim=128)
        self._run(mem.init())
        self._run(mem.store("fast execution pipeline", agent_id="alpha", tags=["perf"]))
        self._run(mem.store("deployment speed matters", agent_id="alpha", tags=["ops"]))
        self._run(mem.store("slow database queries", agent_id="beta", tags=["db"]))

        results = self._run(mem.search("execution speed", top_k=2, agent_id="alpha"))
        self.assertEqual(len(results), 2)
        # "fast execution pipeline" should rank highest
        self.assertIn("execution", results[0]["content"].lower())
        self._run(mem.close())

    def test_cross_agent_search(self):
        mem = SemanticMemory(db_path=self.db, dim=128)
        self._run(mem.init())
        self._run(mem.store("user likes fast bots", agent_id="alpha"))
        self._run(mem.store("bots should be fast", agent_id="beta"))

        results = self._run(mem.search("fast bots", top_k=5))
        self.assertEqual(len(results), 2)
        self._run(mem.close())

    def test_importance_boosting(self):
        mem = SemanticMemory(db_path=self.db, dim=128)
        self._run(mem.init())
        self._run(mem.store("critical alert", importance=2.0))
        self._run(mem.store("minor note", importance=0.1))
        results = self._run(mem.search("alert", top_k=1))
        self.assertEqual(results[0]["content"], "critical alert")
        self._run(mem.close())

    def test_access_count_increment(self):
        mem = SemanticMemory(db_path=self.db, dim=128)
        self._run(mem.init())
        self._run(mem.store("test memory"))
        results = self._run(mem.search("test", top_k=1))
        mid = results[0]["id"]
        # Search again to increment
        self._run(mem.search("test", top_k=1))
        self._run(mem.close())

if __name__ == "__main__":
    unittest.main()
