from __future__ import annotations
import json
import os
import re
from typing import TypeVar, Type, Callable
from pydantic import BaseModel
from novel_pipeline.config import LLMConfig

T = TypeVar("T", bound=BaseModel)


class LLMParseError(Exception):
    pass


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


class LLMClient:
    def __init__(self, config: LLMConfig):
        self._cfg = config
        if config.backend not in ("anthropic", "openai", "openai_compat"):
            raise ValueError(
                f"Unknown backend: {config.backend!r}. Use 'anthropic', 'openai', or 'openai_compat'."
            )
        # 底层 SDK client 惰性创建：仅在真正调用 LLM 时才需要 API key，
        # 这样无需调用模型的命令（如 characters list / sync）不会因缺 key 而崩溃。
        self._call_raw: Callable[[str, str, float], str] | None = None

    def _ensure_client(self) -> Callable[[str, str, float], str]:
        if self._call_raw is not None:
            return self._call_raw
        config = self._cfg

        if config.backend == "anthropic":
            import anthropic
            _client = anthropic.Anthropic(
                api_key=os.environ.get(config.api_key_env, ""),
            )

            def _call_anthropic(system: str, prompt: str, temperature: float) -> str:
                msg = _client.messages.create(
                    model=config.model,
                    max_tokens=config.max_tokens,
                    temperature=temperature,
                    system=system,
                    messages=[{"role": "user", "content": prompt}],
                )
                return msg.content[0].text

            self._call_raw = _call_anthropic
        else:
            from openai import OpenAI
            kwargs: dict = {"api_key": os.environ.get(config.api_key_env, "")}
            if config.base_url:
                kwargs["base_url"] = config.base_url
            _client = OpenAI(**kwargs)

            def _call_openai(system: str, prompt: str, temperature: float) -> str:
                msg = _client.chat.completions.create(
                    model=config.model,
                    max_tokens=config.max_tokens,
                    temperature=temperature,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                )
                return msg.choices[0].message.content or ""

            self._call_raw = _call_openai

        return self._call_raw

    def call_prose(self, system: str, prompt: str) -> str:
        return self._ensure_client()(system, prompt, self._cfg.temperature_creative)

    def call_structured(self, system: str, prompt: str, response_model: Type[T]) -> T:
        call_raw = self._ensure_client()
        structured_system = system + "\n\n只返回JSON，无前后缀，无markdown围栏。"
        last_err: Exception | None = None
        for _ in range(self._cfg.max_retries):
            raw = call_raw(structured_system, prompt, self._cfg.temperature_structured)
            try:
                return response_model.model_validate(json.loads(_strip_fences(raw)))
            except Exception as e:
                last_err = e
        raise LLMParseError(f"Failed after {self._cfg.max_retries} retries: {last_err}")
