"""n8n-lite webhook tests — embedded server + urllib client."""
import json, sys, os, threading, time, unittest, urllib.request, urllib.error
import importlib.util

N8N_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "n8n-lite.py"))
spec = importlib.util.spec_from_file_location("n8n_lite", N8N_PATH)
n8n = importlib.util.module_from_spec(spec)
sys.modules["n8n_lite"] = n8n
spec.loader.exec_module(n8n)


class TestN8NLiteWebhooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._orig_call_dsl = n8n.Handler._call_dsl
        n8n.Handler._call_dsl = lambda self, goal: {"status": "ok", "goal": goal}
        cls.server = n8n.ThreadedHTTPServer(("127.0.0.1", 0), n8n.Handler)
        cls.port = cls.server.server_address[1]
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls._thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls._thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        n8n.Handler._call_dsl = cls._orig_call_dsl
        cls.server.shutdown()
        cls.server.server_close()
        cls._thread.join(timeout=2)

    def _request(self, method, path, body=None):
        url = self.base + path
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json"} if body else {})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            try:
                return e.code, json.loads(body)
            except json.JSONDecodeError:
                return e.code, {"raw": body}

    # ── Health ──
    def test_health(self):
        code, data = self._request("GET", "/health")
        self.assertEqual(code, 200)
        self.assertTrue(data["ok"])
        self.assertIn("version", data)

    def test_root(self):
        code, data = self._request("GET", "/")
        self.assertEqual(code, 200)
        self.assertTrue(data["ok"])

    # ── DSL mission webhook ──
    def test_dsl_missing_goal(self):
        code, data = self._request("POST", "/webhook/dsl-mission", {})
        self.assertEqual(code, 400)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "Missing goal")

    def test_dsl_success(self):
        code, data = self._request("POST", "/webhook/dsl-mission", {"goal": "echo hello"})
        self.assertEqual(code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["mission"], "echo hello")
        self.assertEqual(data["result"]["status"], "ok")

    # ── Telegram webhook ──
    def test_telegram_ignored(self):
        code, data = self._request("POST", "/webhook/telegram", {"message": {"text": "hi", "chat": {"id": 1}}})
        self.assertEqual(code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["status"], "ignored")

    def test_telegram_dsl_accepted(self):
        code, data = self._request("POST", "/webhook/telegram", {"message": {"text": "/dsl run tests", "chat": {"id": 42}}})
        self.assertEqual(code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["status"], "accepted")
        self.assertEqual(data["goal"], "run tests")

    # ── Workflow CRUD ──
    def test_create_workflow(self):
        code, data = self._request("POST", "/workflow/create", {"id": "wf_test", "description": "x", "steps": []})
        self.assertEqual(code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["workflow_id"], "wf_test")

    def test_run_unknown_workflow(self):
        code, data = self._request("POST", "/workflow/run", {"workflow_id": "nonexistent"})
        self.assertEqual(code, 404)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "Unknown workflow")

    def test_run_workflow_steps(self):
        self._request("POST", "/workflow/create", {
            "id": "wf_steps",
            "steps": [
                {"name": "s1", "type": "dsl", "goal": "g1"},
                {"name": "s2", "type": "notify", "chat_id": "1", "message": "m"},
            ]
        })
        code, data = self._request("POST", "/workflow/run", {"workflow_id": "wf_steps"})
        self.assertEqual(code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["workflow_result"]["status"], "ran")
        self.assertEqual(len(data["workflow_result"]["steps"]), 2)
        self.assertEqual(data["workflow_result"]["steps"][0]["result"]["status"], "ok")
        self.assertEqual(data["workflow_result"]["steps"][1]["result"], "sent")

    # ── Generic GET webhook ──
    def test_webhook_trigger(self):
        code, data = self._request("GET", "/webhook/my-tag")
        self.assertEqual(code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["triggered"], "my-tag")

    def test_unknown_path(self):
        code, data = self._request("GET", "/nope")
        self.assertEqual(code, 404)
        self.assertIn("error", data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
