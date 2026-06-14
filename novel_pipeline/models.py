from __future__ import annotations
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class Background(BaseModel):
    """人物背景模块。所有字段可选，留空则由 LLM 自动生成。"""
    origin: str | None = None           # 出身 / 籍贯 / 家庭
    occupation: str | None = None       # 职业 / 身份
    formative_events: list[str] = Field(default_factory=list)  # 塑造性格的关键经历
    secrets: list[str] = Field(default_factory=list)           # 不愿示人的秘密

    def is_empty(self) -> bool:
        return not (self.origin or self.occupation
                    or self.formative_events or self.secrets)


class SpeechStyle(BaseModel):
    """语言风格模块。控制角色的措辞与语感。"""
    language_register: str | None = None  # 语域：口语 / 正式 / 书面 / 市井…
    sentence_length: str | None = None    # 句长偏好：短促 / 绵长…
    vocabulary: str | None = None         # 用词偏好
    dialect_accent: str | None = None     # 方言 / 口音
    catchphrases: list[str] = Field(default_factory=list)  # 口头禅
    verbal_tics: str | None = None        # 语言习惯（如说话前停顿）

    def is_empty(self) -> bool:
        return not (self.language_register or self.sentence_length or self.vocabulary
                    or self.dialect_accent or self.catchphrases or self.verbal_tics)


class DialogueMode(BaseModel):
    """对话模式模块。控制角色在交流中的姿态与互动手法。"""
    assertiveness: str | None = None        # 强势 / 含蓄
    directness: str | None = None           # 直接 / 迂回
    humor: str | None = None                # 幽默感
    emotional_expression: str | None = None # 情绪外露程度
    interaction_patterns: list[str] = Field(default_factory=list)  # 惯用互动手法
    taboo_topics: list[str] = Field(default_factory=list)          # 回避话题

    def is_empty(self) -> bool:
        return not (self.assertiveness or self.directness or self.humor
                    or self.emotional_expression or self.interaction_patterns
                    or self.taboo_topics)


class CharacterProfile(BaseModel):
    id: str
    name: str
    persona: str
    voice: str
    arc: str
    # 可设计的扩展模块，均可选；留空由 prewriting 阶段自动补全。
    background: Background | None = None
    speech_style: SpeechStyle | None = None
    dialogue_mode: DialogueMode | None = None

    def missing_modules(self) -> list[str]:
        """返回需要自动补全的模块名（None 或全空都算缺失）。"""
        missing = []
        if self.background is None or self.background.is_empty():
            missing.append("background")
        if self.speech_style is None or self.speech_style.is_empty():
            missing.append("speech_style")
        if self.dialogue_mode is None or self.dialogue_mode.is_empty():
            missing.append("dialogue_mode")
        return missing


class WorldBible(BaseModel):
    setting: str
    rules: list[str]
    key_facts: list[str]


class ActBeat(BaseModel):
    act_number: int
    title: str
    description: str
    turning_point: str


class Chapter(BaseModel):
    id: str
    act_number: int
    goal: str
    present_character_ids: list[str]
    location: str
    order_idx: int


class ConstraintBox(BaseModel):
    scene_id: str
    chapter_id: str
    entry_state: str
    exit_state: str
    required_events: list[str]
    present_character_ids: list[str]
    location: str
    pov: str | None = None
    order_idx: int


class CharacterState(BaseModel):
    char_id: str
    location: str
    emotional_state: str
    status: str = "alive"


class StateChangeItem(BaseModel):
    target: str
    field: str
    op: Literal["set", "add", "remove"]
    value: str
    reason: str


class StateChangeProposal(BaseModel):
    changes: list[StateChangeItem]


class SceneTranscriptEntry(BaseModel):
    scene_id: str
    turn: int
    speaker_id: str
    content: str
    action_type: str = "speech"
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class Manuscript(BaseModel):
    scene_id: str
    prose: str
    word_count: int
    version: int = 1


class CheckpointRecord(BaseModel):
    id: str
    stage: str
    scene_id: str | None
    state_snapshot: dict
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class DirectorVerdict(BaseModel):
    off_track: bool
    required_events_progress: list[str]
    exit_state_reached: bool
    hint: str | None
    rejected: bool
    rejection_reason: str | None
    next_speaker_id: str


class CriticIssue(BaseModel):
    severity: Literal["warn", "revise", "rollback"]
    description: str
    location: str | None = None


class CriticReport(BaseModel):
    issues: list[CriticIssue]
    passed: bool


class CharacterLine(BaseModel):
    speaker_id: str
    content: str
    action_type: str = "speech"


class ContextPackage(BaseModel):
    character: CharacterProfile
    character_state: CharacterState
    knowledge: list[str]
    constraint_box: ConstraintBox
    transcript: list[SceneTranscriptEntry]
    relevant_prose: list[str]
    world_bible: WorldBible
    director_hint: str | None = None
