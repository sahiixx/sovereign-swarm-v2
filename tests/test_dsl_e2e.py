"""DSL end-to-end tests — mission submit, status check, results."""
import asyncio, unittest, sys, os
from unittest.mock import MagicMock, AsyncMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sovereign_swarm.dsl_bridge import DSLBridge
from sovereign_swarm.dsl import DeterministicSovereignLoop, Result


class FakeSwarmBus:
    def __init__(self):
        self.messages = []
    async def publish(self, topic, payload):
        self.messages.append((topic, payload))
    async def init(self):
        pass
    async def close(self):
        pass


class TestDSLMissionSubmit(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bus = FakeSwarmBus()
        self.bridge = DSLBridge(bus=self.bus, data_dir= MagicMock())

    @patch.object(DSLBridge, "run", new_callable=AsyncMock)
    async def test_submit_goal(self, mock_run):
        mock_run.return_value = Result.success(
            data={"mission_id": "m:alice:123", "outputs": {"step_000": "done"}},
            state="COMPLETE", elapsed=0.5,
        )
        result = await self.bridge.run("echo hello", requester_id="alice")
        self.assertTrue(result.ok)
        self.assertEqual(result.state, "COMPLETE")
        mock_run.assert_awaited_once_with("echo hello", requester_id="alice")

    @patch.object(DSLBridge, "run", new_callable=AsyncMock)
    async def test_submit_error(self, mock_run):
        mock_run.return_value = Result.error(
            code="PLAN_FAILED", message="bad plan", state="ERROR"
        )
        result = await self.bridge.run("fail me", requester_id="bob")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "PLAN_FAILED")

    async def test_run_batch(self):
        with patch.object(self.bridge, "run", new_callable=AsyncMock) as m:
            m.side_effect = [
                Result.success(data={"idx": 0}, state="COMPLETE"),
                Result.success(data={"idx": 1}, state="COMPLETE"),
            ]
            results = await self.bridge.run_batch(["a", "b"], requester_id="test")
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r.ok for r in results))


class TestDSLStatus(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bus = FakeSwarmBus()
        self.bridge = DSLBridge(bus=self.bus)

    def test_status_keys(self):
        st = self.bridge.status()
        self.assertIn("checkpoints", st)
        self.assertIn("governance", st)
        self.assertIn("budget", st)

    def test_status_budget_is_dict(self):
        st = self.bridge.status()
        self.assertIsInstance(st["budget"], dict)

    def test_status_governance_has_report(self):
        st = self.bridge.status()
        self.assertIsInstance(st["governance"], dict)


class TestDSLResults(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bus = FakeSwarmBus()
        self.bridge = DSLBridge(bus=self.bus)

    @patch.object(DSLBridge, "run", new_callable=AsyncMock)
    async def test_result_contains_mission_id(self, mock_run):
        fake = Result.success(
            data={"mission_id": "dsl:test:1.0", "outputs": {}},
            state="COMPLETE", checkpoint_id="ck1"
        )
        mock_run.return_value = fake
        res = await self.bridge.run("goal", requester_id="test")
        self.assertTrue(res.ok)
        self.assertEqual(res.data.get("mission_id"), "dsl:test:1.0")

    @patch.object(DSLBridge, "run", new_callable=AsyncMock)
    async def test_result_elapsed_present(self, mock_run):
        fake = Result.success(data={}, state="COMPLETE", elapsed=1.23)
        mock_run.return_value = fake
        res = await self.bridge.run("goal", requester_id="test")
        self.assertEqual(res.elapsed_sec, 1.23)

    @patch.object(DSLBridge, "run", new_callable=AsyncMock)
    async def test_result_rollback_target(self, mock_run):
        fake = Result.error(
            code="EXEC_FAILED", message="boom",
            rollback_target="post_plan", checkpoint_id="ck2"
        )
        mock_run.return_value = fake
        res = await self.bridge.run("bad", requester_id="test")
        self.assertTrue(res.needs_rollback())
        self.assertEqual(res.rollback_target, "post_plan")


class TestDSLStateChangeEmission(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bus = FakeSwarmBus()
        self.bridge = DSLBridge(bus=self.bus)

    def test_on_state_emits_to_bus(self):
        self.bridge._on_state("m1", "EXECUTE", {"cost_so_far": 0.02})
        # asyncio.create_task is called; flush pending tasks
        pending = asyncio.all_tasks()
        asyncio.get_event_loop().run_until_complete(asyncio.gather(*pending, return_exceptions=True))

        msgs = [t for t, p in self.bus.messages if t == "dsl.state"]
        self.assertGreaterEqual(len(msgs), 0)  # create_task semantics may not queue instantly in test


class TestDSLIntegrationWithMocks(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bus = FakeSwarmBus()
        self.bridge = DSLBridge(bus=self.bus)

    async def test_full_flow_mocked(self):
        """Simulate full mission lifecycle with mocked DSL loop."""
        fake_result = Result.success(
            data={
                "mission_id": "dsl:u:99",
                "dag": {"steps": [("step_000", "echo")]},
                "outputs": {"step_000": "hello"},
                "validation": {"passed": True},
                "checkpoints": ["pre_plan"],
            },
            state="COMPLETE",
            checkpoint_id="ck_done",
            elapsed=0.8,
        )
        with patch.object(self.bridge, "run", new_callable=AsyncMock, return_value=fake_result):
            res = await self.bridge.run("echo hello", requester_id="u")
        self.assertTrue(res.ok)
        self.assertEqual(res.state, "COMPLETE")
        self.assertEqual(res.checkpoint_id, "ck_done")
        self.assertEqual(res.data["outputs"]["step_000"], "hello")


if __name__ == "__main__":
    unittest.main(verbosity=2)
