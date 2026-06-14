import pytest
from novel_pipeline.models import (
    CharacterProfile, WorldBible, ActBeat, Chapter, ConstraintBox,
    CharacterState, StateChangeItem, StateChangeProposal,
    DirectorVerdict, CriticIssue, CriticReport, CharacterLine,
    ContextPackage, SceneTranscriptEntry, Manuscript, CheckpointRecord,
    Background, SpeechStyle, DialogueMode,
)


def test_character_profile_requires_all_fields():
    with pytest.raises(Exception):
        CharacterProfile(id="c1", name="张三")  # missing persona, voice, arc


def test_character_profile_valid():
    c = CharacterProfile(id="c1", name="张三", persona="好奇", voice="直接", arc="懦弱→勇敢")
    assert c.id == "c1"


def test_character_profile_optional_modules_default_none():
    c = CharacterProfile(id="c1", name="张三", persona="p", voice="v", arc="a→b")
    assert c.background is None
    assert c.speech_style is None
    assert c.dialogue_mode is None


def test_missing_modules_reports_all_when_empty():
    c = CharacterProfile(id="c1", name="张三", persona="p", voice="v", arc="a→b")
    assert set(c.missing_modules()) == {"background", "speech_style", "dialogue_mode"}


def test_missing_modules_empty_submodel_counts_as_missing():
    c = CharacterProfile(
        id="c1", name="张三", persona="p", voice="v", arc="a→b",
        background=Background(),  # 全空
        speech_style=SpeechStyle(language_register="书面"),
    )
    assert "background" in c.missing_modules()
    assert "speech_style" not in c.missing_modules()


def test_character_profile_with_full_modules():
    c = CharacterProfile(
        id="c1", name="张三", persona="p", voice="v", arc="a→b",
        background=Background(occupation="侦探", secrets=["真名非张三"]),
        speech_style=SpeechStyle(language_register="冷峻", catchphrases=["线索不会撒谎。"]),
        dialogue_mode=DialogueMode(assertiveness="强势", interaction_patterns=["用反问代替回答"]),
    )
    assert c.missing_modules() == []
    assert c.background.secrets == ["真名非张三"]


def test_state_change_proposal_valid():
    p = StateChangeProposal(changes=[
        StateChangeItem(target="c1", field="knowledge", op="add", value="秘密X", reason="说漏嘴")
    ])
    assert len(p.changes) == 1


def test_state_change_op_enum():
    with pytest.raises(Exception):
        StateChangeItem(target="c1", field="knowledge", op="invalid", value="v", reason="r")


def test_director_verdict_has_next_speaker():
    v = DirectorVerdict(
        off_track=False,
        required_events_progress=[],
        exit_state_reached=False,
        hint=None,
        rejected=False,
        rejection_reason=None,
        next_speaker_id="c1",
    )
    assert v.next_speaker_id == "c1"


def test_critic_report_severity_enum():
    with pytest.raises(Exception):
        CriticIssue(severity="critical", description="bad")  # not in enum
