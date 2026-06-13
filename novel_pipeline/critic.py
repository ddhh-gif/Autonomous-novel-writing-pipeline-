from __future__ import annotations
from novel_pipeline.models import CriticReport, CriticIssue
from novel_pipeline.llm import LLMClient
from novel_pipeline.prompts.loader import render


class Critic:
    def __init__(self, llm: LLMClient):
        self._llm = llm

    def check(self, prose: str, state_snapshot: dict) -> CriticReport:
        char_states = state_snapshot.get("character_states", {})
        prompt = render("critic.j2", prose=prose, character_states=char_states)
        system = "你是严格的小说编辑。只返回JSON，无其他内容。"
        return self._llm.call_structured(
            system=system, prompt=prompt, response_model=CriticReport
        )


class Reviser:
    def __init__(self, llm: LLMClient):
        self._llm = llm

    def revise(self, prose: str, issue: CriticIssue) -> str:
        prompt = render("reviser.j2", prose=prose, issue=issue)
        system = "你是小说编辑，直接输出修订后的完整散文，不加任何说明。"
        return self._llm.call_prose(system=system, prompt=prompt)
