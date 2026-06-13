import pytest
from unittest.mock import MagicMock
from novel_pipeline.prewriting import PrewritingModule
from novel_pipeline.persistence import Persistence
from novel_pipeline.models import WorldBible, CharacterProfile


@pytest.fixture
def db():
    return Persistence(":memory:")


@pytest.fixture
def llm():
    return MagicMock()


def test_run_saves_world_bible(db, llm):
    llm.call_structured.side_effect = [
        WorldBible(setting="架空古代", rules=["魔法存在"], key_facts=["王国内战"]),
        MagicMock(characters=[
            CharacterProfile(id="c1", name="张三", persona="勇敢", voice="豪迈", arc="平民→英雄"),
            CharacterProfile(id="c2", name="李四", persona="狡猾", voice="迂回", arc="盟友→背叛者"),
        ]),
    ]
    module = PrewritingModule(llm=llm, persistence=db)
    wb, chars = module.run(premise="一场关于背叛的故事", num_characters=2)
    assert wb.setting == "架空古代"
    assert db.get_world_bible().setting == "架空古代"


def test_run_saves_characters(db, llm):
    llm.call_structured.side_effect = [
        WorldBible(setting="现代都市", rules=[], key_facts=[]),
        MagicMock(characters=[
            CharacterProfile(id="c1", name="王五", persona="内向", voice="简短", arc="孤独→连接"),
        ]),
    ]
    module = PrewritingModule(llm=llm, persistence=db)
    wb, chars = module.run(premise="一个关于孤独的故事", num_characters=1)
    assert len(chars) == 1
    assert db.get_character("c1").name == "王五"


def test_run_initializes_character_states(db, llm):
    llm.call_structured.side_effect = [
        WorldBible(setting="古代", rules=[], key_facts=[]),
        MagicMock(characters=[
            CharacterProfile(id="c1", name="甲", persona="x", voice="y", arc="a→b"),
        ]),
    ]
    module = PrewritingModule(llm=llm, persistence=db)
    module.run(premise="故事前提", num_characters=1)
    state = db.get_character_state("c1")
    assert state.status == "alive"
