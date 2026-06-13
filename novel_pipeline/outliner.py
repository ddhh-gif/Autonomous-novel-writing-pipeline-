from __future__ import annotations
from pydantic import BaseModel
from novel_pipeline.models import WorldBible, CharacterProfile, ActBeat, Chapter, ConstraintBox
from novel_pipeline.persistence import Persistence
from novel_pipeline.llm import LLMClient
from novel_pipeline.prompts.loader import render


class _ActsResponse(BaseModel):
    acts: list[ActBeat]


class _ChaptersResponse(BaseModel):
    chapters: list[Chapter]


class _ScenesResponse(BaseModel):
    scenes: list[ConstraintBox]


class Outliner:
    def __init__(self, llm: LLMClient, persistence: Persistence):
        self._llm = llm
        self._db = persistence

    def run(
        self,
        premise: str,
        world_bible: WorldBible,
        characters: list[CharacterProfile],
    ) -> list[ConstraintBox]:
        acts_resp = self._llm.call_structured(
            system="你是小说大纲策划专家。只返回JSON。",
            prompt=render("outliner_acts.j2", premise=premise, world_bible=world_bible, characters=characters),
            response_model=_ActsResponse,
        )
        for act in acts_resp.acts:
            self._db.save_act(act)

        all_scenes: list[ConstraintBox] = []
        order = 1
        for act in acts_resp.acts:
            ch_resp = self._llm.call_structured(
                system="你是小说章节规划师。只返回JSON。",
                prompt=render("outliner_chapters.j2", act=act, characters=characters),
                response_model=_ChaptersResponse,
            )
            for ch in ch_resp.chapters:
                ch.order_idx = order
                self._db.save_chapter(ch)
                sc_resp = self._llm.call_structured(
                    system="你是场景设计师。只返回JSON。",
                    prompt=render("outliner_scenes.j2", chapter=ch),
                    response_model=_ScenesResponse,
                )
                for scene in sc_resp.scenes:
                    scene.order_idx = order
                    self._db.save_scene(scene)
                    all_scenes.append(scene)
                    order += 1
        return all_scenes
