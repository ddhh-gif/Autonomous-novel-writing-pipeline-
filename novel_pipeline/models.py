from __future__ import annotations
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class CharacterProfile(BaseModel):
    id: str
    name: str
    persona: str
    voice: str
    arc: str


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
