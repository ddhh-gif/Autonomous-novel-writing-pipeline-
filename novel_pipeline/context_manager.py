from __future__ import annotations
from novel_pipeline.models import ContextPackage
from novel_pipeline.persistence import Persistence


class ContextManager:
    def __init__(self, persistence: Persistence):
        self._db = persistence

    def assemble(
        self,
        speaker_id: str,
        scene_id: str,
        director_hint: str | None = None,
    ) -> ContextPackage:
        character = self._db.get_character(speaker_id)
        character_state = self._db.get_character_state(speaker_id)
        knowledge = self._db.get_character_knowledge(speaker_id)
        constraint_box = self._db.get_scene(scene_id)
        transcript = self._db.get_transcript(scene_id)
        world_bible = self._db.get_world_bible()
        relevant_prose = self._db.search_fts(character.name, top_k=5)

        return ContextPackage(
            character=character,
            character_state=character_state,
            knowledge=knowledge,
            constraint_box=constraint_box,
            transcript=transcript,
            relevant_prose=relevant_prose,
            world_bible=world_bible,
            director_hint=director_hint,
        )
