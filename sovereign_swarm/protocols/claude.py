"""ClaudeProvider — Anthropic Claude API bridge for Sovereign Swarm v2.

Supports direct Anthropic endpoint and OpenRouter proxy.
Auto-detects credentials from env: ANTHROPIC_API_KEY, OPENROUTER_API_KEY, CLAUDE_API_KEY.

Usage:
    provider = ClaudeProvider(model="claude-sonnet-4-20250514")
    result = await provider.generate("Write a secure auth middleware", max_tokens=4096)
"""

import asyncio, json, os
from typing import Dict, List, Optional
import httpx


class ClaudeProvider:
    """Anthropic Claude inference provider with fallback routing."""

    DEFAULT_MODEL = "claude-sonnet-4-20250514"
    ANTHROPIC_BASE = "https://api.anthropic.com/v1"
    OPENROUTER_BASE = "https://openrouter.ai/api/v1"

    def __init__(self, model: str = None, api_key: str = None, base_url: str = None):
        self.model = model or self.DEFAULT_MODEL
        self.base_url = base_url
        self.api_key = api_key
        self.client = httpx.AsyncClient(timeout=120)
        self._detect_credentials()

    def _detect_credentials(self):
        """Auto-detect provider endpoint from available env vars."""
        if self.base_url:
            return

        # Direct Anthropic
        if self.api_key or os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY"):
            self.api_key = self.api_key or os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
            self.base_url = self.ANTHROPIC_BASE
            self._provider = "anthropic"
            return

        # OpenRouter fallback (includes Claude models)
        if os.getenv("OPENROUTER_API_KEY"):
            self.api_key = os.getenv("OPENROUTER_API_KEY")
            self.base_url = self.OPENROUTER_BASE
            self._provider = "openrouter"
            return

        raise RuntimeError(
            "No Claude credentials found. Set ANTHROPIC_API_KEY, CLAUDE_API_KEY, or OPENROUTER_API_KEY."
        )

    async def generate(self, prompt: str, system: str = "", max_tokens: int = 4096,
                       temperature: float = 0.7, tools: List[Dict] = None) -> Dict:
        """Send a message to Claude and return structured result."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        if self._provider == "anthropic":
            headers["anthropic-version"] = "2023-06-01"
            url = f"{self.base_url}/messages"
            body = {
                "model": self.model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system:
                body["system"] = system
            if tools:
                body["tools"] = tools
        else:
            # OpenRouter
            url = f"{self.base_url}/chat/completions"
            headers["HTTP-Referer"] = "https://sovereign-swarm.ai"
            headers["X-Title"] = "SovereignSwarm"
            body = {
                "model": self.model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [
                    {"role": "system", "content": system or "You are a helpful assistant."},
                    {"role": "user", "content": prompt},
                ],
            }
            if tools:
                body["tools"] = tools

        resp = await self.client.post(url, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()

        if self._provider == "anthropic":
            content = "".join(
                block.get("text", "")
                for block in data.get("content", [])
                if block.get("type") == "text"
            )
            usage = data.get("usage", {})
            return {
                "content": content,
                "model": data.get("model"),
                "stop_reason": data.get("stop_reason"),
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "provider": "anthropic",
            }
        else:
            choice = data.get("choices", [{}])[0]
            msg = choice.get("message", {})
            usage = data.get("usage", {})
            return {
                "content": msg.get("content", ""),
                "model": data.get("model"),
                "stop_reason": msg.get("stop_reason"),
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
                "provider": "openrouter",
            }

    async def embed(self, text: str) -> List[float]:
        """Generate embeddings via the provider (if supported)."""
        # Anthropic doesn't expose embeddings; fall back to OpenRouter or local
        if self._provider == "openrouter":
            # Use OpenRouter embedding-compatible models
            url = f"{self.base_url}/embeddings"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://sovereign-swarm.ai",
            }
            body = {"model": "text-embedding-3-small", "input": text}
            resp = await self.client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", [{}])[0].get("embedding", [])
        return []

    async def close(self):
        await self.client.aclose()

    def status(self) -> Dict:
        return {
            "provider": self._provider,
            "model": self.model,
            "base_url": self.base_url,
            "available": bool(self.api_key),
        }
