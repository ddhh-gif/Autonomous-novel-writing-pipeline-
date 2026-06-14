# Novel Pipeline

自主中文长篇小说生成系统。基于 Anthropic Messages API 支持多种厂家API格式，通过多 Agent 协作、严格状态管控和逐场景检查点，生成约 2 万字、单情节线、3–5 个角色的短篇小说。

---

## 目录

- [设计原则](#设计原则)
- [架构总览](#架构总览)
- [快速开始](#快速开始)
- [CLI 用法](#cli-用法)
- [配置参考](#配置参考)
- [数据模型](#数据模型)
- [Pipeline 流程](#pipeline-流程)
- [模块说明](#模块说明)
- [数据库 Schema](#数据库-schema)
- [测试](#测试)
- [扩展点](#扩展点)
- [验收标准验证](#验收标准验证)

---

## 设计原则

这五条原则在代码里没有妥协空间：

**1. 状态与指令分离**  
世界的事实状态存在 SQLite，是唯一真相源（source of truth）。Prompt 是状态的一次性投影——每次调用 LLM 时，从数据库读出相关状态、组装 prompt、调用模型、把结果写回数据库。长期状态绝不只存在 LLM 的上下文里。

**2. LLM 写关门（Write-Gate）**  
LLM 只能输出 `StateChangeProposal`（结构化 JSON 变更提议），由 `Persistence.validate_and_apply()` 校验后才能写入数据库。LLM 没有任何直接写库的路径。

**3. 生成与校验角色分离**  
负责"演/写"的 Agent（CharacterAgent、Drafter）和负责"审"的 Agent（DirectorAgent、Critic）是完全独立的 LLM 调用，使用不同的 prompt。生成 Agent 不能自评后直接放行。

**4. 自顶向下定边界，自底向上填内容**  
Outliner 把全书分解为 ConstraintBox（约束盒），每个约束盒固定 `entry_state`、`exit_state`、`required_events`。场景内部由角色 Agent 自主互动涌现，DirectorAgent 在出口处校验结果是否满足约束。

**5. 每步可检查点、可回滚**  
每个 scene turn 写一次 CheckpointRecord，`rollback` 命令可恢复到任意历史快照。

---

## 架构总览

```
用户提供 premise
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│                      Orchestrator                       │
│   状态机：INIT → PREWRITING → OUTLINING → SCENE_LOOP    │
└───┬──────────────┬────────────────────┬─────────────────┘
    │              │                    │
    ▼              ▼                    ▼
PrewritingModule  Outliner         SceneRunner (每场景)
  世界设定          三层大纲              │
  角色档案          ConstraintBox[]      ├─ DirectorAgent（选角色 + 审稿）
    │                   │               ├─ CharacterAgent（发言）
    └─────────┬─────────┘               ├─ Drafter（transcript → 散文）
              │                         ├─ Critic（一致性校验）
              ▼                         └─ Reviser（按 Critic 反馈修订）
         Persistence (SQLite)
              ▲
              │  所有读写经过此层
         ContextManager
              │  组装每次 LLM 调用的上下文包
              └─ 按角色过滤 knowledge（信息差）
```

**数据流向（核心节拍）：**

```
ContextManager.assemble()     ← 从 DB 读状态
    → build prompt            ← Jinja2 模板渲染
    → LLMClient.call_*()      ← Anthropic API
    → parse / validate
    → Persistence.validate_and_apply()   ← 写关门
    → save_checkpoint()
```

---

## 快速开始

### 1. 环境准备

```bash
conda create -n novel-pipeline python=3.11
conda activate novel-pipeline
pip install -r requirements.txt
```

### 2. 配置 API Key

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

### 3. 编辑配置文件

复制并按需修改 `config.yaml`（项目根目录已有默认配置）：

```bash
cp config.yaml my_novel.yaml
# 按需修改 model、target_words 等
```

### 4. 运行 Pipeline

```bash
PYTHONPATH=/home/zihan/writing \
  python -m novel_pipeline run \
  --config my_novel.yaml \
  --premise "皇帝神秘失踪，两位侠士联手追查真相" \
  --characters 3
```

Pipeline 分三个阶段自动执行：
1. **Prewriting** — 生成世界设定 + 角色档案，写入 DB
2. **Outlining** — 生成三层大纲 + ConstraintBox 列表
3. **Scene Loop** — 逐场景跑角色互动 → 散文 → 校验，每 turn 写检查点

---

## CLI 用法

### `run` — 运行 pipeline

```bash
python -m novel_pipeline run \
  --config config.yaml \
  --premise "故事前提，一句话描述" \
  --characters 4
```

| 参数 | 说明 | 默认 |
|------|------|------|
| `--config` | 配置文件路径 | `config.yaml` |
| `--premise` | 故事前提（必填） | — |
| `--characters` | 角色数量 | `4` |

中途中断后，重新执行相同命令会从最近检查点继续（不会重跑已完成的场景）。

### `status` — 查看进度

```bash
python -m novel_pipeline status --config config.yaml
```

输出示例：

```json
{
  "stage": "SCENE_LOOP",
  "latest_checkpoint": "a3f2c1d0-...",
  "scenes_total": 12,
  "scenes_done": 5
}
```

### `rollback` — 回滚到检查点

```bash
python -m novel_pipeline rollback \
  --config config.yaml \
  --checkpoint a3f2c1d0-...
```

Checkpoint ID 可从 `status` 输出或直接查询数据库获取：

```bash
sqlite3 novel.db "SELECT id, stage, scene_id, created_at FROM checkpoints ORDER BY created_at DESC LIMIT 10;"
```

---

## 配置参考

`config.yaml` 完整字段说明：

```yaml
llm:
  model: claude-sonnet-4-6          # Anthropic 模型 ID
  temperature_creative: 0.9          # 散文生成温度（CharacterAgent、Drafter）
  temperature_structured: 0.2        # 结构化 JSON 输出温度（Outliner、Director 等）
  max_tokens: 4096                   # 单次 LLM 调用最大 token 数
  max_retries: 3                     # JSON 解析失败后的重试次数

pipeline:
  max_turns_per_scene: 40            # 单场景最大对话轮数（防无限循环）
  max_rollbacks_per_scene: 3         # 单场景 Critic 触发回滚的最大次数
  target_words: 20000                # 全书目标字数（均摊到各场景）

db:
  path: novel.db                     # SQLite 数据库路径（":memory:" 用于测试）
```

```
llm:
  backend: openai_compat  # 若非 Anthropic API 需要加这一行
  model: deepseek-chat
  api_key_env: DEEPSEEK_API_KEY
  base_url: https://api.deepseek.com
  temperature_creative: 0.9
  temperature_structured: 0.2
  max_tokens: 4096
  max_retries: 3

pipeline:
  max_turns_per_scene: 40
  max_rollbacks_per_scene: 3
  target_words: 20000

db:
  path: novel.db

  
---

## 数据模型

所有模型定义在 `novel_pipeline/models.py`，使用 Pydantic v2。

### 写作前生成（不可变）

```python
class CharacterProfile(BaseModel):
    id: str                  # 角色唯一标识，供 Agent 引用
    name: str                # 中文姓名
    persona: str             # 动机、背景、性格描述
    voice: str               # 说话风格 + 2–3 句示例台词（prompt few-shot）
    arc: str                 # 人物弧光："初始状态 → 终态"

class WorldBible(BaseModel):
    setting: str             # 时代背景、地理描述
    rules: list[str]         # 世界运行规则（如"魔法需要代价"）
    key_facts: list[str]     # 不可违背的事实
```

### 大纲层（自顶向下）

```python
class ActBeat(BaseModel):
    act_number: int          # 幕号
    title: str               # 幕标题
    description: str         # 本幕概述
    turning_point: str       # 转折点描述

class Chapter(BaseModel):
    id: str
    act_number: int          # 所属幕
    goal: str                # 本章目标
    present_character_ids: list[str]
    location: str
    order_idx: int

class ConstraintBox(BaseModel):
    scene_id: str
    chapter_id: str
    entry_state: str         # 进场时的世界/角色状态（自然语言）
    exit_state: str          # 必须达成的退出状态（Director 以此收场）
    required_events: list[str]   # 必须发生的事件列表
    present_character_ids: list[str]
    location: str
    pov: str | None          # 视角角色（可空）
    order_idx: int
```

### 运行时状态（高频读写）

```python
class CharacterState(BaseModel):
    char_id: str
    location: str
    emotional_state: str
    status: str              # "alive" / "dead" / "injured" 等

# knowledge 存储在独立的 character_knowledge 表，按 char_id 隔离
# → 这是信息差（Information Gap）的技术基础
```

### LLM 写关门（核心安全契约）

```python
class StateChangeItem(BaseModel):
    target: str              # 角色 id、"world"、"foreshadowing"
    field: str               # location / emotional_state / status / knowledge
    op: Literal["set", "add", "remove"]
    value: str
    reason: str              # LLM 解释变更原因，便于审计

class StateChangeProposal(BaseModel):
    changes: list[StateChangeItem]
    # LLM 只能输出此类型，代码校验后才写库
```

### 场景生产物

```python
class SceneTranscriptEntry(BaseModel):
    scene_id: str
    turn: int
    speaker_id: str
    content: str
    action_type: str         # "speech" / "action" 等

class Manuscript(BaseModel):
    scene_id: str
    prose: str               # 最终散文
    word_count: int
    version: int             # Reviser 每次修订递增

class DirectorVerdict(BaseModel):
    off_track: bool
    required_events_progress: list[str]
    exit_state_reached: bool
    hint: str | None         # 给下一轮角色 Agent 的暗示
    rejected: bool
    rejection_reason: str | None
    next_speaker_id: str     # Director 同时决定下一个发言角色
```

---

## Pipeline 流程

### 阶段状态机

```
INIT
  │  (首次运行，或无检查点)
  ▼
PREWRITING
  │  PrewritingModule.run(premise, num_characters)
  │  → 生成 WorldBible + CharacterProfile[]
  │  → 写入 DB，初始化 CharacterState
  ▼
OUTLINING
  │  Outliner.run(premise, world_bible, characters)
  │  → 生成 ActBeat[] → Chapter[] → ConstraintBox[]
  │  → 写入 DB
  ▼
SCENE_LOOP
  │  对每个 ConstraintBox（按 order_idx 排序）：
  │    若已有 Manuscript，跳过（支持断点续跑）
  │    否则 SceneRunner.run_scene(scene_id)
  ▼
DONE
```

### 场景级子流程（SceneRunner）

```
load ConstraintBox(scene_id)
director.review(line=None, ...)         ← 初始评估，获得首个发言角色

while not exit_state_reached AND turn < MAX_TURNS:
    speaker_id = verdict.next_speaker_id
    ctx = ContextManager.assemble(speaker_id, scene_id, hint)
    # ctx 只包含该角色可见的 knowledge（信息差过滤）

    line = CharacterAgent.act(ctx)

    # 最多重试 2 次（若 Director 拒绝）
    verdict = DirectorAgent.review(line, transcript, box)
    if verdict.rejected:
        line = CharacterAgent.act(ctx_with_hint)

    transcript.append(line)
    Persistence.append_transcript(line)

    proposal = LLM.extract_state_changes(line)    ← 结构化提议
    Persistence.validate_and_apply(proposal)       ← 写关门
    Persistence.save_checkpoint(...)               ← 每 turn 存档

if turn >= MAX_TURNS:
    director.force_resolution(transcript, box)    ← 强制收场

prose = Drafter.draft(transcript, box, target_words)

report = Critic.check(prose, state_snapshot)
for issue in report.issues:
    if severity == "rollback":
        raise RuntimeError(...)    ← Orchestrator 捕获，触发重试
    if severity == "revise":
        prose = Reviser.revise(prose, issue)

Persistence.save_manuscript(Manuscript(scene_id, prose, ...))
```

---

## 模块说明

| 模块 | 文件 | 职责 |
|------|------|------|
| `Orchestrator` | `orchestrator.py` | 状态机驱动，检查点恢复，错误边界 |
| `PrewritingModule` | `prewriting.py` | 生成 WorldBible + CharacterProfile[]，初始化 CharacterState |
| `Outliner` | `outliner.py` | 三层大纲生成，产出 ConstraintBox[] |
| `ContextManager` | `context_manager.py` | 唯一读状态入口，组装 ContextPackage，按角色过滤 knowledge |
| `CharacterAgent` | `agents/character.py` | 接收 ContextPackage，输出 CharacterLine |
| `DirectorAgent` | `agents/director.py` | 审稿（review）+ 选下一发言者，合并为单次 LLM 调用 |
| `Drafter` | `agents/drafter.py` | transcript → 散文 |
| `Critic` | `critic.py` | 独立校验散文（连续性、角色一致性），输出 CriticReport |
| `Reviser` | `critic.py` | 按 CriticIssue 做定向修订 |
| `Persistence` | `persistence.py` | SQLite CRUD + validate_and_apply 写关门 + 检查点 |
| `LLMClient` | `llm.py` | Anthropic API 封装，`call_prose`（散文）/ `call_structured`（JSON）|
| `ContextPackage` | `models.py` | 传给 CharacterAgent 的完整上下文，含 world_bible、knowledge、transcript |

### 信息差（Information Gap）实现

`character_knowledge` 表以 `char_id` 为维度存储每个角色知道的事实。`ContextManager.assemble()` 只查询当前发言角色的 knowledge，其他角色的秘密对其完全不可见：

```python
# ContextManager
knowledge = self._db.get_character_knowledge(speaker_id)  # 只取此角色
# → 注入到 ContextPackage.knowledge
# → CharacterAgent 的 prompt 中只包含此列表
```

### 写关门（Write-Gate）实现

`Persistence.validate_and_apply()` 是唯一写入状态的路径：

```python
def validate_and_apply(self, proposal: StateChangeProposal) -> None:
    for change in proposal.changes:
        # 1. 验证 target 是合法角色 id（或 "world" / "foreshadowing"）
        row = self._conn.execute("SELECT id FROM characters WHERE id=?", (change.target,)).fetchone()
        if not row:
            raise ValidationError(f"Unknown target: {change.target!r}")
        # 2. 验证 field 在白名单内
        if change.field not in _VALID_CHAR_FIELDS:  # {"location", "emotional_state", "status", "knowledge"}
            raise ValidationError(f"Unknown field: {change.field!r}")
        # 3. 通过后才执行 SQL 写入
        ...
```

任何不合法的 `target` 或 `field` 都会抛 `ValidationError`，变更不会写入数据库。

---

## 数据库 Schema

数据库路径由配置文件 `db.path` 控制（默认 `novel.db`）。

```sql
-- 角色档案（写作前生成，基本不变）
characters          (id, name, persona, voice, arc)

-- 世界设定（单行，id=1）
world_bible         (id, setting, rules JSON, key_facts JSON)

-- 三层大纲
outline_acts        (act_number PK, title, description, turning_point)
chapters            (id PK, act_number, goal, present_character_ids JSON, location, order_idx)
scenes              (scene_id PK, chapter_id, entry_state, exit_state,
                     required_events JSON, present_character_ids JSON, location, pov, order_idx)

-- 运行时状态（高频读写）
character_states    (char_id PK, location, emotional_state, status)
character_knowledge (id AUTOINCREMENT, char_id, fact, created_at)

-- 世界物品与伏笔
world_items         (item_id PK, name, location, description)
foreshadowings      (id PK, description, status, planted_scene_id, resolved_scene_id)

-- 场景生产物
scene_transcripts   (id AUTOINCREMENT, scene_id, turn, speaker_id, content, action_type, timestamp)
manuscripts         (scene_id PK, prose, word_count, version)

-- 全文检索（Chinese LIKE search，FTS5 虚拟表作索引备用）
fts_manuscripts     VIRTUAL TABLE fts5 (scene_id UNINDEXED, prose)

-- 检查点
checkpoints         (id PK, stage, scene_id, state_snapshot JSON, created_at)
```

查看当前状态快照：

```bash
sqlite3 novel.db "SELECT char_id, location, emotional_state, status FROM character_states;"
sqlite3 novel.db "SELECT char_id, fact FROM character_knowledge ORDER BY char_id, id;"
sqlite3 novel.db "SELECT scene_id, word_count FROM manuscripts ORDER BY rowid;"
```

---

## 测试

```bash
# 运行全部测试（49 个）
PYTHONPATH=/home/zihan/writing \
  /home/zihan/miniconda3/envs/novel-pipeline/bin/pytest tests/ -v
```

测试文件说明：

| 文件 | 覆盖范围 |
|------|---------|
| `test_models.py` | Pydantic 模型字段校验 |
| `test_config.py` | YAML 配置加载 |
| `test_persistence.py` | SQLite CRUD、写关门、信息差、检查点回滚 |
| `test_llm.py` | JSON 解析、markdown 围栏剥离、重试逻辑 |
| `test_prewriting.py` | WorldBible 生成、角色初始化 |
| `test_outliner.py` | 大纲生成、ConstraintBox 写入 |
| `test_context_manager.py` | 上下文组装、knowledge 过滤、FTS 检索 |
| `test_agents.py` | CharacterAgent、DirectorAgent、Drafter |
| `test_critic.py` | Critic 校验、Reviser 修订 |
| `test_scene_runner.py` | 完整场景循环、信息差验证 |
| `test_orchestrator.py` | 三阶段状态机、检查点恢复 |
| `test_e2e.py` | 端到端冒烟测试、写关门验证、信息差验证 |

> **注意**：所有测试使用 `":memory:"` SQLite 数据库和 Mock LLM，不消耗 API 配额。

---

## 扩展点

### 替换向量检索（当前为 LIKE 占位）

`Persistence.search_fts()` 目前用 `LIKE` 搜索，适合 MVP。替换为 Chroma 向量库：

```python
# persistence.py
def search_fts(self, query: str, top_k: int = 5) -> list[str]:
    # 替换为：
    import chromadb
    results = self._chroma.query(query_texts=[query], n_results=top_k)
    return results["documents"][0]
```

同时在 `save_manuscript()` 中添加 embed + upsert 逻辑。

### 切换模型

修改 `config.yaml` 的 `llm.model` 即可，无需改代码：

```yaml
llm:
  model: claude-opus-4-8   # 或 claude-haiku-4-5-20251001
```

### 添加新的角色状态字段

在 `persistence.py` 的 `_VALID_CHAR_FIELDS` 白名单中添加新字段，并在 `_FIELD_SQL` 中添加对应 SQL，同时更新 `character_states` 表 schema：

```python
_VALID_CHAR_FIELDS = {"location", "emotional_state", "status", "knowledge", "inventory"}
_FIELD_SQL["inventory"] = "UPDATE character_states SET inventory = ? WHERE char_id = ?"
```

### 修改 Prompt 模板

所有 prompt 在 `novel_pipeline/prompts/` 目录下，使用 Jinja2 格式：

```
prewriting_world.j2       # 世界设定生成
prewriting_character.j2   # 角色档案生成
outliner_acts.j2          # 幕/转折点生成
outliner_chapters.j2      # 章节生成
outliner_scenes.j2        # 场景约束盒生成
character_agent.j2        # 角色发言
director_review.j2        # 导演审稿 + 选角色
director_force.j2         # 强制收场
state_extract.j2          # 状态变更提取
drafter.j2                # 散文生成
critic.j2                 # 一致性校验
reviser.j2                # 定向修订
```

修改模板后无需重启，下次 LLM 调用自动生效（Jinja2 运行时渲染）。

---

## 验收标准验证

### 1. 一键全流程 + 断点续跑

```bash
# 首次运行
python -m novel_pipeline run --config config.yaml --premise "你的故事前提"

# 中断后从检查点继续（重复执行即可）
python -m novel_pipeline run --config config.yaml --premise "你的故事前提"
```

已完成场景（有对应 `manuscripts` 记录）会自动跳过。

### 2. Critic 死亡检测 + 回滚

手动往数据库注入矛盾（角色死亡后仍登场）：

```bash
# 将角色设为死亡
sqlite3 novel.db "UPDATE character_states SET status='dead' WHERE char_id='c1';"

# Critic 检测逻辑在 critic.py，检查 prose 中的角色名与 state_snapshot 中的 status
# severity="rollback" 的 issue 会让 SceneRunner 抛 RuntimeError
# Orchestrator 捕获后递增 rollback_count，直到达上限
```

### 3. 信息差验证

```python
# tests/test_e2e.py::test_information_gap_between_characters
# 已覆盖：c1 的秘密 knowledge 对 c2 不可见
```

也可直接查库验证：

```bash
sqlite3 novel.db "SELECT char_id, fact FROM character_knowledge WHERE char_id='c1';"
# c2 的 knowledge 中不应出现 c1 的秘密
```

### 4. 写关门审计

```bash
# 确认代码中无任何绕过 validate_and_apply 的直接写库路径
grep -rn "INSERT\|UPDATE\|DELETE" novel_pipeline/ \
  --include="*.py" \
  | grep -v "persistence.py" \
  | grep -v "test_"
# 应无输出（所有写库操作集中在 persistence.py）
```

### 5. 单元测试全覆盖

```bash
PYTHONPATH=/home/zihan/writing \
  /home/zihan/miniconda3/envs/novel-pipeline/bin/pytest tests/ -v
# 49 passed
```

---

## 项目文件结构

```
novel_pipeline/
├── __init__.py
├── __main__.py          # CLI 入口（run / rollback / status）
├── config.py            # AppConfig / LLMConfig / PipelineConfig
├── models.py            # 全部 Pydantic 数据模型
├── persistence.py       # SQLite CRUD + validate_and_apply 写关门
├── llm.py               # Anthropic API 封装
├── context_manager.py   # 唯一读状态入口，组装 ContextPackage
├── prewriting.py        # PrewritingModule
├── outliner.py          # Outliner（三层大纲）
├── scene_runner.py      # SceneRunner（场景级主循环）
├── critic.py            # Critic + Reviser
├── orchestrator.py      # Orchestrator 状态机
├── agents/
│   ├── character.py     # CharacterAgent
│   ├── director.py      # DirectorAgent
│   └── drafter.py       # Drafter
└── prompts/
    ├── loader.py         # Jinja2 环境 + render() 函数
    ├── prewriting_world.j2
    ├── prewriting_character.j2
    ├── outliner_acts.j2
    ├── outliner_chapters.j2
    ├── outliner_scenes.j2
    ├── character_agent.j2
    ├── director_review.j2
    ├── director_force.j2
    ├── state_extract.j2
    ├── drafter.j2
    ├── critic.j2
    └── reviser.j2

tests/
├── test_models.py
├── test_config.py
├── test_persistence.py
├── test_llm.py
├── test_prewriting.py
├── test_outliner.py
├── test_context_manager.py
├── test_agents.py
├── test_critic.py
├── test_scene_runner.py
├── test_orchestrator.py
└── test_e2e.py

config.yaml              # 默认配置（可复制后修改）
requirements.txt
```
