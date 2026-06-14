from __future__ import annotations
from novel_pipeline.models import WorldBible, CharacterProfile, CharacterState
from novel_pipeline.persistence import Persistence
from novel_pipeline.llm import LLMClient
from novel_pipeline.characters_loader import CharactersLoader
from novel_pipeline.prompts.loader import render


class PrewritingModule:
    def __init__(
        self,
        llm: LLMClient,
        persistence: Persistence,
        characters_loader: CharactersLoader | None = None,
    ):
        self._llm = llm
        self._db = persistence
        # 默认 loader：无 YAML 种子时退回整批生成的行为。
        self._loader = characters_loader or CharactersLoader(llm, persistence)

    def run(self, premise: str, num_characters: int) -> tuple[WorldBible, list[CharacterProfile]]:
        world_bible = self._llm.call_structured(
            system="你是小说世界设定专家。只返回JSON。",
            prompt=render("prewriting_world.j2", premise=premise),
            response_model=WorldBible,
        )
        self._db.save_world_bible(world_bible)

        characters = self._loader.prepare_characters(
            premise=premise, world_bible=world_bible, num_characters=num_characters,
        )
        for char in characters:
            self._db.save_character(char)
            self._db.init_character_state(
                CharacterState(
                    char_id=char.id,
                    location="未知",
                    emotional_state="平静",
                    status="alive",
                )
            )
        return world_bible, characters
