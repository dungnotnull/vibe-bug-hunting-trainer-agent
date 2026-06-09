"""LLM client for mutation generation.

Supports local Ollama (default) and external APIs (Claude, GPT, Gemini).
Handles retry logic, fallback chains, and response parsing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

import httpx
from loguru import logger

from bughunter.core.config import Config


@dataclass
class LLMResponse:
    content: str
    model: str
    provider: str
    tokens_used: int = 0
    latency_ms: float = 0.0


@dataclass
class LLMConfig:
    provider: str = "ollama"
    model: str = "qwen2.5-coder:7b"
    base_url: str = "http://localhost:11434"
    api_key: str = ""
    temperature: float = 0.4
    max_tokens: int = 2000
    timeout: float = 60.0


class LLMClient:
    """Multi-provider LLM client for bug mutation generation."""

    def __init__(self, config: Config):
        self._config = config
        self._local_config = LLMConfig(
            provider="ollama",
            model=config.local_model,
            base_url="http://localhost:11434",
            temperature=0.4,
            max_tokens=2000,
        )
        self._external_config: Optional[LLMConfig] = None
        if config.external_llm_provider:
            self._external_config = LLMConfig(
                provider=config.external_llm_provider,
                model=config.external_llm_model,
                api_key=config.external_llm_api_key,
                temperature=0.5,
                max_tokens=2000,
            )
        self._client = httpx.Client(timeout=httpx.Timeout(self._local_config.timeout))

    def generate(
        self,
        prompt: str,
        use_external: bool = False,
        retries: int = 3,
    ) -> LLMResponse:
        """Generate text from the configured LLM."""
        if use_external and self._external_config:
            return self._try_generate(self._external_config, prompt, retries)
        return self._try_generate(self._local_config, prompt, retries)

    def _try_generate(
        self, llm_cfg: LLMConfig, prompt: str, retries: int
    ) -> LLMResponse:
        last_error = None
        for attempt in range(retries):
            try:
                if llm_cfg.provider == "ollama":
                    return self._ollama_generate(llm_cfg, prompt)
                elif llm_cfg.provider in ("claude", "anthropic"):
                    return self._anthropic_generate(llm_cfg, prompt)
                elif llm_cfg.provider == "openai":
                    return self._openai_generate(llm_cfg, prompt)
                elif llm_cfg.provider == "gemini":
                    return self._gemini_generate(llm_cfg, prompt)
                else:
                    raise ValueError(f"Unknown provider: {llm_cfg.provider}")
            except Exception as e:
                last_error = e
                logger.warning(f"LLM attempt {attempt + 1}/{retries} failed: {e}")
        raise RuntimeError(f"LLM generation failed after {retries} attempts: {last_error}")

    def _ollama_generate(self, cfg: LLMConfig, prompt: str) -> LLMResponse:
        import time
        start = time.time()
        url = f"{cfg.base_url}/api/generate"
        payload = {
            "model": cfg.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": cfg.temperature,
                "num_predict": cfg.max_tokens,
            },
        }
        resp = self._client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return LLMResponse(
            content=data.get("response", ""),
            model=cfg.model,
            provider="ollama",
            tokens_used=data.get("eval_count", 0),
            latency_ms=(time.time() - start) * 1000,
        )

    def _anthropic_generate(self, cfg: LLMConfig, prompt: str) -> LLMResponse:
        import time
        start = time.time()
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": cfg.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": cfg.model,
            "max_tokens": cfg.max_tokens,
            "temperature": cfg.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        resp = self._client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        content = "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        )
        return LLMResponse(
            content=content,
            model=cfg.model,
            provider="anthropic",
            tokens_used=data.get("usage", {}).get("output_tokens", 0),
            latency_ms=(time.time() - start) * 1000,
        )

    def _openai_generate(self, cfg: LLMConfig, prompt: str) -> LLMResponse:
        import time
        start = time.time()
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {cfg.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": cfg.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": cfg.temperature,
            "max_tokens": cfg.max_tokens,
        }
        resp = self._client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return LLMResponse(
            content=data["choices"][0]["message"]["content"],
            model=cfg.model,
            provider="openai",
            tokens_used=data.get("usage", {}).get("completion_tokens", 0),
            latency_ms=(time.time() - start) * 1000,
        )

    def _gemini_generate(self, cfg: LLMConfig, prompt: str) -> LLMResponse:
        import time
        start = time.time()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{cfg.model}:generateContent"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": cfg.temperature,
                "maxOutputTokens": cfg.max_tokens,
            },
        }
        resp = self._client.post(f"{url}?key={cfg.api_key}", json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        content = ""
        for candidate in data.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                content += part.get("text", "")
        return LLMResponse(
            content=content,
            model=cfg.model,
            provider="gemini",
            latency_ms=(time.time() - start) * 1000,
        )

    def generate_mutation(
        self,
        category: str,
        language: str,
        original_code: str,
        line_start: int,
        line_end: int,
        context: str = "",
    ) -> str:
        """Generate a bug mutation for a specific code snippet."""
        prompt = self._build_mutation_prompt(
            category, language, original_code, line_start, line_end, context
        )
        response = self.generate(prompt, use_external=False)
        mutation = self._extract_code_block(response.content, language)
        if not mutation:
            logger.warning("LLM returned no code block, using raw response")
            mutation = response.content
        return mutation

    def _build_mutation_prompt(
        self,
        category: str,
        language: str,
        original_code: str,
        line_start: int,
        line_end: int,
        context: str,
    ) -> str:
        return f"""You are an expert at creating realistic, subtle software bugs for training purposes.

TASK: Inject a SINGLE subtle bug into the following {language} code.
The bug must:
1. Be in the {category} category
2. NOT cause syntax errors or crash the program
3. Pass all existing linter and type-checker checks
4. Look like a mistake a real developer would make
5. Produce subtly wrong behavior that requires debugging to find

CODE TO MUTATE (lines {line_start}-{line_end}):
```{language}
{original_code}
```

CONTEXT: {context if context else "No additional context"}

Return ONLY the modified code block with the injected bug. Keep the same structure.
Do NOT add comments or explanations. Do NOT mark the bug location."""

    def _extract_code_block(self, text: str, language: str) -> str:
        patterns = [
            rf"```{language}\s*\n(.*?)```",
            rf"```\s*\n(.*?)```",
            r"```(.*?)```",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                return match.group(1).strip()
        if language == "python" and ("def " in text or "import " in text):
            return text.strip()
        if "function" in text.lower() or "const " in text:
            return text.strip()
        return ""

    def score_realism(self, original: str, mutated: str, language: str) -> float:
        """Use LLM to score the realism of a generated mutation."""
        prompt = f"""Rate how realistic this software bug is on a scale of 0.0 to 1.0.

Original {language} code:
```{language}
{original}
```

Buggy version:
```{language}
{mutated}
```

Consider: Would a real developer write this mistake? Is it subtle or obvious?
Does it look accidental or intentional?

Respond with ONLY a number between 0.0 and 1.0, nothing else."""
        response = self.generate(prompt, use_external=False)
        try:
            numbers = re.findall(r"(\d+\.?\d*)", response.content)
            if numbers:
                return min(1.0, max(0.0, float(numbers[0])))
        except ValueError:
            pass
        return 0.5

    def close(self):
        self._client.close()
