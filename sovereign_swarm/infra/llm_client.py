from ..config import *

class LLMClient:
    def __init__(self):
        self.ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.openai_key = os.getenv("OPENAI_API_KEY", "")
        self.default_model = os.getenv("OLLAMA_MODEL", "qwen3:4b")

    async def healthcheck(self) -> str:
        if not aiohttp:
            return "aiohttp not installed"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.ollama_host}/api/tags", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    return "healthy" if resp.status == 200 else f"status:{resp.status}"
        except Exception as e:
            return f"unreachable ({str(e)[:50]})"

    async def chat(self, prompt: str, model: Optional[str] = None) -> Dict[str, Any]:
        model = model or self.default_model
        if not aiohttp:
            return {"error": "aiohttp missing", "response": ""}
        try:
            async with aiohttp.ClientSession() as session:
                payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False}
                async with session.post(f"{self.ollama_host}/api/chat", json=payload, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {"response": data.get("message", {}).get("content", ""), "model": model}
                    return {"error": f"HTTP {resp.status}", "response": ""}
        except Exception as e:
            return {"error": str(e), "response": ""}


