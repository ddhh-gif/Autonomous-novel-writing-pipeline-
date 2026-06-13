from __future__ import annotations
from novel_pipeline.models import CharacterLine, SceneTranscriptEntry, ConstraintBox, DirectorVerdict
from novel_pipeline.llm import LLMClient
from novel_pipeline.prompts.loader import render


class DirectorAgent:
    def __init__(self, llm: LLMClient):
        self._llm = llm

    def review(
        self,
        line: CharacterLine | None,
        transcript: list[SceneTranscriptEntry],
        box: ConstraintBox,
    ) -> DirectorVerdict:
        prompt = render("director_review.j2", line=line, transcript=transcript, box=box)
        system = "你是小说导演，负责场景监控和节奏控制。只返回JSON。"
        return self._llm.call_structured(
            system=system, prompt=prompt, response_model=DirectorVerdict
        )

    def force_resolution(
        self,
        transcript: list[SceneTranscriptEntry],
        box: ConstraintBox,
        completed_events: list[str],
    ) -> str:
        pending = [e for e in box.required_events if e not in completed_events]
        prompt = render("director_force.j2", transcript=transcript, box=box, pending_events=pending)
        system = "你是导演，需要强制推进情节至退出状态。"
        return self._llm.call_prose(system=system, prompt=prompt)
