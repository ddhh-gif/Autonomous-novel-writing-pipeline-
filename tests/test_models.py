import pytest
from novel_pipeline.models import (
    CharacterProfile, WorldBible, ActBeat, Chapter, ConstraintBox,
    CharacterState, StateChangeItem, StateChangeProposal,
    DirectorVerdict, CriticIssue, CriticReport, CharacterLine,
    ContextPackage, SceneTranscriptEntry, Manuscript, CheckpointRecord,
)


def test_character_profile_requires_all_fields():
    with pytest.raises(Exception):
        CharacterProfile(id="c1", name="张三")  # missing persona, voice, arc


def test_character_profile_valid():
    c = CharacterProfile(id="c1", name="张三", persona="好奇", voice="直接", arc="懦弱→勇敢")
    assert c.id == "c1"


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
