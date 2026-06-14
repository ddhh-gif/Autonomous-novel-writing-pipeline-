import pytest
import yaml
from unittest.mock import MagicMock
from novel_pipeline.characters_loader import CharactersLoader, SyncReport, _EnrichResponse
from novel_pipeline.persistence import Persistence
from novel_pipeline.models import (
    WorldBible, CharacterProfile, ConstraintBox,
    Background, SpeechStyle, DialogueMode,
)


@pytest.fixture
def db():
    p = Persistence(":memory:")
    p.save_world_bible(WorldBible(setting="架空都市", rules=[], key_facts=[]))
    return p


@pytest.fixture
def llm():
    return MagicMock()


def _loader(llm, db, tmp_path, auto_enrich=True):
    return CharactersLoader(
        llm=llm, persistence=db,
        characters_dir=str(tmp_path / "characters"),
        auto_enrich=auto_enrich,
    )


def _write_seed(tmp_path, name, data):
    d = tmp_path / "characters"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def test_load_seeds_bare_file(llm, db, tmp_path):
    _write_seed(tmp_path, "char_1.yaml", {"id": "char_1", "name": "林深"})
    loader = _loader(llm, db, tmp_path)
    seeds = loader.load_seeds()
    assert len(seeds) == 1
    assert seeds[0].name == "林深"
    assert seeds[0].persona == ""  # 缺省核心字段以空串占位


def test_load_seeds_id_from_filename(llm, db, tmp_path):
    _write_seed(tmp_path, "hero.yaml", {"name": "无名"})
    loader = _loader(llm, db, tmp_path)
    seeds = loader.load_seeds()
    assert seeds[0].id == "hero"


def test_write_back_roundtrip(llm, db, tmp_path):
    loader = _loader(llm, db, tmp_path)
    char = CharacterProfile(
        id="c1", name="甲", persona="p", voice="v", arc="a→b",
        speech_style=SpeechStyle(language_register="书面", catchphrases=["线索不会撒谎。"]),
    )
    path = loader.write_back(char)
    assert path.exists()
    reloaded = loader.load_seeds()[0]
    assert reloaded.speech_style.language_register == "书面"
    assert "线索不会撒谎。" in reloaded.speech_style.catchphrases


def test_enrich_fills_missing_modules(llm, db, tmp_path):
    llm.call_structured.return_value = _EnrichResponse(
        background=Background(occupation="侦探"),
        speech_style=SpeechStyle(language_register="冷峻"),
        dialogue_mode=DialogueMode(assertiveness="强势"),
    )
    loader = _loader(llm, db, tmp_path)
    char = CharacterProfile(id="c1", name="甲", persona="p", voice="v", arc="a→b")
    enriched = loader.enrich(char, premise="谜案", world_bible=db.get_world_bible())
    assert enriched.background.occupation == "侦探"
    assert enriched.dialogue_mode.assertiveness == "强势"
    llm.call_structured.assert_called_once()


def test_enrich_noop_when_complete(llm, db, tmp_path):
    loader = _loader(llm, db, tmp_path)
    char = CharacterProfile(
        id="c1", name="甲", persona="p", voice="v", arc="a→b",
        background=Background(occupation="x"),
        speech_style=SpeechStyle(language_register="x"),
        dialogue_mode=DialogueMode(assertiveness="x"),
    )
    loader.enrich(char, premise="x", world_bible=db.get_world_bible())
    llm.call_structured.assert_not_called()


def test_enrich_disabled_skips_llm(llm, db, tmp_path):
    loader = _loader(llm, db, tmp_path, auto_enrich=False)
    char = CharacterProfile(id="c1", name="甲", persona="p", voice="v", arc="a→b")
    out = loader.enrich(char, premise="x", world_bible=db.get_world_bible())
    assert out is char
    llm.call_structured.assert_not_called()


def test_prepare_characters_from_seeds(llm, db, tmp_path):
    _write_seed(tmp_path, "char_1.yaml", {"id": "char_1", "name": "林深",
                                          "persona": "p", "voice": "v", "arc": "a→b"})
    llm.call_structured.return_value = _EnrichResponse(
        background=Background(occupation="侦探"),
        speech_style=SpeechStyle(language_register="冷峻"),
        dialogue_mode=DialogueMode(assertiveness="强势"),
    )
    loader = _loader(llm, db, tmp_path)
    chars = loader.prepare_characters(premise="谜案", world_bible=db.get_world_bible(), num_characters=1)
    assert len(chars) == 1
    assert chars[0].background.occupation == "侦探"
    # 回写后文件应包含补全内容
    assert "侦探" in (tmp_path / "characters" / "char_1.yaml").read_text(encoding="utf-8")


def test_prepare_characters_batch_when_no_seeds(llm, db, tmp_path):
    llm.call_structured.return_value = MagicMock(characters=[
        CharacterProfile(id="c1", name="甲", persona="p", voice="v", arc="a→b",
                         background=Background(occupation="x"),
                         speech_style=SpeechStyle(language_register="x"),
                         dialogue_mode=DialogueMode(assertiveness="x")),
    ])
    loader = _loader(llm, db, tmp_path)
    chars = loader.prepare_characters(premise="x", world_bible=db.get_world_bible(), num_characters=1)
    assert len(chars) == 1
    llm.call_structured.assert_called_once()  # 只批量生成，无需逐个补全


def test_sync_adds_new_character(llm, db, tmp_path):
    loader = _loader(llm, db, tmp_path, auto_enrich=False)
    _write_seed(tmp_path, "c1.yaml", {"id": "c1", "name": "甲", "persona": "p", "voice": "v", "arc": "a→b"})
    report = loader.sync()
    assert "c1" in report.added
    assert db.get_character("c1").name == "甲"
    assert db.get_character_state("c1").status == "alive"


