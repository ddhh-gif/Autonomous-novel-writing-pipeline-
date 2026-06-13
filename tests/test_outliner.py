import pytest
from unittest.mock import MagicMock
from pydantic import BaseModel
from novel_pipeline.outliner import Outliner
from novel_pipeline.persistence import Persistence
from novel_pipeline.models import (
    WorldBible, CharacterProfile, ActBeat, Chapter, ConstraintBox,
)


@pytest.fixture
def db():
    p = Persistence(":memory:")
    wb = WorldBible(setting="古代", rules=[], key_facts=[])
    p.save_world_bible(wb)
    char = CharacterProfile(id="c1", name="张三", persona="x", voice="y", arc="a→b")
    p.save_character(char)
    return p


@pytest.fixture
def llm():
    return MagicMock()


def _acts_response():
    class R(BaseModel):
        acts: list[ActBeat]
    return R(acts=[ActBeat(act_number=1, title="开端", description="故事开始", turning_point="危机出现")])


def _chapters_response():
    class R(BaseModel):
        chapters: list[Chapter]
    return R(chapters=[Chapter(id="ch_1_1", act_number=1, goal="引入角色", present_character_ids=["c1"], location="村庄", order_idx=1)])


def _scenes_response():
    class R(BaseModel):
        scenes: list[ConstraintBox]
    return R(scenes=[ConstraintBox(
        scene_id="ch_1_1_s1", chapter_id="ch_1_1",
        entry_state="平静的早晨", exit_state="发现危险",
        required_events=["张三得知威胁"],
        present_character_ids=["c1"], location="村庄", order_idx=1,
    )])


def test_run_saves_acts(db, llm):
    llm.call_structured.side_effect = [_acts_response(), _chapters_response(), _scenes_response()]
    outliner = Outliner(llm=llm, persistence=db)
    wb = db.get_world_bible()
    chars = db.get_all_characters()
    scenes = outliner.run(premise="故事", world_bible=wb, characters=chars)
    assert len(db.get_all_acts()) == 1
    assert db.get_all_acts()[0].title == "开端"


def test_run_saves_constraint_boxes(db, llm):
    llm.call_structured.side_effect = [_acts_response(), _chapters_response(), _scenes_response()]
    outliner = Outliner(llm=llm, persistence=db)
    wb = db.get_world_bible()
    chars = db.get_all_characters()
    scenes = outliner.run(premise="故事", world_bible=wb, characters=chars)
    assert len(scenes) >= 1
    assert scenes[0].scene_id == "ch_1_1_s1"
    assert db.get_scene("ch_1_1_s1").exit_state == "发现危险"
