import pytest
from unittest.mock import MagicMock, patch
from novel_pipeline.orchestrator import Orchestrator


def test_orchestrator_runs_all_stages(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("""
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
    with patch("novel_pipeline.orchestrator.PrewritingModule") as MockPre, \
         patch("novel_pipeline.orchestrator.Outliner") as MockOut, \
         patch("novel_pipeline.orchestrator.SceneRunner") as MockRunner, \
         patch("novel_pipeline.orchestrator.LLMClient"):
        from novel_pipeline.models import WorldBible, CharacterProfile, ConstraintBox, Manuscript
        MockPre.return_value.run.return_value = (
            WorldBible(setting="古代", rules=[], key_facts=[]),
            [CharacterProfile(id="c1", name="张三", persona="x", voice="y", arc="a→b")],
        )
        MockOut.return_value.run.return_value = [
            ConstraintBox(
                scene_id="s1", chapter_id="ch1",
                entry_state="开始", exit_state="结束",
                required_events=[], present_character_ids=["c1"],
                location="广场", order_idx=1,
            )
        ]
        MockRunner.return_value.run_scene.return_value = Manuscript(
            scene_id="s1", prose="故事内容", word_count=4
        )
        orch = Orchestrator(config_path=str(cfg_file))
        orch.run(premise="测试故事", num_characters=1)
        MockPre.return_value.run.assert_called_once()
        MockOut.return_value.run.assert_called_once()
        MockRunner.return_value.run_scene.assert_called_once_with("s1")


def test_orchestrator_status(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("""
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
    with patch("novel_pipeline.orchestrator.LLMClient"):
        orch = Orchestrator(config_path=str(cfg_file))
        status = orch.status()
        assert "stage" in status
