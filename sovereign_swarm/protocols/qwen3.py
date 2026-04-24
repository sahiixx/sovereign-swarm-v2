from ..config import *

class Qwen3Router:
    THINKING_MODELS = ["qwen3:4b", "qwen3:7b", "qwen3:14b", "qwen3:30b"]
    NON_THINKING_SUFFIX = "-no-think"
    def __init__(self, default: str = "qwen3:4b"): self.default = default

    def route(self, prompt: str, complexity: str = "auto") -> Dict:
        if complexity == "auto":
            word_count = len(prompt.split())
            reasoning_keywords = ["analyze", "compare", "reason", "evaluate", "prove", "explain why"]
            complexity = "complex" if (word_count > 100 or any(kw in prompt.lower() for kw in reasoning_keywords)) else "simple"
        if complexity == "complex":
            return {"model": self.default, "thinking": True, "complexity": complexity}
        return {"model": f"{self.default}{self.NON_THINKING_SUFFIX}", "thinking": False, "complexity": complexity}

    def parse_thinking(self, response: str) -> Dict:
        think_blocks = re.findall(r"<think>(.*?)</think>", response, re.DOTALL)
        clean = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()
        return {"thinking_blocks": think_blocks, "clean_response": clean, "had_thinking": len(think_blocks) > 0}


