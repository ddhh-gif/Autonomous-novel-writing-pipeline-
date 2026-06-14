from __future__ import annotations
import json
import sqlite3
from novel_pipeline.models import (
    CharacterProfile, WorldBible, ActBeat, Chapter, ConstraintBox,
    CharacterState, StateChangeProposal, SceneTranscriptEntry,
    Manuscript, CheckpointRecord,
    Background, SpeechStyle, DialogueMode,
)

_CHAR_MODULE_TYPES = {
    "background": Background,
    "speech_style": SpeechStyle,
    "dialogue_mode": DialogueMode,
}


def _dump_module(module) -> str | None:
    return json.dumps(module.model_dump(), ensure_ascii=False) if module is not None else None


def _row_to_character(row) -> CharacterProfile:
    d = dict(row)
    d.pop("removed", None)
    for field, model in _CHAR_MODULE_TYPES.items():
        raw = d.get(field)
        d[field] = model(**json.loads(raw)) if raw else None
    return CharacterProfile(**d)

_VALID_CHAR_FIELDS = {"location", "emotional_state", "status", "knowledge"}

_FIELD_SQL = {
    "location": "UPDATE character_states SET location = ? WHERE char_id = ?",
    "emotional_state": "UPDATE character_states SET emotional_state = ? WHERE char_id = ?",
    "status": "UPDATE character_states SET status = ? WHERE char_id = ?",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS characters (
    id TEXT PRIMARY KEY, name TEXT NOT NULL,
    persona TEXT NOT NULL, voice TEXT NOT NULL, arc TEXT NOT NULL,
    background TEXT, speech_style TEXT, dialogue_mode TEXT,
    removed INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS world_bible (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    setting TEXT NOT NULL, rules TEXT NOT NULL, key_facts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outline_acts (
    act_number INTEGER PRIMARY KEY, title TEXT NOT NULL,
    description TEXT NOT NULL, turning_point TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chapters (
    id TEXT PRIMARY KEY, act_number INTEGER NOT NULL, goal TEXT NOT NULL,
    present_character_ids TEXT NOT NULL, location TEXT NOT NULL, order_idx INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS scenes (
    scene_id TEXT PRIMARY KEY, chapter_id TEXT NOT NULL,
    entry_state TEXT NOT NULL, exit_state TEXT NOT NULL,
    required_events TEXT NOT NULL, present_character_ids TEXT NOT NULL,
    location TEXT NOT NULL, pov TEXT, order_idx INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS character_states (
    char_id TEXT PRIMARY KEY, location TEXT NOT NULL,
    emotional_state TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'alive'
);
CREATE TABLE IF NOT EXISTS character_knowledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    char_id TEXT NOT NULL, fact TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS world_items (
    item_id TEXT PRIMARY KEY, name TEXT NOT NULL,
    location TEXT NOT NULL, description TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS foreshadowings (
    id TEXT PRIMARY KEY, description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'planted',
    planted_scene_id TEXT NOT NULL, resolved_scene_id TEXT
);
CREATE TABLE IF NOT EXISTS scene_transcripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scene_id TEXT NOT NULL, turn INTEGER NOT NULL,
    speaker_id TEXT NOT NULL, content TEXT NOT NULL,
    action_type TEXT NOT NULL DEFAULT 'speech', timestamp TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS manuscripts (
    scene_id TEXT PRIMARY KEY, prose TEXT NOT NULL,
    word_count INTEGER NOT NULL, version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS checkpoints (
    id TEXT PRIMARY KEY, stage TEXT NOT NULL, scene_id TEXT,
    state_snapshot TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS fts_manuscripts USING fts5(
    scene_id UNINDEXED, prose,
    content='manuscripts', content_rowid='rowid',
    tokenize='trigram'
);
"""


class ValidationError(Exception):
    pass


class Persistence:
    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self._conn.executescript(SCHEMA)
        self._migrate_characters()
        self._conn.commit()

    def _migrate_characters(self):
        """为旧版数据库补齐新增列，保持向后兼容。"""
        existing = {row["name"] for row in
                    self._conn.execute("PRAGMA table_info(characters)").fetchall()}
        additions = {
            "background": "ALTER TABLE characters ADD COLUMN background TEXT",
            "speech_style": "ALTER TABLE characters ADD COLUMN speech_style TEXT",
            "dialogue_mode": "ALTER TABLE characters ADD COLUMN dialogue_mode TEXT",
            "removed": "ALTER TABLE characters ADD COLUMN removed INTEGER NOT NULL DEFAULT 0",
        }
        for col, sql in additions.items():
            if col not in existing:
                self._conn.execute(sql)

    def save_character(self, char: CharacterProfile) -> None:
        # ON CONFLICT 升级而非替换，保留软删除标记（removed）不被重置。
        self._conn.execute(
            "INSERT INTO characters"
            " (id, name, persona, voice, arc, background, speech_style, dialogue_mode)"
            " VALUES (?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " name=excluded.name, persona=excluded.persona, voice=excluded.voice,"
            " arc=excluded.arc, background=excluded.background,"
            " speech_style=excluded.speech_style, dialogue_mode=excluded.dialogue_mode",
            (char.id, char.name, char.persona, char.voice, char.arc,
             _dump_module(char.background), _dump_module(char.speech_style),
             _dump_module(char.dialogue_mode)),
        )
        self._conn.commit()

    def get_character(self, char_id: str) -> CharacterProfile:
        row = self._conn.execute("SELECT * FROM characters WHERE id=?", (char_id,)).fetchone()
        if not row:
            raise KeyError(char_id)
        return _row_to_character(row)

    def get_all_characters(self, include_removed: bool = False) -> list[CharacterProfile]:
        sql = "SELECT * FROM characters"
        if not include_removed:
            sql += " WHERE removed = 0"
        rows = self._conn.execute(sql).fetchall()
        return [_row_to_character(r) for r in rows]

    def set_character_removed(self, char_id: str, removed: bool) -> None:
        """软删除 / 恢复一个角色。已生成的稿件与对话记录不受影响。"""
        cur = self._conn.execute(
            "UPDATE characters SET removed=? WHERE id=?",
            (1 if removed else 0, char_id),
        )
        if cur.rowcount == 0:
            raise KeyError(char_id)
        self._conn.commit()

    def is_character_removed(self, char_id: str) -> bool:
        row = self._conn.execute(
            "SELECT removed FROM characters WHERE id=?", (char_id,)
        ).fetchone()
        if not row:
            raise KeyError(char_id)
        return bool(row["removed"])

    def save_world_bible(self, wb: WorldBible) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO world_bible VALUES (1,?,?,?)",
            (wb.setting, json.dumps(wb.rules, ensure_ascii=False),
             json.dumps(wb.key_facts, ensure_ascii=False)),
        )
        self._conn.commit()

    def get_world_bible(self) -> WorldBible:
        row = self._conn.execute("SELECT * FROM world_bible WHERE id=1").fetchone()
        if not row:
            raise KeyError("world_bible not set")
        return WorldBible(
            setting=row["setting"],
            rules=json.loads(row["rules"]),
            key_facts=json.loads(row["key_facts"]),
        )

    def save_act(self, act: ActBeat) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO outline_acts VALUES (?,?,?,?)",
            (act.act_number, act.title, act.description, act.turning_point),
        )
        self._conn.commit()

    def get_all_acts(self) -> list[ActBeat]:
        rows = self._conn.execute("SELECT * FROM outline_acts ORDER BY act_number").fetchall()
        return [ActBeat(**dict(r)) for r in rows]

    def save_chapter(self, chapter: Chapter) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO chapters VALUES (?,?,?,?,?,?)",
            (chapter.id, chapter.act_number, chapter.goal,
             json.dumps(chapter.present_character_ids, ensure_ascii=False),
             chapter.location, chapter.order_idx),
        )
        self._conn.commit()

    def get_all_chapters(self) -> list[Chapter]:
        rows = self._conn.execute("SELECT * FROM chapters ORDER BY order_idx").fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["present_character_ids"] = json.loads(d["present_character_ids"])
            result.append(Chapter(**d))
        return result

    def save_scene(self, scene: ConstraintBox) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO scenes VALUES (?,?,?,?,?,?,?,?,?)",
            (scene.scene_id, scene.chapter_id, scene.entry_state, scene.exit_state,
             json.dumps(scene.required_events, ensure_ascii=False),
             json.dumps(scene.present_character_ids, ensure_ascii=False),
             scene.location, scene.pov, scene.order_idx),
        )
        self._conn.commit()

    def get_scene(self, scene_id: str) -> ConstraintBox:
        row = self._conn.execute("SELECT * FROM scenes WHERE scene_id=?", (scene_id,)).fetchone()
        if not row:
            raise KeyError(scene_id)
        d = dict(row)
        d["required_events"] = json.loads(d["required_events"])
        d["present_character_ids"] = json.loads(d["present_character_ids"])
        return ConstraintBox(**d)

    def get_all_scenes(self) -> list[ConstraintBox]:
        rows = self._conn.execute("SELECT * FROM scenes ORDER BY order_idx").fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["required_events"] = json.loads(d["required_events"])
            d["present_character_ids"] = json.loads(d["present_character_ids"])
            result.append(ConstraintBox(**d))
        return result

    def init_character_state(self, state: CharacterState) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO character_states VALUES (?,?,?,?)",
            (state.char_id, state.location, state.emotional_state, state.status),
        )
        self._conn.commit()

    def get_character_state(self, char_id: str) -> CharacterState:
        row = self._conn.execute(
            "SELECT * FROM character_states WHERE char_id=?", (char_id,)
        ).fetchone()
        if not row:
            raise KeyError(char_id)
        return CharacterState(**dict(row))

    def get_character_knowledge(self, char_id: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT fact FROM character_knowledge WHERE char_id=? ORDER BY id", (char_id,)
        ).fetchall()
        return [r["fact"] for r in rows]

    def validate_and_apply(self, proposal: StateChangeProposal) -> None:
        from datetime import datetime
        with self._conn:
            for change in proposal.changes:
                if change.target == "world":
                    self._conn.execute(
                        "INSERT OR REPLACE INTO world_items VALUES (?,?,?,?)",
                        (change.field, change.field, change.value, change.reason),
                    )
                    continue
                if change.target == "foreshadowing":
                    self._conn.execute(
                        "UPDATE foreshadowings SET status=? WHERE id=?",
                        (change.value, change.field),
                    )
                    continue
                row = self._conn.execute(
                    "SELECT id FROM characters WHERE id=?", (change.target,)
                ).fetchone()
                if not row:
                    raise ValidationError(f"Unknown target: {change.target!r}")
                if change.field not in _VALID_CHAR_FIELDS:
                    raise ValidationError(f"Unknown field: {change.field!r}")
                if change.field == "knowledge":
                    if change.op == "add":
                        self._conn.execute(
                            "INSERT INTO character_knowledge (char_id, fact, created_at) VALUES (?,?,?)",
                            (change.target, change.value, datetime.utcnow().isoformat()),
                        )
                    elif change.op == "remove":
                        self._conn.execute(
                            "DELETE FROM character_knowledge WHERE char_id=? AND fact=?",
                            (change.target, change.value),
                        )
                else:
                    sql = _FIELD_SQL[change.field]
                    self._conn.execute(sql, (change.value, change.target))

    def append_transcript(self, entry: SceneTranscriptEntry) -> None:
        self._conn.execute(
            "INSERT INTO scene_transcripts (scene_id, turn, speaker_id, content, action_type, timestamp)"
            " VALUES (?,?,?,?,?,?)",
            (entry.scene_id, entry.turn, entry.speaker_id,
             entry.content, entry.action_type, entry.timestamp),
        )
        self._conn.commit()

    def get_transcript(self, scene_id: str) -> list[SceneTranscriptEntry]:
        rows = self._conn.execute(
            "SELECT scene_id, turn, speaker_id, content, action_type, timestamp"
            " FROM scene_transcripts WHERE scene_id=? ORDER BY turn",
            (scene_id,),
        ).fetchall()
        return [SceneTranscriptEntry(**dict(r)) for r in rows]

    def save_manuscript(self, manuscript: Manuscript) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO manuscripts VALUES (?,?,?,?)",
            (manuscript.scene_id, manuscript.prose, manuscript.word_count, manuscript.version),
        )
        self._conn.execute(
            "INSERT OR REPLACE INTO fts_manuscripts(scene_id, prose) VALUES (?,?)",
            (manuscript.scene_id, manuscript.prose),
        )
        self._conn.commit()

    def get_manuscript(self, scene_id: str) -> Manuscript | None:
        row = self._conn.execute(
            "SELECT * FROM manuscripts WHERE scene_id=?", (scene_id,)
        ).fetchone()
        if not row:
            return None
        return Manuscript(**dict(row))

    def search_fts(self, query: str, top_k: int = 5) -> list[str]:
        # MVP placeholder: LIKE search. Replace with vector search (Chroma) later.
        rows = self._conn.execute(
            "SELECT prose FROM manuscripts WHERE prose LIKE ? LIMIT ?",
            (f"%{query}%", top_k),
        ).fetchall()
        return [r["prose"] for r in rows]

    def take_state_snapshot(self) -> dict:
        chars = {}
        for row in self._conn.execute("SELECT * FROM character_states").fetchall():
            cid = row["char_id"]
            chars[cid] = dict(row)
            chars[cid]["knowledge"] = self.get_character_knowledge(cid)
        return {"character_states": chars}

    def save_checkpoint(self, cp: CheckpointRecord) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO checkpoints VALUES (?,?,?,?,?)",
            (cp.id, cp.stage, cp.scene_id,
             json.dumps(cp.state_snapshot, ensure_ascii=False), cp.created_at),
        )
        self._conn.commit()

    def get_latest_checkpoint(self) -> CheckpointRecord | None:
        row = self._conn.execute(
            "SELECT * FROM checkpoints ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["state_snapshot"] = json.loads(d["state_snapshot"])
        return CheckpointRecord(**d)

    def get_checkpoint(self, checkpoint_id: str) -> CheckpointRecord:
        row = self._conn.execute(
            "SELECT * FROM checkpoints WHERE id=?", (checkpoint_id,)
        ).fetchone()
        if not row:
            raise KeyError(checkpoint_id)
        d = dict(row)
        d["state_snapshot"] = json.loads(d["state_snapshot"])
        return CheckpointRecord(**d)

    def restore_checkpoint(self, checkpoint_id: str) -> None:
        from datetime import datetime
        cp = self.get_checkpoint(checkpoint_id)
        snap = cp.state_snapshot
        with self._conn:
            for char_id, state in snap.get("character_states", {}).items():
                self._conn.execute(
                    "UPDATE character_states SET location=?, emotional_state=?, status=?"
                    " WHERE char_id=?",
                    (state["location"], state["emotional_state"], state["status"], char_id),
                )
                self._conn.execute(
                    "DELETE FROM character_knowledge WHERE char_id=?", (char_id,)
                )
                for fact in state.get("knowledge", []):
                    self._conn.execute(
                        "INSERT INTO character_knowledge (char_id, fact, created_at) VALUES (?,?,?)",
                        (char_id, fact, datetime.utcnow().isoformat()),
                    )
