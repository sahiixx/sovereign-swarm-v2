"""Tests for ClaudeProvider — Anthropic/API bridge."""
import asyncio, os, unittest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from sovereign_swarm.protocols.claude import ClaudeProvider


class MockResponse:
    def __init__(self, json_data, status=200):
        self._json = json_data
        self.status_code = status
    def json(self): return self._json
    def raise_for_status(self): pass


class TestClaudeProvider(unittest.TestCase):
    def _run(self, coro):
        return asyncio.run(coro)

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test_key"}, clear=False)
    def test_detects_anthropic(self):
        p = ClaudeProvider()
        self.assertEqual(p._provider, "anthropic")
        self.assertEqual(p.api_key, "test_key")

    @patch.dict(os.environ, {}, clear=True)
    @patch.dict(os.environ, {"OPENROUTER_API_KEY": "or_key"})
    def test_fallback_to_openrouter(self):
        # Ensure ANTHROPIC key not present
        for k in ["ANTHROPIC_API_KEY", "CLAUDE_API_KEY"]:
            if k in os.environ:
                del os.environ[k]
        p = ClaudeProvider()
        self.assertEqual(p._provider, "openrouter")

    def test_no_credentials_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                ClaudeProvider()

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test_key"})
    @patch("httpx.AsyncClient.post")
    def test_generate_anthropic(self, mock_post):
        mock_post.return_value = MockResponse({
            "id": "msg_1",
            "model": "claude-sonnet-4",
            "content": [{"type": "text", "text": "Hello world"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        })
        p = ClaudeProvider()
        result = self._run(p.generate("Say hello"))
        self.assertEqual(result["content"], "Hello world")
        self.assertEqual(result["input_tokens"], 10)

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": "or_key"})
    @patch("httpx.AsyncClient.post")
    def test_generate_openrouter(self, mock_post):
        mock_post.return_value = MockResponse({
            "choices": [{"message": {"content": "OR output"}}],
            "model": "claude-sonnet",
            "usage": {"prompt_tokens": 3, "completion_tokens": 2},
        })
        p = ClaudeProvider()
        result = self._run(p.generate("Test"))
        self.assertEqual(result["content"], "OR output")
        self.assertEqual(result["provider"], "openrouter")

    def test_status(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}, clear=False):
            p = ClaudeProvider()
            st = p.status()
            self.assertTrue(st["available"])
            self.assertEqual(st["provider"], "anthropic")

if __name__ == "__main__":
    unittest.main()
