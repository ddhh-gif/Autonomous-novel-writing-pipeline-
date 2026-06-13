from __future__ import annotations
import uuid
from novel_pipeline.models import (
    CharacterLine, SceneTranscriptEntry, StateChangeProposal, Manuscript, CheckpointRecord,
)
from novel_pipeline.persistence import Persistence, ValidationError
from novel_pipeline.llm import LLMClient
from novel_pipeline.context_manager import ContextManager
from novel_pipeline.agents.character import CharacterAgent
from novel_pipeline.agents.director import DirectorAgent
from novel_pipeline.agents.drafter import Drafter
from novel_pipeline.critic import Critic, Reviser
from novel_pipeline.config import PipelineConfig
from novel_pipeline.prompts.loader import render


def _extract_state_changes(llm: LLMClient, line: CharacterLine, box_char_ids: list[str]) -> StateChangeProposal:
    prompt = render(
        "state_extract.j2",
        speaker_id=line.speaker_id,
        content=line.content,
        present_character_ids=box_char_ids,
    )
    system = "你是状态追踪助手。只返回JSON，无其他内容。"
    return llm.call_structured(system=system, prompt=prompt, response_model=StateChangeProposal)


class SceneRunner:
    def __init__(
        self,
        persistence: Persistence,
        llm: LLMClient,
        context_manager: ContextManager,
        character_agent: CharacterAgent,
        director: DirectorAgent,
        drafter: Drafter,
        critic: Critic,
        reviser: Reviser,
        config: PipelineConfig,
    ):
        self._db = persistence
        self._llm = llm
        self._cm = context_manager
        self._char_agent = character_agent
        self._director = director
        self._drafter = drafter
        self._critic = critic
        self._reviser = reviser
        self._cfg = config

    def run_scene(self, scene_id: str) -> Manuscript:
        box = self._db.get_scene(scene_id)
        transcript: list[SceneTranscriptEntry] = []
        completed_events: list[str] = []
        turn = 0

        verdict = self._director.review(line=None, transcript=transcript, box=box)

        while not verdict.exit_state_reached and turn < self._cfg.max_turns_per_scene:
            speaker_id = verdict.next_speaker_id
            ctx = self._cm.assemble(
                speaker_id=speaker_id,
                scene_id=scene_id,
                director_hint=verdict.hint,
            )
            line = self._char_agent.act(ctx)

            retries = 0
            while retries < 2:
                verdict = self._director.review(line=line, transcript=transcript, box=box)
                if not verdict.rejected:
                    break
                ctx = self._cm.assemble(
                    speaker_id=speaker_id,
                    scene_id=scene_id,
                    director_hint=verdict.hint,
                )
                line = self._char_agent.act(ctx)
                retries += 1

            entry = SceneTranscriptEntry(
                scene_id=scene_id,
                turn=turn,
                speaker_id=line.speaker_id,
                content=line.content,
                action_type=line.action_type,
            )
            transcript.append(entry)
            self._db.append_transcript(entry)
            completed_events.extend(verdict.required_events_progress)

            proposal = _extract_state_changes(self._llm, line, box.present_character_ids)
            try:
                self._db.validate_and_apply(proposal)
            except ValidationError:
                pass

            self._db.save_checkpoint(CheckpointRecord(
                id=str(uuid.uuid4()),
                stage="SCENE_LOOP",
                scene_id=scene_id,
                state_snapshot=self._db.take_state_snapshot(),
            ))
            turn += 1

        if turn >= self._cfg.max_turns_per_scene and not verdict.exit_state_reached:
            forced = self._director.force_resolution(transcript, box, completed_events)
            entry = SceneTranscriptEntry(
                scene_id=scene_id, turn=turn,
                speaker_id="narrator", content=forced,
            )
            transcript.append(entry)
            self._db.append_transcript(entry)

        words_target = self._cfg.target_words // max(1, len(self._db.get_all_scenes()))
        prose = self._drafter.draft(transcript=transcript, box=box, target_words=words_target)

        report = self._critic.check(prose=prose, state_snapshot=self._db.take_state_snapshot())
        for issue in report.issues:
            if issue.severity == "rollback":
                raise RuntimeError(f"Critic rollback: {issue.description}")
            elif issue.severity == "revise":
                prose = self._reviser.revise(prose=prose, issue=issue)

        manuscript = Manuscript(scene_id=scene_id, prose=prose, word_count=len(prose))
        self._db.save_manuscript(manuscript)
        return manuscript
