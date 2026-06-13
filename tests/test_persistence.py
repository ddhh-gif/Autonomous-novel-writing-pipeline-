import pytest
from novel_pipeline.persistence import Persistence, ValidationError
from novel_pipeline.models import (
    CharacterProfile, WorldBible, ActBeat, Chapter, ConstraintBox,
    CharacterState, StateChangeProposal, StateChangeItem,
    SceneTranscriptEntry, Manuscript, CheckpointRecord,
)


@pytest.fixture
def db():
    p = Persistence(":memory:")
    return p


def _char(id="c1"):
    return CharacterProfile(id=id, name="张三", persona="好奇心旺盛", voice="直接简短", arc="懦弱→勇敢")


def _state(char_id="c1"):
    return CharacterState(char_id=char_id, location="村口", emotional_state="紧张", status="alive")


def test_save_and_get_character(db):
    db.save_character(_char())
    result = db.get_character("c1")
    assert result.name == "张三"
    assert result.arc == "懦弱→勇敢"


def test_get_all_characters(db):
    db.save_character(_char("c1"))
    db.save_character(_char("c2"))
    assert len(db.get_all_characters()) == 2


def test_save_and_get_world_bible(db):
    wb = WorldBible(setting="架空古代", rules=["魔法存在"], key_facts=["王国内战"])
    db.save_world_bible(wb)
    result = db.get_world_bible()
    assert result.setting == "架空古代"
    assert "魔法存在" in result.rules


def test_init_and_get_character_state(db):
    db.save_character(_char())
    db.init_character_state(_state())
    s = db.get_character_state("c1")
    assert s.location == "村口"
    assert s.status == "alive"


def test_validate_and_apply_adds_knowledge(db):
    db.save_character(_char())
    db.init_character_state(_state())
    proposal = StateChangeProposal(changes=[
        StateChangeItem(target="c1", field="knowledge", op="add", value="秘密X", reason="得知")
    ])
    db.validate_and_apply(proposal)
    knowledge = db.get_character_knowledge("c1")
    assert "秘密X" in knowledge


def test_validate_and_apply_updates_state(db):
    db.save_character(_char())
    db.init_character_state(_state())
    proposal = StateChangeProposal(changes=[
        StateChangeItem(target="c1", field="location", op="set", value="城堡", reason="移动")
    ])
    db.validate_and_apply(proposal)
    assert db.get_character_state("c1").location == "城堡"


def test_validate_blocks_unknown_target(db):
    proposal = StateChangeProposal(changes=[
        StateChangeItem(target="nobody", field="knowledge", op="add", value="x", reason="test")
    ])
    with pytest.raises(ValidationError):
        db.validate_and_apply(proposal)


def test_validate_blocks_unknown_field(db):
    db.save_character(_char())
    db.init_character_state(_state())
    proposal = StateChangeProposal(changes=[
        StateChangeItem(target="c1", field="hair_color", op="set", value="red", reason="test")
    ])
    with pytest.raises(ValidationError):
        db.validate_and_apply(proposal)


def test_knowledge_information_gap(db):
    db.save_character(_char("c1"))
    db.save_character(_char("c2"))
    db.init_character_state(_state("c1"))
    db.init_character_state(_state("c2"))
    proposal = StateChangeProposal(changes=[
        StateChangeItem(target="c1", field="knowledge", op="add", value="c1的秘密", reason="自知")
    ])
    db.validate_and_apply(proposal)
    assert "c1的秘密" in db.get_character_knowledge("c1")
    assert "c1的秘密" not in db.get_character_knowledge("c2")


def test_transcript_append_and_get(db):
    entry = SceneTranscriptEntry(scene_id="s1", turn=0, speaker_id="c1", content="你好")
    db.append_transcript(entry)
    result = db.get_transcript("s1")
    assert len(result) == 1
    assert result[0].content == "你好"


def test_manuscript_save_and_get(db):
    m = Manuscript(scene_id="s1", prose="从前有座山", word_count=5)
    db.save_manuscript(m)
    result = db.get_manuscript("s1")
    assert result.prose == "从前有座山"


def test_fts_search(db):
    db.save_manuscript(Manuscript(scene_id="s1", prose="张三拔出了宝剑", word_count=7))
    db.save_manuscript(Manuscript(scene_id="s2", prose="李四躲在角落里", word_count=7))
    results = db.search_fts("宝剑", top_k=3)
    assert any("宝剑" in r for r in results)


def test_checkpoint_save_and_restore(db):
    db.save_character(_char())
    db.init_character_state(_state())
    db.validate_and_apply(StateChangeProposal(changes=[
        StateChangeItem(target="c1", field="location", op="set", value="城堡", reason="移动")
    ]))
    snap = db.take_state_snapshot()
    cp = CheckpointRecord(id="cp1", stage="SCENE_LOOP", scene_id="s1", state_snapshot=snap)
    db.save_checkpoint(cp)
    db.validate_and_apply(StateChangeProposal(changes=[
        StateChangeItem(target="c1", field="location", op="set", value="地牢", reason="被抓")
    ]))
    assert db.get_character_state("c1").location == "地牢"
    db.restore_checkpoint("cp1")
    assert db.get_character_state("c1").location == "城堡"
