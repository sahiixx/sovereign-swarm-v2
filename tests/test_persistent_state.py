"""Tests for PersistentAgentState — restart-safe agent identities."""
import asyncio, tempfile, unittest
from pathlib import Path

from sovereign_swarm.agents.state import PersistentAgentState, AgentIdentity


class TestPersistentAgentState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "agents.db"

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_new_agent(self):
        s = PersistentAgentState("alpha_1", "executor", db_path=self.db)
        self.assertEqual(s.agent_id, "alpha_1")
        self.assertTrue(s.is_new)
        s.close()

    def test_restore_after_close(self):
        s1 = PersistentAgentState("beta_2", "planner", db_path=self.db)
        s1.update_objective("audit smart contract")
        s1.add_task_result("scan", {"result": "clean"}, 0.97)
        s1.sync()
        s1.close()

        s2 = PersistentAgentState("beta_2", "planner", db_path=self.db)
        self.assertEqual(s2._identity.objective, "audit smart contract")
        self.assertEqual(s2._identity.task_count, 1)
        self.assertFalse(s2.is_new)

        history = s2.get_task_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["task"], "scan")
        s2.close()

    def test_success_rate_calculation(self):
        s = PersistentAgentState("gamma_3", "critic", db_path=self.db)
        s.add_task_result("t1", {}, 0.5)
        s.add_task_result("t2", {}, 1.0)
        # avg = 0.75
        self.assertEqual(s._identity.success_rate, 0.75)
        s.close()

    def test_skills_and_tags(self):
        s = PersistentAgentState("delta_4", "observer", db_path=self.db)
        s.add_skill("web_scraper")
        s.add_skill("web_scraper")  # duplicate ignored
        s.add_tag("production")
        s.sync()

        s2 = PersistentAgentState("delta_4", "observer", db_path=self.db)
        self.assertEqual(s2._identity.skills, ["web_scraper"])
        self.assertEqual(s2._identity.tags, ["production"])
        s2.close()

    def test_checkpoint_roundtrip(self):
        s = PersistentAgentState("eps_5", "learner", db_path=self.db)
        s.update_objective("train model")
        cp = s.checkpoint()
        self.assertEqual(cp["agent_id"], "eps_5")
        self.assertEqual(cp["objective"], "train model")
        self.assertTrue("timestamp" in cp)
        s.close()

if __name__ == "__main__":
    unittest.main()
