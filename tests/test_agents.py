import pytest
from unittest.mock import MagicMock
from novel_pipeline.agents.character import CharacterAgent
from novel_pipeline.agents.director import DirectorAgent
from novel_pipeline.agents.drafter import Drafter
from novel_pipeline.models import (
    CharacterProfile, CharacterState, WorldBible, ConstraintBox,
    ContextPackage, CharacterLine, DirectorVerdict, SceneTranscriptEntry,
)


def _ctx():
    return ContextPackage(
        character=CharacterProfile(id="c1", name="张三", persona="勇敢", voice="直接", arc="a→b"),
        character_state=CharacterState(char_id="c1", location="村口", emotional_state="紧张", status="alive"),
        knowledge=["秘密X"],
        constraint_box=ConstraintBox(
            scene_id="s1", chapter_id="ch1",
            entry_state="初始", exit_state="危机解决",
            required_events=["发现秘密"],
            present_character_ids=["c1", "c2"],
            location="广场", order_idx=1,
        ),
        transcript=[],
        relevant_prose=[],
        world_bible=WorldBible(setting="古代", rules=[], key_facts=[]),
    )


def test_character_agent_returns_line():
    llm = MagicMock()
    llm.call_prose.return_value = "我知道真相！"
    agent = CharacterAgent(llm=llm)
    line = agent.act(_ctx())
    assert isinstance(line, CharacterLine)
    assert line.speaker_id == "c1"
    assert line.content == "我知道真相！"


def test_director_review_returns_verdict():
    llm = MagicMock()
    llm.call_structured.return_value = DirectorVerdict(
        off_track=False,
        required_events_progress=["发现秘密"],
        exit_state_reached=False,
        hint=None,
        rejected=False,
        rejection_reason=None,
        next_speaker_id="c2",
    )
    agent = DirectorAgent(llm=llm)
    box = _ctx().constraint_box
    line = CharacterLine(speaker_id="c1", content="我知道真相！")
    verdict = agent.review(line=line, transcript=[], box=box)
    assert isinstance(verdict, DirectorVerdict)
    assert verdict.next_speaker_id == "c2"


def test_director_review_first_turn_no_line():
    llm = MagicMock()
    llm.call_structured.return_value = DirectorVerdict(
        off_track=False, required_events_progress=[],
        exit_state_reached=False, hint=None,
        rejected=False, rejection_reason=None, next_speaker_id="c1",
    )
    agent = DirectorAgent(llm=llm)
    box = _ctx().constraint_box
    verdict = agent.review(line=None, transcript=[], box=box)
    assert verdict.next_speaker_id == "c1"


def test_drafter_returns_prose():
    llm = MagicMock()
    llm.call_prose.return_value = "从前有座山，山里有座庙。"
    drafter = Drafter(llm=llm)
    box = _ctx().constraint_box
    transcript = [SceneTranscriptEntry(scene_id="s1", turn=0, speaker_id="c1", content="我来了")]
    prose = drafter.draft(transcript=transcript, box=box, target_words=500)
    assert prose == "从前有座山，山里有座庙。"
