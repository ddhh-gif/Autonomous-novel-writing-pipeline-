from __future__ import annotations
from novel_pipeline.config import load_config
from novel_pipeline.persistence import Persistence
from novel_pipeline.llm import LLMClient
from novel_pipeline.context_manager import ContextManager
from novel_pipeline.agents.character import CharacterAgent
from novel_pipeline.agents.director import DirectorAgent
from novel_pipeline.agents.drafter import Drafter
from novel_pipeline.critic import Critic, Reviser
from novel_pipeline.prewriting import PrewritingModule
from novel_pipeline.characters_loader import CharactersLoader, SyncReport
from novel_pipeline.outliner import Outliner
from novel_pipeline.scene_runner import SceneRunner


class Orchestrator:
    def __init__(self, config_path: str):
        self._cfg = load_config(config_path)
        self._db = Persistence(self._cfg.db.path)
        self._llm = LLMClient(self._cfg.llm)
        self._cm = ContextManager(self._db)
        char_agent = CharacterAgent(self._llm)
        director = DirectorAgent(self._llm)
        drafter = Drafter(self._llm)
        critic = Critic(self._llm)
        reviser = Reviser(self._llm)
        self._char_loader = CharactersLoader(
            llm=self._llm, persistence=self._db,
            characters_dir=self._cfg.pipeline.characters_dir,
            auto_enrich=self._cfg.pipeline.auto_enrich,
        )
        self._prewriting = PrewritingModule(self._llm, self._db, self._char_loader)
        self._outliner = Outliner(self._llm, self._db)
        self._runner = SceneRunner(
            persistence=self._db, llm=self._llm, context_manager=self._cm,
            character_agent=char_agent, director=director, drafter=drafter,
            critic=critic, reviser=reviser, config=self._cfg.pipeline,
        )

    def run(self, premise: str, num_characters: int = 4) -> None:
        cp = self._db.get_latest_checkpoint()
        stage = cp.stage if cp else "INIT"

        wb, chars, scenes = None, None, None
        if stage in ("INIT", "PREWRITING"):
            print("[1/3] Prewriting...")
            wb, chars = self._prewriting.run(premise=premise, num_characters=num_characters)
            stage = "OUTLINING"

        if stage == "OUTLINING":
            print("[2/3] Outlining...")
            if wb is None:
                wb = self._db.get_world_bible()
            if chars is None:
                chars = self._db.get_all_characters()
            scenes = self._outliner.run(premise=premise, world_bible=wb, characters=chars)
            stage = "SCENE_LOOP"

        if stage in ("SCENE_LOOP", "DONE"):
            if scenes is None:
                scenes = self._db.get_all_scenes()
            for i, scene in enumerate(scenes):
                if self._db.get_manuscript(scene.scene_id):
                    continue
                print(f"[3/3] Scene {i+1}/{len(scenes)}: {scene.scene_id}")
                rollback_count = 0
                while rollback_count <= self._cfg.pipeline.max_rollbacks_per_scene:
                    try:
                        self._runner.run_scene(scene.scene_id)
                        break
                    except RuntimeError as e:
                        rollback_count += 1
                        print(f"  Rollback {rollback_count}: {e}")
                        if rollback_count > self._cfg.pipeline.max_rollbacks_per_scene:
                            print(f"  Max rollbacks reached for scene {scene.scene_id}, skipping.")
                            break

        print("Done.")

    def rollback(self, checkpoint_id: str) -> None:
        self._db.restore_checkpoint(checkpoint_id)
        print(f"Restored checkpoint {checkpoint_id}")

    # ---------- 角色生命周期管理 ----------

    def characters_list(self) -> list[dict]:
        rows = []
        for c in self._db.get_all_characters(include_removed=True):
            rows.append({
                "id": c.id,
                "name": c.name,
                "removed": self._db.is_character_removed(c.id),
                "modules_filled": [m for m in ("background", "speech_style", "dialogue_mode")
                                   if m not in c.missing_modules()],
            })
        return rows

    def characters_sync(self, premise: str | None = None) -> SyncReport:
        return self._char_loader.sync(premise=premise)

    def characters_regen(self, char_id: str, premise: str | None = None):
        return self._char_loader.regen(char_id, premise=premise)

    def status(self) -> dict:
        cp = self._db.get_latest_checkpoint()
        scenes = self._db.get_all_scenes()
        done = [s for s in scenes if self._db.get_manuscript(s.scene_id)]
        return {
            "stage": cp.stage if cp else "INIT",
            "latest_checkpoint": cp.id if cp else None,
            "scenes_total": len(scenes),
            "scenes_done": len(done),
        }
