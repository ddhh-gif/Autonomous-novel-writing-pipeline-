from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import yaml
from pydantic import BaseModel
from novel_pipeline.models import (
    CharacterProfile, CharacterState, WorldBible,
    Background, SpeechStyle, DialogueMode,
)
from novel_pipeline.persistence import Persistence
from novel_pipeline.llm import LLMClient
from novel_pipeline.prompts.loader import render


class _CharacterListResponse(BaseModel):
    characters: list[CharacterProfile]


class _EnrichResponse(BaseModel):
    """LLM 补全单个角色缺失项时返回的结构，全部可选。"""
    persona: str | None = None
    voice: str | None = None
    arc: str | None = None
    background: Background | None = None
    speech_style: SpeechStyle | None = None
    dialogue_mode: DialogueMode | None = None


@dataclass
class SyncReport:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    restored: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _needs_core(char: CharacterProfile) -> bool:
    return not (char.persona and char.voice and char.arc)


class CharactersLoader:
    """把「一人一档」YAML 目录与数据库对账，并按需自动补全角色设计模块。

    YAML 文件是可手动编辑的真相源；数据库是运行期缓存。
    """

    def __init__(
        self,
        llm: LLMClient,
        persistence: Persistence,
        characters_dir: str = "characters",
        auto_enrich: bool = True,
    ):
        self._llm = llm
        self._db = persistence
        self._dir = Path(characters_dir)
        self._auto_enrich = auto_enrich

    # ---------- 文件 IO ----------

    def load_seeds(self) -> list[CharacterProfile]:
        """读取 characters/ 目录下的角色 YAML 作为种子。

        宽容解析：缺失的核心字段以空串占位，留待自动补全。
        """
        if not self._dir.is_dir():
            return []
        seeds: list[CharacterProfile] = []
        for path in sorted([*self._dir.glob("*.yaml"), *self._dir.glob("*.yml")]):
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if not isinstance(raw, dict):
                continue
            raw.setdefault("id", path.stem)
            raw.setdefault("name", path.stem)
            for core in ("persona", "voice", "arc"):
                raw.setdefault(core, "")
            seeds.append(CharacterProfile(**raw))
        return seeds

    def write_back(self, char: CharacterProfile) -> Path:
        """把补全后的角色回写到 characters/<id>.yaml，供作者查看与微调。"""
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{char.id}.yaml"
        data = char.model_dump(exclude_none=True)
        path.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return path

    def delete_file(self, char_id: str) -> bool:
        for suffix in (".yaml", ".yml"):
            path = self._dir / f"{char_id}{suffix}"
            if path.exists():
                path.unlink()
                return True
        return False

    # ---------- 自动补全 ----------

    def _missing(self, char: CharacterProfile) -> list[str]:
        missing = char.missing_modules()
        if _needs_core(char):
            missing = ["core", *missing]
        return missing

    def enrich(
        self,
        char: CharacterProfile,
        premise: str | None,
        world_bible: WorldBible,
    ) -> CharacterProfile:
        """补全缺失的核心字段 / 背景 / 语言风格 / 对话模式。无缺失则原样返回。"""
        if not self._auto_enrich:
            return char
        missing = self._missing(char)
        if not missing:
            return char
        resp = self._llm.call_structured(
            system="你是小说角色设计专家。只返回JSON。",
            prompt=render(
                "prewriting_character_enrich.j2",
                character=char,
                world_bible=world_bible,
                premise=premise,
                missing=missing,
            ),
            response_model=_EnrichResponse,
        )
        # 直接取 resp 上的子模型实例（而非 model_dump 的 dict），避免反序列化丢类型。
        update = {f: v for f in _EnrichResponse.model_fields
                  if (v := getattr(resp, f)) is not None}
        return char.model_copy(update=update)

    def generate_batch(
        self, premise: str, world_bible: WorldBible, num_characters: int
    ) -> list[CharacterProfile]:
        resp = self._llm.call_structured(
            system="你是小说角色设计专家。只返回JSON。",
            prompt=render(
                "prewriting_character.j2",
                premise=premise,
                world_bible=world_bible,
                num_characters=num_characters,
            ),
            response_model=_CharacterListResponse,
        )
        return resp.characters

    # ---------- 高层流程 ----------

    def prepare_characters(
        self, premise: str, world_bible: WorldBible, num_characters: int
    ) -> list[CharacterProfile]:
        """prewriting 阶段调用：有种子文件则补全，否则整批生成；最后回写文件。"""
        seeds = self.load_seeds()
        if seeds:
            chars = [self.enrich(c, premise, world_bible) for c in seeds]
        else:
            chars = [
                self.enrich(c, premise, world_bible)
                for c in self.generate_batch(premise, world_bible, num_characters)
            ]
        for c in chars:
            self.write_back(c)
        return chars

    def sync(self, premise: str | None = None) -> SyncReport:
        """把 characters/ 目录的增 / 删 / 改对账进数据库。"""
        world_bible = self._db.get_world_bible()
        report = SyncReport()

        seeds = {c.id: c for c in self.load_seeds()}
        db_chars = {c.id: c for c in self._db.get_all_characters(include_removed=True)}

        for cid, seed in seeds.items():
            enriched = self.enrich(seed, premise, world_bible)
            self.write_back(enriched)
            if cid not in db_chars:
                self._db.save_character(enriched)
                self._db.init_character_state(CharacterState(
                    char_id=cid, location="未知", emotional_state="平静", status="alive",
                ))
                report.added.append(cid)
            else:
                self._db.save_character(enriched)
                if self._db.is_character_removed(cid):
                    self._db.set_character_removed(cid, False)
                    report.restored.append(cid)
                else:
                    report.updated.append(cid)

        for cid in db_chars:
            if cid in seeds or self._db.is_character_removed(cid):
                continue
            self._db.set_character_removed(cid, True)
            report.removed.append(cid)
            affected = [s.scene_id for s in self._db.get_all_scenes()
                        if cid in s.present_character_ids]
            if affected:
                report.warnings.append(
                    f"角色 {cid} 已移除，但仍出现在场景 {', '.join(affected)} 的出场名单中；"
                    "这些场景如尚未生成会受影响，请按需调整场景。"
                )
        return report

    def regen(self, char_id: str, premise: str | None = None) -> CharacterProfile:
        """重写某个角色：清空三个设计模块后重新自动生成并回写。"""
        world_bible = self._db.get_world_bible()
        char = self._db.get_character(char_id)
        char = char.model_copy(update={
            "background": None, "speech_style": None, "dialogue_mode": None,
        })
        # 强制走补全（即便全局关闭 auto_enrich，显式 regen 也应生成）。
        prev = self._auto_enrich
        self._auto_enrich = True
        try:
            char = self.enrich(char, premise, world_bible)
        finally:
            self._auto_enrich = prev
        self._db.save_character(char)
        self.write_back(char)
        return char
