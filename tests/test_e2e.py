"""End-to-end smoke test: full pipeline with mocked LLM calls."""
import json
import pytest
from unittest.mock import MagicMock, patch
from novel_pipeline.orchestrator import Orchestrator
from novel_pipeline.models import (
    WorldBible, CharacterProfile, CharacterState,
    ConstraintBox,
    CharacterLine, DirectorVerdict, StateChangeProposal, CriticReport, Manuscript,
)


def _make_verdict(exit_reached: bool = False, speaker: str = "c1") -> DirectorVerdict:
    return DirectorVerdict(
        off_track=False,
        required_events_progress=[],
        exit_state_reached=exit_reached,
        hint=None,
        rejected=False,
        rejection_reason=None,
        next_speaker_id=speaker,
    )


@pytest.fixture
def config_file(tmp_path):
    f = tmp_path / "config.yaml"
    f.write_text("""
llm:
  model: claude-sonnet-4-6
  temperature_creative: 0.9
  temperature_structured: 0.2
  max_tokens: 4096
  max_retries: 3
pipeline:
  max_turns_per_scene: 5
  max_rollbacks_per_scene: 1
  target_words: 500
db:
  path: ":memory:"
""")
    return str(f)


def test_full_pipeline_smoke(config_file):
    """Full pipeline runs all three stages and produces a manuscript."""
    wb = WorldBible(setting="唐代长安", rules=["武功可以习得"], key_facts=["皇帝失踪"])
    chars = [
        CharacterProfile(id="c1", name="李青", persona="侠客", voice="豪放", arc="迷茫→觉醒"),
        CharacterProfile(id="c2", name="王芳", persona="谋士", voice="沉稳", arc="忠诚→怀疑"),
    ]
    scene = ConstraintBox(
        scene_id="s1", chapter_id="ch1",
        entry_state="二人相遇于长安城门",
        exit_state="决定合作追查皇帝失踪",
        required_events=["交换情报"],
        present_character_ids=["c1", "c2"],
        location="长安城门",
        order_idx=1,
    )

    with patch("novel_pipeline.orchestrator.LLMClient") as MockLLM, \
         patch("novel_pipeline.orchestrator.PrewritingModule") as MockPre, \
         patch("novel_pipeline.orchestrator.Outliner") as MockOut, \
         patch("novel_pipeline.orchestrator.SceneRunner") as MockRunner:

        MockPre.return_value.run.return_value = (wb, chars)
        MockOut.return_value.run.return_value = [scene]
        MockRunner.return_value.run_scene.return_value = Manuscript(
            scene_id="s1",
            prose="李青与王芳在城门前相遇，交换了关于皇帝失踪的情报，决定联手追查真相。",
            word_count=30,
        )

        orch = Orchestrator(config_path=config_file)
        orch.run(premise="皇帝神秘失踪，两位侠士联手追查", num_characters=2)

        MockPre.return_value.run.assert_called_once_with(
            premise="皇帝神秘失踪，两位侠士联手追查", num_characters=2
        )
        MockOut.return_value.run.assert_called_once()
        MockRunner.return_value.run_scene.assert_called_once_with("s1")


def test_validate_gate_blocks_direct_writes(config_file):
    """LLM cannot write to DB directly — only via validate_and_apply."""
    from novel_pipeline.persistence import Persistence, ValidationError
    db = Persistence(":memory:")

    from novel_pipeline.models import StateChangeProposal, StateChangeItem
    db.save_world_bible(WorldBible(setting="古代", rules=[], key_facts=[]))
    db.save_character(CharacterProfile(id="c1", name="张三", persona="x", voice="y", arc="a→b"))
    db.init_character_state(CharacterState(char_id="c1", location="村口", emotional_state="平静", status="alive"))

    with pytest.raises(ValidationError):
        db.validate_and_apply(StateChangeProposal(changes=[
            StateChangeItem(target="c1", field="nonexistent_field", op="set", value="x", reason="hack")
        ]))

    with pytest.raises(ValidationError):
        db.validate_and_apply(StateChangeProposal(changes=[
            StateChangeItem(target="nonexistent_char", field="location", op="set", value="x", reason="hack")
        ]))


def test_information_gap_between_characters(config_file):
    """Knowledge added for one character is invisible to others."""
    from novel_pipeline.persistence import Persistence
    from novel_pipeline.models import StateChangeProposal, StateChangeItem
    db = Persistence(":memory:")
    db.save_world_bible(WorldBible(setting="古代", rules=[], key_facts=[]))
    for cid, name in [("c1", "甲"), ("c2", "乙")]:
        db.save_character(CharacterProfile(id=cid, name=name, persona="x", voice="y", arc="a→b"))
        db.init_character_state(CharacterState(char_id=cid, location="村口", emotional_state="平静", status="alive"))

    db.validate_and_apply(StateChangeProposal(changes=[
        StateChangeItem(target="c1", field="knowledge", op="add", value="密道入口在东墙", reason="发现")
    ]))

    assert "密道入口在东墙" in db.get_character_knowledge("c1")
    assert "密道入口在东墙" not in db.get_character_knowledge("c2")


def test_status_reflects_pipeline_state(config_file):
    """Status command returns correct stage before any run."""
    with patch("novel_pipeline.orchestrator.LLMClient"):
        orch = Orchestrator(config_path=config_file)
        status = orch.status()
        assert status["stage"] == "INIT"
        assert status["scenes_total"] == 0
        assert status["scenes_done"] == 0
        assert status["latest_checkpoint"] is None
