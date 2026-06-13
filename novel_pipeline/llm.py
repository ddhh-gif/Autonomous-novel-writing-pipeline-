from __future__ import annotations
import json
import re
from typing import TypeVar, Type
import anthropic
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
        self._client = anthropic.Anthropic()

    def call_prose(self, system: str, prompt: str) -> str:
        msg = self._client.messages.create(
            model=self._cfg.model,
            max_tokens=self._cfg.max_tokens,
            temperature=self._cfg.temperature_creative,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text

    def call_structured(self, system: str, prompt: str, response_model: Type[T]) -> T:
        structured_system = system + "\n\n只返回JSON，无前后缀，无markdown围栏。"
        last_err: Exception | None = None
        for attempt in range(self._cfg.max_retries):
            msg = self._client.messages.create(
                model=self._cfg.model,
                max_tokens=self._cfg.max_tokens,
                temperature=self._cfg.temperature_structured,
                system=structured_system,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text
            try:
                cleaned = _strip_fences(raw)
                data = json.loads(cleaned)
                return response_model.model_validate(data)
            except Exception as e:
                last_err = e
        raise LLMParseError(f"Failed after {self._cfg.max_retries} retries: {last_err}")
