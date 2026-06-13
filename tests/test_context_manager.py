import pytest
from novel_pipeline.context_manager import ContextManager
from novel_pipeline.persistence import Persistence
from novel_pipeline.models import (
    CharacterProfile, WorldBible, CharacterState,
    ConstraintBox, StateChangeProposal, StateChangeItem, Manuscript,
)


@pytest.fixture
def db():
    p = Persistence(":memory:")
    p.save_world_bible(WorldBible(setting="古代", rules=[], key_facts=[]))
    p.save_character(CharacterProfile(id="c1", name="张三", persona="x", voice="y", arc="a→b"))
    p.save_character(CharacterProfile(id="c2", name="李四", persona="x", voice="y", arc="a→b"))
    p.init_character_state(CharacterState(char_id="c1", location="村口", emotional_state="紧张", status="alive"))
    p.init_character_state(CharacterState(char_id="c2", location="城堡", emotional_state="冷静", status="alive"))
    box = ConstraintBox(
        scene_id="s1", chapter_id="ch1",
        entry_state="初始", exit_state="结束",
        required_events=["事件A"],
        present_character_ids=["c1", "c2"],
        location="广场", order_idx=1,
    )
    p.save_scene(box)
    p.validate_and_apply(StateChangeProposal(changes=[
        StateChangeItem(target="c1", field="knowledge", op="add", value="c1的秘密", reason="test")
    ]))
    return p


def test_assemble_returns_context_package(db):
    cm = ContextManager(persistence=db)
    ctx = cm.assemble(speaker_id="c1", scene_id="s1")
    assert ctx.character.id == "c1"
    assert ctx.character_state.location == "村口"
    assert ctx.constraint_box.scene_id == "s1"


def test_knowledge_filtered_per_character(db):
    cm = ContextManager(persistence=db)
    ctx_c1 = cm.assemble(speaker_id="c1", scene_id="s1")
    ctx_c2 = cm.assemble(speaker_id="c2", scene_id="s1")
    assert "c1的秘密" in ctx_c1.knowledge
    assert "c1的秘密" not in ctx_c2.knowledge


def test_relevant_prose_from_fts(db):
    db.save_manuscript(Manuscript(scene_id="s0", prose="张三拔出宝剑大喊", word_count=8))
    cm = ContextManager(persistence=db)
    ctx = cm.assemble(speaker_id="c1", scene_id="s1")
    assert isinstance(ctx.relevant_prose, list)