def test_sync_removes_missing_file(llm, db, tmp_path):
    db.save_character(CharacterProfile(id="c1", name="甲", persona="p", voice="v", arc="a→b"))
    from novel_pipeline.models import CharacterState
    db.init_character_state(CharacterState(char_id="c1", location="x", emotional_state="y"))
    loader = _loader(llm, db, tmp_path, auto_enrich=False)
    report = loader.sync()
    assert "c1" in report.removed
    assert db.is_character_removed("c1") is True
    assert db.get_character("c1").name == "甲"  # 软删除，记录仍在


def test_sync_warns_when_removed_char_in_scene(llm, db, tmp_path):
    db.save_character(CharacterProfile(id="c1", name="甲", persona="p", voice="v", arc="a→b"))
    from novel_pipeline.models import CharacterState
    db.init_character_state(CharacterState(char_id="c1", location="x", emotional_state="y"))
    db.save_scene(ConstraintBox(
        scene_id="s1", chapter_id="ch1", entry_state="e", exit_state="x",
        required_events=[], present_character_ids=["c1"], location="L", order_idx=1,
    ))
    loader = _loader(llm, db, tmp_path, auto_enrich=False)
    report = loader.sync()
    assert "c1" in report.removed
    assert any("s1" in w for w in report.warnings)


def test_sync_restores_character(llm, db, tmp_path):
    db.save_character(CharacterProfile(id="c1", name="甲", persona="p", voice="v", arc="a→b"))
    from novel_pipeline.models import CharacterState
    db.init_character_state(CharacterState(char_id="c1", location="x", emotional_state="y"))
    db.set_character_removed("c1", True)
    _write_seed(tmp_path, "c1.yaml", {"id": "c1", "name": "甲", "persona": "p", "voice": "v", "arc": "a→b"})
    loader = _loader(llm, db, tmp_path, auto_enrich=False)
    report = loader.sync()
    assert "c1" in report.restored
    assert db.is_character_removed("c1") is False


def test_regen_rewrites_modules(llm, db, tmp_path):
    db.save_character(CharacterProfile(
        id="c1", name="甲", persona="p", voice="v", arc="a→b",
        dialogue_mode=DialogueMode(assertiveness="旧"),
    ))
    llm.call_structured.return_value = _EnrichResponse(
        background=Background(occupation="新职业"),
        speech_style=SpeechStyle(language_register="新语域"),
        dialogue_mode=DialogueMode(assertiveness="新姿态"),
    )
    loader = _loader(llm, db, tmp_path)
    out = loader.regen("c1")
    assert out.dialogue_mode.assertiveness == "新姿态"
    assert db.get_character("c1").background.occupation == "新职业"


# ---------- 防御性边角 ----------

def test_sync_before_world_bible_does_not_crash(llm, db, tmp_path):
    # 没有世界设定时 sync 仍能登记角色，跳过补全并给出警告，不抛异常。
    db_no_wb = Persistence(":memory:")
    _write_seed(tmp_path, "c1.yaml", {"id": "c1", "name": "甲"})  # 只有 name
    loader = CharactersLoader(
        llm=llm, persistence=db_no_wb,
        characters_dir=str(tmp_path / "characters"), auto_enrich=True,
    )
    report = loader.sync()
    assert "c1" in report.added
    assert report.warnings  # 提示跳过补全
    llm.call_structured.assert_not_called()


def test_regen_before_world_bible_raises_runtimeerror(llm, tmp_path):
    db_no_wb = Persistence(":memory:")
    db_no_wb.save_character(CharacterProfile(id="c1", name="甲", persona="p", voice="v", arc="a→b"))
    loader = CharactersLoader(
        llm=llm, persistence=db_no_wb,
        characters_dir=str(tmp_path / "characters"), auto_enrich=True,
    )
    with pytest.raises(RuntimeError):
        loader.regen("c1")


def test_load_seeds_skips_malformed_files(llm, db, tmp_path):
    d = tmp_path / "characters"
    d.mkdir(parents=True, exist_ok=True)
    (d / "good.yaml").write_text("id: good\nname: 好的\n", encoding="utf-8")
    (d / "syntax.yaml").write_text("name: [unclosed\n", encoding="utf-8")           # YAML 语法错
    (d / "wrongtype.yaml").write_text(                                              # 字段类型错
        "id: bad\nname: 阿萍\nspeech_style:\n  catchphrases: 不是列表\n", encoding="utf-8")
    (d / "notmap.yaml").write_text("- 1\n- 2\n", encoding="utf-8")                  # 顶层非映射
    loader = _loader(llm, db, tmp_path)
    seeds = loader.load_seeds()
    assert [s.id for s in seeds] == ["good"]


def test_sync_preserves_unchanged_file(llm, db, tmp_path):
    # 完整角色（无需补全）经 sync 后文件不应被重写。
    seed_path = tmp_path / "characters" / "c1.yaml"
    seed_path.parent.mkdir(parents=True, exist_ok=True)
    original = "id: c1\nname: 甲\npersona: p\nvoice: v\narc: a→b\n# 我的注释\n"
    seed_path.write_text(original, encoding="utf-8")
    # 提供 world bible 但角色仍缺模块——auto_enrich 关闭，故不改动。
    loader = _loader(llm, db, tmp_path, auto_enrich=False)
    loader.sync()
    assert seed_path.read_text(encoding="utf-8") == original  # 注释与格式保留
