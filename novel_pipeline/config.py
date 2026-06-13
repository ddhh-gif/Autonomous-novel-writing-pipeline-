from __future__ import annotations
from dataclasses import dataclass, field
import yaml


@dataclass
class LLMConfig:
    model: str = "claude-sonnet-4-6"
    temperature_creative: float = 0.9
    temperature_structured: float = 0.2
    max_tokens: int = 4096
    max_retries: int = 3


@dataclass
class PipelineConfig:
    max_turns_per_scene: int = 40
    max_rollbacks_per_scene: int = 3
    target_words: int = 20000


@dataclass
class DBConfig:
    path: str = "novel.db"


@dataclass
class AppConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    db: DBConfig = field(default_factory=DBConfig)


def load_config(path: str) -> AppConfig:
    with open(path) as f:
        raw = yaml.safe_load(f)
    cfg = AppConfig()
    if "llm" in raw:
        cfg.llm = LLMConfig(**raw["llm"])
    if "pipeline" in raw:
        cfg.pipeline = PipelineConfig(**raw["pipeline"])
    if "db" in raw:
        cfg.db = DBConfig(**raw["db"])
    return cfg
