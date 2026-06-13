from __future__ import annotations
from novel_pipeline.models import ContextPackage, CharacterLine
from novel_pipeline.llm import LLMClient
from novel_pipeline.prompts.loader import render


class CharacterAgent:
    def __init__(self, llm: LLMClient):
        self._llm = llm

    def act(self, ctx: ContextPackage) -> CharacterLine:
        prompt = render(
            "character_agent.j2",
            character=ctx.character,
            character_state=ctx.character_state,
            knowledge=ctx.knowledge,
            constraint_box=ctx.constraint_box,
            transcript=ctx.transcript,
            director_hint=ctx.director_hint,
        )
        system = (
            f"你是小说角色「{ctx.character.name}」。"
            "只用第一人称说话，不要描述其他角色的反应，不要跳出角色。"
        )
        content = self._llm.call_prose(system=system, prompt=prompt)
        return CharacterLine(speaker_id=ctx.character.id, content=content)
