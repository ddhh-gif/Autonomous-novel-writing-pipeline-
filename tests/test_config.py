from novel_pipeline.config import load_config, AppConfig


def test_load_config_from_yaml(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("""
llm:
  model: claude-sonnet-4-6
  temperature_creative: 0.9
  temperature_structured: 0.2
  max_tokens: 4096
  max_retries: 3
pipeline:
  max_turns_per_scene: 40
  max_rollbacks_per_scene: 3
  target_words: 20000
db:
  path: novel.db
""")
    cfg = load_config(str(cfg_file))
    assert cfg.llm.model == "claude-sonnet-4-6"
    assert cfg.pipeline.max_turns_per_scene == 40
    assert cfg.db.path == "novel.db"


def test_config_defaults():
    cfg = AppConfig()
    assert cfg.llm.max_retries == 3
