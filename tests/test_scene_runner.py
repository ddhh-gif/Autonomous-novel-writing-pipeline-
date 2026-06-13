import pytest
from unittest.mock import MagicMock
from novel_pipeline.scene_runner import SceneRunner
from novel_pipeline.persistence import Persistence
from novel_pipeline.context_manager import ContextManager
from novel_pipeline.config import PipelineConfig
from novel_pipeline.models import (
    CharacterProfile, WorldBible, CharacterState, ConstraintBox,
    CharacterLine, DirectorVerdict, CriticReport, StateChangeProposal,
    StateChangeItem,
)


@pytest.fixture
def db():
    p = Persistence(":memory:")
    p.save_world_bible(WorldBible(setting="古代", rules=[], key_facts=[]))
    for cid, name in [("c1", "张三"), ("c2", "李四")]:
        p.save_character(CharacterProfile(id=cid, name=name, persona="x", voice="y", arc="a→b"))
        p.init_character_state(CharacterState(char_id=cid, location="村口", emotional_state="平静", status="alive"))
    box = ConstraintBox(
        scene_id="s1", chapter_id="ch1",
        entry_state="初始", exit_state="达成目标",
        required_events=["发现线索"],
        present_character_ids=["c1", "c2"],
        location="广场", order_idx=1,
    )
    p.save_scene(box)
    return p


def _make_verdict(exit_reached=False, speaker="c1"):
    return DirectorVerdict(
        off_track=False, required_events_progress=[],
        exit_state_reached=exit_reached, hint=None,
        rejected=False, rejection_reason=None, next_speaker_id=speaker,
    )


def test_scene_runner_runs_to_exit_state(db):
    llm = MagicMock()
    char_agent = MagicMock()
    director = MagicMock()
    drafter = MagicMock()
    critic = MagicMock()
    reviser = MagicMock()

    char_agent.act.return_value = CharacterLine(speaker_id="c1", content="我发现了线索！")
    director.review.side_effect = [_make_verdict(False, "c2"), _make_verdict(True, "c1")]
    llm.call_structured.return_value = StateChangeProposal(changes=[])
    drafter.draft.return_value = "张三发现了线索，故事推进。"
    critic.check.return_value = CriticReport(issues=[], passed=True)

    cm = ContextManager(persistence=db)
    cfg = PipelineConfig(max_turns_per_scene=40, max_rollbacks_per_scene=3)
    runner = SceneRunner(
        persistence=db, llm=llm, context_manager=cm,
        character_agent=char_agent, director=director,
        drafter=drafter, critic=critic, reviser=reviser, config=cfg,
    )
    manuscript = runner.run_scene("s1")
    assert manuscript.prose == "张三发现了线索，故事推进。"
    assert db.get_manuscript("s1").prose == "张三发现了线索，故事推进。"


def test_information_gap_enforced(db):
    db.validate_and_apply(StateChangeProposal(changes=[
        StateChangeItem(target="c1", field="knowledge", op="add", value="c1的秘密", reason="test")
    ]))
    assert "c1的秘密" not in db.get_character_knowledge("c2")
