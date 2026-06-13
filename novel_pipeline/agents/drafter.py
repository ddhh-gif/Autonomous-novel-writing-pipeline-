from __future__ import annotations
from novel_pipeline.models import SceneTranscriptEntry, ConstraintBox
from novel_pipeline.llm import LLMClient
from novel_pipeline.prompts.loader import render


class Drafter:
    def __init__(self, llm: LLMClient):
        self._llm = llm

    def draft(
        self,
        transcript: list[SceneTranscriptEntry],
        box: ConstraintBox,
        target_words: int = 1000,
    ) -> str:
        prompt = render("drafter.j2", transcript=transcript, box=box, target_words=target_words)
        system = "你是专业中文小说作家。直接输出散文正文，不加任何说明或前缀。"
        return self._llm.call_prose(system=system, prompt=prompt)
