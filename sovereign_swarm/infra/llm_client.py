from ..config import *

# Try to load .env if python-dotenv available
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

class LLMClient:
    """Unified LLM client supporting Ollama (local) and Anthropic Claude (cloud)."""

    # Anthropic Claude 3.5 Sonnet model identifier
    CLAUDE_MODEL = "claude-3-5-sonnet-20241022"
    ANTHROPIC_BASE = "https://api.anthropic.com/v1"

    def __init__(self, session: Optional[Any] = None):
        self.ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.openai_key = os.getenv("OPENAI_API_KEY", "")
        self.default_model = os.getenv("OLLAMA_MODEL", "qwen3:4b")

        # Anthropic credentials
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY", "") or os.getenv("CLAUDE_API_KEY", "")
        self.anthropic_base = os.getenv("ANTHROPIC_BASE_URL", self.ANTHROPIC_BASE)
        self.claude_model = os.getenv("CLAUDE_MODEL", self.CLAUDE_MODEL)

        self._session = session
        self._httpx = None
        try:
            import httpx
            self._httpx = httpx
        except ImportError:
            pass

    def _get_session(self):
        if self._session:
            return self._session, False
        if aiohttp:
            return aiohttp.ClientSession(), True
        return None, False

    def _httpx_client(self):
        if self._httpx:
            return self._httpx.AsyncClient(timeout=self._httpx.Timeout(120.0))
        return None

    @property
    def claude_available(self) -> bool:
        return bool(self.anthropic_key) and self._httpx is not None

    async def healthcheck(self, provider: str = "ollama") -> str:
        if provider == "claude":
            if not self.claude_available:
                return "claude unavailable (no ANTHROPIC_API_KEY or httpx missing)"
            client = self._httpx_client()
            if not client:
                return "httpx not installed"
            try:
                url = f"{self.anthropic_base}/models"
                headers = {
                    "x-api-key": self.anthropic_key,
                    "anthropic-version": "2023-06-01",
                }
                resp = await client.get(url, headers=headers, timeout=10)
                ok = "healthy" if resp.status_code == 200 else f"status:{resp.status_code}"
                await client.aclose()
                return ok
            except Exception as e:
                try:
                    await client.aclose()
                except Exception:
                    pass
                return f"unreachable ({str(e)[:50]})"

        # Ollama healthcheck
        if not aiohttp:
            return "aiohttp not installed"
        session, owned = self._get_session()
        if not session:
            return "aiohttp not installed"
        try:
            async with session.get(f"{self.ollama_host}/api/tags", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                return "healthy" if resp.status == 200 else f"status:{resp.status}"
        except Exception as e:
            return f"unreachable ({str(e)[:50]})"
        finally:
            if owned:
                await session.close()

    async def chat(self, prompt: str, model: Optional[str] = None, json_mode: bool = False,
                   tools: Optional[List[Dict[str, Any]]] = None, fallback: bool = True) -> Dict[str, Any]:
        """Chat with LLM. Uses Claude if available, otherwise Ollama.

        Args:
            prompt: User prompt string.
            model: Override model name. If empty and Claude available, uses claude-3-5-sonnet.
            json_mode: Request structured JSON output (Claude + Ollama).
            tools: Optional tool definitions for function calling.
            fallback: If True, fallback to Ollama when Claude fails.
        """
        # Decide provider
        use_claude = self.claude_available and (not model or model.startswith("claude"))
        if use_claude:
            try:
                return await self._chat_claude(prompt, model=model or self.claude_model,
                                                json_mode=json_mode, tools=tools)
            except Exception as e:
                if not fallback:
                    return {"error": f"Claude error: {e}", "response": ""}
                # Fall through to Ollama
        return await self._chat_ollama(prompt, model=model or self.default_model,
                                        json_mode=json_mode, tools=tools)

    async def _chat_claude(self, prompt: str, model: str, json_mode: bool = False,
                           tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        if not self._httpx:
            return {"error": "httpx missing", "response": ""}
        client = self._httpx_client()
        if not client:
            return {"error": "httpx missing", "response": ""}
        try:
            url = f"{self.anthropic_base}/messages"
            headers = {
                "x-api-key": self.anthropic_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            body = {
                "model": model,
                "max_tokens": 4096,
                "temperature": 0.7,
                "messages": [{"role": "user", "content": prompt}],
            }
            if json_mode:
                # Claude 3.5 Sonnet supports JSON mode via system prompt hint
                body["system"] = "Respond ONLY with a valid JSON object. Do not include markdown formatting or explanations."
            if tools:
                body["tools"] = tools
            resp = await client.post(url, headers=headers, json=body, timeout=120)
            resp.raise_for_status()
            data = resp.json()

            content = ""
            tool_calls = []
            for block in data.get("content", []):
                if block.get("type") == "text":
                    content += block.get("text", "")
                elif block.get("type") == "tool_use":
                    tool_calls.append({
                        "id": block.get("id", ""),
                        "name": block.get("name", ""),
                        "input": block.get("input", {}),
                    })

            usage = data.get("usage", {})
            result = {
                "response": content,
                "model": data.get("model", model),
                "provider": "anthropic",
                "stop_reason": data.get("stop_reason"),
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
            }
            if tool_calls:
                result["tool_calls"] = tool_calls
            if json_mode:
                try:
                    result["json"] = json.loads(content)
                except Exception:
                    result["json"] = None
            return result
        except Exception as e:
            return {"error": str(e), "response": ""}
        finally:
            try:
                await client.aclose()
            except Exception:
                pass

    async def _chat_ollama(self, prompt: str, model: str, json_mode: bool = False,
                            tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        if not aiohttp:
            return {"error": "aiohttp missing", "response": ""}
        session, owned = self._get_session()
        if not session:
            return {"error": "aiohttp missing", "response": ""}
        try:
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            }
            if json_mode:
                payload["format"] = "json"
            if tools:
                payload["tools"] = tools
            async with session.post(f"{self.ollama_host}/api/chat", json=payload,
                                    timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result = {"response": data.get("message", {}).get("content", ""), "model": model, "provider": "ollama"}
                    if json_mode:
                        try:
                            result["json"] = json.loads(result["response"])
                        except Exception:
                            result["json"] = None
                    return result
                return {"error": f"HTTP {resp.status}", "response": ""}
        except Exception as e:
            return {"error": str(e), "response": ""}
        finally:
            if owned:
                await session.close()

    async def generate(self, prompt: str, model: Optional[str] = None, system: str = "",
                       max_tokens: int = 4096, temperature: float = 0.7,
                       json_mode: bool = False, tools: Optional[List[Dict[str, Any]]] = None,
                       fallback: bool = True) -> Dict[str, Any]:
        """Unified generate interface — mirrors ClaudeProvider.generate for compatibility."""
        use_claude = self.claude_available and (not model or model.startswith("claude"))
        if use_claude:
            try:
                return await self._chat_claude(
                    prompt,
                    model=model or self.claude_model,
                    json_mode=json_mode,
                    tools=tools,
                )
            except Exception as e:
                if not fallback:
                    return {"error": f"Claude error: {e}", "response": "", "provider": "anthropic"}
        return await self._chat_ollama(
            prompt,
            model=model or self.default_model,
            json_mode=json_mode,
            tools=tools,
        )
