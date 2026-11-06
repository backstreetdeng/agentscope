# 竞品洞察「用户洞察档案」tab · 技术实施方案 v1

- 任务：BCI-004
- 日期：2026-11-06（v2：已完成真实库只读实测，§6 由预判改为实测）
- 状态：**方案已按用户拍板更新；本文件不产生业务代码、不建表**
- 已定决策：Q1 批准新建 `bci` schema 与 4 张表（`192.168.3.146:5432/vectordb`）；Q2 档案模型自动生成 + 只读，无人工填写入口；Q9 先 10 人试点再全量
- 数据核验：2026-11-06 已直连 `192.168.3.146:5432` 只读实测，43 维逐维计数见 [coverage.csv](coverage.csv)
- 口径提醒：业务口中的「① 用户洞察档案」= 当前页面导航里的 **tab ②「洞察档案」**（tab ① 已被「数据源筛选」占用）。本文技术标识统一用 `profile`，接口前缀 `/api/bci/archive/*`，避免与原型模块编号冲突。

---

## 0. 结论先行

| # | 决策 | 结论 | 理由 |
|---|---|---|---|
| D1 | 档案存储 | PostgreSQL 长表（`bci.archive` + `bci.archive_field`），一档案 N 行（当前模板 43） | 维度随模板变化，宽表会随模板升级改表结构；长表可按维度挂证据、算覆盖、做人工复核 |
| D2 | 模板驱动 | 表头、分组、类型、校验全部来自模板 JSON + 独立 `source-map.json`；前端零硬编码 | 已有两套模板同为 43 维但语义不同，写死 43 必然错 |
| D3 | 生成策略 | 确定性优先：`metadata` / `tag` 直取，只有综合类维度走 LLM | 63 人 × 43 维全量 LLM 既贵又不稳；标签表已有结构化值 |
| D4 | 反幻觉 | LLM 只允许返回候选证据 ID，不接受模型生成的原话文本；证据不属于该受访者则本次生成判失败，不落半份档案 | 与现有问答链路的 receipt/证据纪律一致，避免编造原话 |
| D5 | 生成执行 | 后台 job + 轮询（`archive_run` / `archive_run_item`），单人也可走同一通道 | 63 人批量耗时远超 HTTP 超时；ThreadingHTTPServer 可承载轮询 |
| D6 | 导出 | 真 `.xlsx`（openpyxl，内存返回）+ 单人 `.md`；不做伪 `.xls` | openpyxl 已在环境内；避免 HTML 改后缀的坏文件 |
| D7 | v1 不做 | 自由指令解析、多人并排查看、人工在线编辑、档案审批流 | 原型里的假进度、子串匹配、伪导出只是交互示意，不是需求 |
| D8 | 落地范围 | 先 10 人试点（选样见 §6.3），试点通过再全量 63 人 | 用户已拍板 Q9；试点可先暴露生成质量与 RT 空维问题 |
| D9 | 无来源维度 | 8 维照常显示，标注「本期无来源」并写明具体原因；不补题、不补访、不用模型兜 | **Q11 已拍板**（2026-11-06）；下周统一与业务对接 |
| D10 | 满意度评分 | 只对 13 位有明确分数的受访者生成；其余留空并显示「访谈中未给出明确评分 / 仅有描述性评价」，用醒目色标注，不用中性灰 | **Q12 已拍板**（2026-11-06）；下周与业务对接 |

**范围**：只做 tab ② 的读取、生成、证据回溯与导出。不做 tab ③ 即时分析、tab ④ 报告输出，不改智能问答链路。

---

## 1. 整体架构

### 1.1 分层与落点

```
home.html  [data-view=bci]
├── tab ① 数据源筛选   competitor_insight/web/bci.js      （已有，不改）
│      └── localStorage['bci.scope'] / window.BCI_SCOPE / bci:scope-applied
└── tab ② 洞察档案     competitor_insight/web/bci-profile.js  （新增）
       │  fetch /api/bci/archive/*
       ▼
app.py（只做路由与请求/响应装配）
       ▼
competitor_insight/server/
├── archive_api.py        接口编排：参数校验、错误码、二进制导出响应
├── template_registry.py  模板清单/定义/source-map 的加载与校验
├── archive_store.py      bci.* 读写（或文件后端，见 2.6）
├── archive_generator.py  确定性直取 + LLM 综合 + 硬门
├── quote_service.py      「找原话」检索
└── export_service.py     xlsx / md 生成（返回 bytes）
       │
       ├── competitor_insight/templates/*.json     模板与题项映射（只读）
       ├── PostgreSQL bci.*                        档案与运行记录（写）
       └── PostgreSQL user_insight.*               访谈、答案、证据、标签（只读）
```

新增文件清单（开发阶段才创建）：

| 文件 | 作用 |
|---|---|
| `competitor_insight/web/bci-profile.js` | tab ② 全部交互，自包含，暴露 `window.BciProfile` |
| `competitor_insight/web/bci-profile.css` | tab ② 样式，沿用 `bci.css` 的深蓝 token |
| `competitor_insight/server/archive_api.py` | 接口实现 |
| `competitor_insight/server/template_registry.py` | 模板加载/校验 |
| `competitor_insight/server/archive_store.py` | 存储层 |
| `competitor_insight/server/archive_generator.py` | 归档生成 |
| `competitor_insight/server/quote_service.py` | 原话检索 |
| `competitor_insight/server/export_service.py` | 导出 |
| `competitor_insight/templates/user_insight_archive.source-map.json` | 43 维 → 题号/标签/元数据字段映射 |
| `competitor_insight/tests/test_archive_*.py` | 单测与契约测试 |

共享文件只做最小改动：`home.html`（启用 tab、加 panel 容器、引入两个新资源）、`app.py`（注册 GET/POST 路由、POST 白名单、增加二进制响应方法）。

### 1.2 与 `bci.scope` 的衔接

`bci.scope` 当前结构（`bci.js` `buildScope()`）：

```json
{
  "version": 2,
  "datasources": {
    "quant_structured": ["2025"],
    "interview_parsed": "2025",
    "insight_template": "user_insight_archive",
    "flow_data": ""
  }
}
```

tab ② 进入和 `bci:scope-applied` 时读取该结构，按下列规则决定状态：

| scope 状态 | tab ② 行为 |
|---|---|
| `insight_template` 为空 | 阻断：提示「先在 ① 选择洞察档案模板」，给跳回 ① 的按钮 |
| 模板 `status != ready` 或定义文件缺失 | 阻断：显示模板不可用原因，不允许生成 |
| `interview_parsed != "2025"` | 允许查看已有档案；生成按钮禁用，提示「本次未选入 2025 年定性解析数据」 |
| `quant_structured` 有值 | 忽略并在页脚说明「档案只取定性深访，定量数据不参与本 tab」 |
| `flow_data` 有值 | 同上，当前无数据源 |
| 模板切换 | 重新拉取模板与受访者列表；旧模板档案保留在库中，不混入当前视图 |

约束：**tab ② 只读 scope，不回写 scope**；不自动触发生成。模板可用性以服务端 `templates.json` + 模板定义校验结果为准，不信任前端缓存。

### 1.3 与 tab ③④ 的边界

| tab | 负责 | 不负责 |
|---|---|---|
| ② 洞察档案（本任务） | 单人 × 模板维度的档案生成、读取、证据、导出 | 跨人聚合、比例计算、结论撰写、报告排版 |
| ③ 即时分析（后续任务） | 消费档案做聚合/对比/归因，产出分析结果 | 不直接写 `bci.archive*`，不改档案值 |
| ④ 报告输出（后续任务） | 消费档案 + ③ 结果生成 HTML/PPT | 不重算档案 |

依赖方向单向：② → ③ → ④。③ 只能通过 `/api/bci/archive/detail`（或后续批量只读接口）取数，不直连 `bci.*` 表；② 不 import ③ 的模块。

---

## 2. 数据模型

### 2.1 核心表（PostgreSQL）

> 状态：Q1 已批准。目标库 `192.168.3.146:5432/vectordb`，2026-11-06 已连通。本方案不建表，DDL 由具备 DDL 权限的账号在开发阶段执行一次；Web 服务只做 `SELECT/INSERT/UPDATE`。

```sql
CREATE SCHEMA IF NOT EXISTS bci;

-- 一次生成运行（单人/勾选/缺失补齐/全量共用）
CREATE TABLE bci.archive_run (
    run_id              uuid PRIMARY KEY,
    template_id         text NOT NULL,
    template_version    text NOT NULL,
    mode                text NOT NULL CHECK (mode IN ('single','selected','missing','all')),
    request_json        jsonb NOT NULL,
    status              text NOT NULL CHECK (status IN ('queued','running','completed','partial','failed','cancelled')),
    total               integer NOT NULL DEFAULT 0,
    done                integer NOT NULL DEFAULT 0,
    failed              integer NOT NULL DEFAULT 0,
    model               text,
    prompt_version      text,
    error_text          text,
    created_by          text NOT NULL DEFAULT 'local',
    created_at          timestamptz NOT NULL DEFAULT now(),
    finished_at         timestamptz
);

-- 运行内每个受访者的状态，支持断点续跑与逐人报错
CREATE TABLE bci.archive_run_item (
    run_id              uuid NOT NULL REFERENCES bci.archive_run(run_id) ON DELETE CASCADE,
    interview_id        text NOT NULL,
    status              text NOT NULL CHECK (status IN ('queued','running','done','failed','skipped')),
    error_text          text,
    updated_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, interview_id)
);

-- 一份档案 = 一个受访者 × 一个模板版本
CREATE TABLE bci.archive (
    archive_id          bigserial PRIMARY KEY,
    interview_id        text NOT NULL,              -- 逻辑引用 user_insight.interview，不建外键
    template_id         text NOT NULL,
    template_version    text NOT NULL,
    template_snapshot   jsonb NOT NULL,             -- 生成时的模板定义快照
    run_id              uuid REFERENCES bci.archive_run(run_id) ON DELETE SET NULL,
    revision            integer NOT NULL DEFAULT 1,        -- 同模板同版本内的重跑序号
    status              text NOT NULL CHECK (status IN ('ready','partial','failed','stale')),
    coverage_required   numeric(5,2) NOT NULL DEFAULT 0,   -- 必填维度有值率
    model               text,
    prompt_version      text,
    generated_at        timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (interview_id, template_id, template_version, revision)
);

-- 档案的维度值，一维一行
CREATE TABLE bci.archive_field (
    archive_id          bigint NOT NULL REFERENCES bci.archive(archive_id) ON DELETE CASCADE,
    dimension_id        text NOT NULL,
    group_id            text NOT NULL,
    fill_mode           text NOT NULL CHECK (fill_mode IN ('metadata','tag','llm','none')),
    value_text          text,
    value_json          jsonb,
    source_ref          jsonb NOT NULL DEFAULT '{}'::jsonb, -- 确定性来源：metadata 字段名 / tag_id
    no_data_reason      text,
    confidence          numeric(4,3),
    evidence_refs       jsonb NOT NULL DEFAULT '[]'::jsonb,
    review_status       text NOT NULL DEFAULT 'auto'
                        CHECK (review_status IN ('auto','ok','suspect','missing')),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (archive_id, dimension_id)
);

CREATE INDEX idx_archive_lookup ON bci.archive (template_id, template_version, revision DESC, status);
CREATE INDEX idx_archive_interview ON bci.archive (interview_id);
CREATE INDEX idx_run_item_status ON bci.archive_run_item (run_id, status);
```

授权（由具备 DDL 权限的账号执行，不由 Web 服务执行）：

```sql
GRANT USAGE ON SCHEMA bci TO user_insight_loader;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA bci TO user_insight_loader;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA bci TO user_insight_loader;
```

### 2.2 为什么是长表

1. 模板维度会变（现有 `nev_user_insight` 与 `user_insight_archive` 都是 43 维但语义不同），宽表每换模板就要 `ALTER TABLE`。
2. 证据、置信度、复核状态、无数据原因是**维度级**属性，宽表无法挂。
3. 覆盖率是 `count(有值)/count(必填)`，长表一条 SQL 即可，宽表要写 43 个 CASE。
4. 单人只有 43 行，63 人全量 2709 行，规模不构成理由。
5. 后续 ③ 聚合可直接 `GROUP BY dimension_id`，不需要解析 JSON 大字段。

### 2.3 证据引用格式

`evidence_refs` 为数组，单字段最多 5 条，每条：

```json
{
  "kind": "evidence",
  "id": "R001-Q020-E003",
  "question_id": 20,
  "speaker": "用户",
  "quote": "原话快照，最多 300 字",
  "source_missing": false
}
```

`kind` 取值：`answer`（答案级）、`evidence`（访谈证据）、`tag_evidence`（标签证据）。规则：

- `id` 必须是该受访者名下真实存在的记录；生成时校验归属，不匹配则本次生成判失败（不落半份档案）。
- `quote` 是**服务端从库中截取的快照**，不接受模型返回的文本。
- 读取时按 `id` 再查一次最新原话；查不到则 `source_missing=true`，界面显示「原话来源已失效」但仍保留快照，不静默删除。
- 不在 `evidence_refs` 中存音频路径、转写 URI、内部标签（`source_label`）。

### 2.4 模板升级与旧档案

- 档案唯一键包含 `template_version` 与 `revision`，**新版本或强制重跑都新增一行，不覆盖旧档案**；旧行标 `stale`。
- `archive.template_snapshot` 保存生成时的完整模板定义（分组、维度名、顺序、类型、选项、合格标准）。旧档案渲染只读快照，不读当前模板文件，避免模板改名后旧档案错位。
- 同名同版本重跑：`revision = max(revision)+1`。详情接口默认取最高 `revision`；审核或回溯时可传 `revision` 查看历史。
- 同一受访者存在多个模板版本时，默认显示最新版本；旧版本标 `stale`，页面提示「模板已升级，可重新归档」，不做自动迁移。
- 不自动迁移的理由：维度语义可能变化，字段对字段搬运会制造假数据；需要重跑生成。
- 保留策略：档案与证据引用长期保留；`archive_run` 只在排障时需要，可按 180 天清理运行日志，不清理档案。

### 2.5 状态与完整度

- `ready`：所有必填维度要么满足证据要求，要么明确 `no_data_reason`。
  - `fill_mode=llm`：至少 1 条 `evidence_refs`；
  - `fill_mode=tag`：`source_ref.tag_id` 必填，`evidence_refs` 可空；
  - `fill_mode=metadata`：`source_ref.field` 必填，`evidence_refs` 可空；
  - `fill_mode=none`：必须有 `no_data_reason`。
- `partial`：存在必填维度既无值也无 `no_data_reason`。
- `failed`：生成异常且无可落库结果。
- 指标分开算，避免把「无数据」算成「已覆盖」：
  - `coverage_required` = 有值必填维度 / 必填维度总数
  - `completeness` = （有值 + 已注明无数据）必填维度 / 必填维度总数（接口返回，不落库）

### 2.6 降级方案：文件后端（DDL 已批准，仅作应急）

Q1 已批准建表，默认走数据库。若执行阶段 DDL 因权限或审批卡住，可用同一 Python Protocol 切换到文件后端，不阻塞前端开发：

存储接口保持同一 Python Protocol，切换实现即可：

```
runtime/competitor-insight/archives/<template_id>/<version>/<interview_id>-r<revision>.json
runtime/competitor-insight/runs/<run_id>.json
```

单文件结构 = `archive` + `fields` 的同一 JSON 契约；写入用临时文件 + `os.replace` 原子替换。限制：跨档案聚合需遍历文件（63 份可接受），无数据库级并发控制（当前单用户本地服务可接受）。**默认仍推荐数据库方案**，文件后端只作为授权未通过时的降级，不作为长期方案。

---

## 3. 模板驱动机制

### 3.1 加载链路

1. 读 `competitor_insight/web/templates.json`，取 `status=ready` 且 `id` 匹配的条目。
2. 校验 `definition` 路径必须位于 `competitor_insight/templates/` 下（`Path.resolve()` 后前缀比对），拒绝任意路径。
3. 加载模板定义 JSON，做结构 + 语义校验（见 3.4）。
4. 加载同名 `*.source-map.json`，校验每个维度恰好一条映射。
5. 进程内按文件 `mtime + size` 缓存；文件变化自动重载，无需重启服务。

### 3.2 题项映射文件（新增，不改模板本体）

`competitor_insight/templates/user_insight_archive.source-map.json`：

```json
{
  "template_id": "user_insight_archive",
  "template_version": "v1",
  "dimensions": {
    "purchase_attribute": {
      "mode": "metadata",
      "field": "purchase_type",
      "allowed_columns": ["purchase_type"]
    },
    "purchased_model_owned": {
      "mode": "metadata",
      "field": "vehicle_model"
    },
    "purchase_budget": {
      "mode": "tag",
      "question_ids": [12],
      "tag_names": ["购车预算"]
    },
    "archive_summary": {
      "mode": "llm",
      "question_ids": [1, 7, 20, 21, 68],
      "max_evidence": 5
    },
    "first_choice_ranking": {
      "mode": "none",
      "reason": "85 题中无首选排序题，不推断顺序"
    }
  }
}
```

规则：

- `mode=metadata`：只允许 `interview` 表白名单字段（`city` / `vehicle_model` / `purchase_type`），不接受任意 SQL 字段名。
- `mode=tag`：优先用 `tag.mapped_question_ids` 与 `question_ids` 求交集；`question_ids` 必须 1–85；`tag_names` 必须在 `user_insight.tag` 中出现过（S1 盘点时校验）。
- `mode=llm`：只把 `question_ids` 对应的答案/标签/证据送入模型，不喂整份转写。
- `mode=none`：直接生成 `no_data_reason`，不调用模型，不猜。
- 每个维度必须恰好出现一次；缺映射或多映射都视为模板不可用。

### 3.3 前端如何被模板驱动

| 模板字段 | 前端用法 |
|---|---|
| `groups[].order`（数组顺序） | 决定模块列顺序与 `rowspan` 跨度 |
| `dimensions[]` 数组顺序 | 决定行顺序；不按名称排序、不按分组重排 |
| `dimensions[].group` | 决定归属模块；找不到分组即校验失败 |
| `dimensions[].name` | 子项列文本 |
| `dimensions[].type` | `text` 原样；`enum` 单选 chip；`multi` 多值用「、」连接；`number` 右对齐并保留原始精度 |
| `dimensions[].options` | 枚举校验与展示；非法值标红并进入待复核 |
| `dimensions[].required` | 覆盖率分母；缺失在表头总览计数 |
| `dimensions[].qualified` | 仅作为生成提示与人工复核参考，**不做机器语义判定** |

前端不在任何位置写死维度数量、分组名或 43 这个数字；以模板返回的数组长度为准。现有两套模板都恰好 43 维只是事实，不是契约。

当前 `user_insight_archive` 的实际类型分布（用于 S2 单测样例）：`enum` 2 个（`purchase_attribute`、`kol_influence`），`multi` 2 个（`info_channels`、`content_format_preference`），`number` 1 个（`satisfaction_score`），其余为 `text`；`required=false` 共 5 个（`personality_interest_social`、`sales_marketing_attention`、`purchased_model_compared`、`compromise_points`、`loyal_repurchase_reason`），覆盖率分母只计 `required=true`。

### 3.4 模板校验规则

结构校验（jsonschema 或手写，环境已有 `jsonschema`）：

1. 必填：`template_id`、`version`、`name`、`groups`、`dimensions`。
2. `groups[].id` 唯一且非空；`dimensions[].id` 唯一且非空。
3. 每个 `dimensions[].group` 必须存在于 `groups`。
4. `type` ∈ `text / enum / multi / number`。
5. `enum` / `multi` 必须有非空 `options`；`number` 的 `options` 必须为空。
6. `required` 必须是布尔值。
7. `version` 与 `templates.json` 中的 `version` 一致，不一致拒绝加载。
8. source-map：43 个维度全覆盖、无多余 key；`question_ids` 在 1–85；`metadata.field` 在白名单。

校验失败时接口返回 `template_invalid`，页面阻断并列出第一条失败原因；不降级成"空表"。

---

## 4. 后端接口

所有接口前缀 `/api/bci/archive`，响应统一：

- 成功：`{"ok": true, "data": ...}`
- 失败：`{"ok": false, "error": {"code": "...", "message": "..."}}`，不返回堆栈。

| # | 方法 | 路径 | 入参 | 出参 | 服务哪个交互 |
|---|---|---|---|---|---|
| 1 | GET | `/template` | `template_id` | 模板分组 + 维度（按模板顺序） | 首屏渲染表头 |
| 2 | GET | `/respondents` | `template_id`、`keyword`、`limit`、`offset` | 受访者列表 + 每人档案状态/完整度 | 左侧列表 |
| 3 | GET | `/detail` | `interview_id`、`template_id`、`version`（可选）、`revision`（可选） | 档案 + 全部维度字段 + 证据 | 右侧档案表 |
| 4 | POST | `/generate` | `interview_ids[]`、`template_id`、`mode`、`force` | `run_id`、`total` | 生成/重新归档 |
| 5 | GET | `/run` | `run_id` | 运行状态、计数、逐人结果 | 进度日志轮询 |
| 6 | GET | `/raw` | `interview_id`、`limit` | 标签分组 + 答案摘要 + 证据节选 | 「定性解析数据（节选）」 |
| 7 | GET | `/quote` | `interview_id`、`keyword`、`limit` | 命中列表（答案/证据/标签/档案值） | 「找原话」 |
| 8 | POST | `/export` | `interview_ids[]`、`template_id`、`version`、`format` | 二进制 xlsx / md | 导出 |

### 4.1 关键接口契约

`GET /respondents` → `data`：

```json
{
  "template_id": "user_insight_archive",
  "template_version": "v1",
  "total": 63,
  "items": [
    {
      "interview_id": "R001",
      "respondent_code": "R001",
      "city": "广州",
      "vehicle_model": "唐L",
      "purchase_type": "换购",
      "archive": {
        "status": "ready",
        "version": "v1",
        "coverage_required": 81.4,
        "completeness": 95.3,
        "generated_at": "2026-11-06T20:10:00+08:00"
      }
    }
  ]
}
```

`GET /detail` → `data`：

```json
{
  "template": {"template_id": "user_insight_archive", "version": "v1", "name": "用户洞察档案模板"},
  "archive": {"status": "ready", "coverage_required": 81.4, "generated_at": "..."},
  "fields": [
    {
      "dimension_id": "purchase_attribute",
      "group_id": "ownership",
      "value_text": "换购",
      "value_json": null,
      "source_ref": {"kind": "metadata", "field": "purchase_type"},
      "fill_mode": "metadata",
      "no_data_reason": null,
      "confidence": 1.0,
      "review_status": "auto",
      "evidence_refs": []
    },
    {
      "dimension_id": "purchase_budget",
      "group_id": "ownership",
      "value_text": "20-25 万",
      "value_json": null,
      "source_ref": {"kind": "tag", "tag_id": "T-R001-012-购车预算"},
      "fill_mode": "tag",
      "no_data_reason": null,
      "confidence": 0.9,
      "review_status": "auto",
      "evidence_refs": [
        {"kind": "tag_evidence", "id": "TE-R001-012-02", "question_id": 12, "speaker": "用户", "quote": "预算大概二十多万，最多不超过二十五。", "source_missing": false}
      ]
    }
  ]
}
```

> 以上 JSON 中的编号、预算与原话均为结构示例，不是真实受访者数据。

无档案时返回 `200` + `archive: null` + `fields: []`，由前端渲染空态；不用 404 区分，避免把"没生成"当错误。

`POST /generate` 请求与响应：

```json
{"interview_ids": ["R001", "R002"], "template_id": "user_insight_archive", "mode": "selected", "force": false}
```

```json
{"ok": true, "data": {"run_id": "6f1c...", "status": "queued", "total": 2, "skipped": 0}}
```

- `mode=selected`：生成给定 ID；`missing`：只补无档案/`partial`；`all`：全部 63 人。
- `force=false` 且已有 `ready` 档案 → 计入 `skipped`，不重复消耗模型调用。
- 同一时刻只允许一个 `running` 运行；已有运行时返回 `409 run_in_progress` 并附 `run_id`，前端改为轮询已有运行。

`GET /run` → `data`：

```json
{
  "run_id": "6f1c...",
  "status": "running",
  "total": 63,
  "done": 17,
  "failed": 1,
  "items": [
    {"interview_id": "R001", "status": "done", "error": null, "updated_at": "..."},
    {"interview_id": "R018", "status": "failed", "error": "evidence_not_found", "updated_at": "..."}
  ]
}
```

`GET /quote` 检索范围：

- `answer.answer_text`、`evidence.quote_text`、`tag_evidence.quote_text` 使用 `ILIKE '%keyword%'`，每人最多 50 条；`tag_evidence` 本身无 `interview_id`，必须 `JOIN user_insight.tag USING(tag_id)` 后再按 `tag.interview_id` 过滤。
- 同时匹配当前模板档案的 `value_text`，命中标记 `kind=archive` + `dimension_id`。
- 关键词长度 1–30，转义 `%` / `_`；结果文本由前端 `textContent` 渲染，禁止 `innerHTML` 拼接。
- 当前只有 5355 条答案 + 81437 条证据 + 45244 条标签证据，按 `interview_id` 过滤后为单人量级，`ILIKE` 足够；不引入 pg_trgm。

`POST /export`：

- `format=xlsx`：1–63 人合并，一人一列。
- `format=md`：仅允许 1 人；多人返回 `400 md_single_only`。
- 响应头：`Content-Type` + `Content-Disposition: attachment; filename*=UTF-8''<encoded>`；正文为字节流。
- 导出前校验：所选每人都有当前模板版本的档案，缺失则 `409 archive_missing` 并列出编号，不导出半份文件。

### 4.2 权限与数据边界

- 与现有 `/api/insight/*` 一致：本地服务、无登录、无 token。当前 `HOST=0.0.0.0`，局域网可访问，这是一个既有风险，见 §8。
- 接口与导出只暴露 `interview_id` / `respondent_code` / 城市 / 车型 / 购车类型，不返回姓名、`source_label`、转写 URI、音频路径。
- `created_by` 固定 `local`；将来接入登录后再替换为账号标识。
- `app.py` 的 `do_POST` 白名单需新增：`/api/bci/archive/generate`、`/api/bci/archive/export`。GET 不需要白名单，但需在 `do_GET` 增加路由分支。
- 新增一个通用 `_send_bytes(data, content_type, filename)`（约 8 行）用于导出；不复用 `_send_file`，避免把导出文件落到 `outputs/` 或扩大静态目录白名单。

### 4.3 生成流水线（`archive_generator`）

单人一次生成的固定步骤，顺序不可调换：

1. **取数**：按 `source-map` 的 `question_ids` 取该人的 `answer`、`tag`、`evidence`、`tag_evidence`；不加载其他受访者、不加载未映射题目。
2. **确定性填充**：`metadata` 直接读白名单字段；`tag` 取交集后的标签值，按模板 `options` 做同义词归一（如"换购/置换"→`换购`）。无法归一的标签值不硬塞，落 `review_status=suspect` 并保留原值。
3. **分批**：仅把 `mode=llm` 的维度按 `group_id` 分批；单批字符预算 ≤ 40k（答案 + 候选证据），最多 4 个分组。`mode=none` 直接写 `no_data_reason`，不进入模型。
4. **候选证据**：每批附带候选清单，格式 `{id, question_id, speaker, quote(≤200字)}`；只允许模型从这个清单选 ID。
5. **模型调用**：复用 `utils/model_factory.build_model` 与 `utils/model_routing.py` 的默认路由；`temperature=0.2`；要求纯 JSON 输出，解析失败重试 1 次，仍失败则本人 `failed`，错误码 `llm_output_invalid`。
6. **硬门校验**（任一失败即该人失败，不落半份档案）：
   - 维度 ID 必须在本批范围内且不重复；
   - `enum` / `multi` 值必须命中模板 `options`；
   - `evidence_refs[].id` 必须属于本人且在本批候选清单内；
   - 证据要求按 `fill_mode` 区分：`llm` 非空值至少 1 条 `evidence_refs`；`tag` 必须有 `source_ref.tag_id`；`metadata` 必须有 `source_ref.field`；`none` 必须有 `no_data_reason`；
   - 模型返回的 `quote` 字段一律忽略，原话由服务端按 ID 截取。
7. **落库**：全部批次通过后，一个事务写入 `archive` + 该模板全部 `archive_field`（当前 43 条）；任一批失败则不写，`archive_run_item` 记 `failed` + 错误码，继续处理下一位。

约束：

- 不占用 `AGENT_RUN_LOCK`（避免批量归档期间智能问答不可用）；使用独立的 `BCI_GENERATE_LOCK`，同一时刻只跑一个 `archive_run`。
- 默认并发 2 个受访者；失败重试只针对 `failed` 项，不重跑 `done`。
- `prompt_version` = 模板 ID + 模板版本 + 提示词文件的 SHA-256 前 12 位，写入档案，便于回溯。
- 已 `ready` 且 `force=false` 的人直接 `skipped`，不产生模型调用。

---

## 5. 前端设计

### 5.1 页面结构

```
<section class="bci-profile">
  <header class="bp-toolbar">
    <div class="bp-scope">模板：用户洞察档案模板 v1 · 63 人</div>
    <div class="bp-actions">
      <button>生成缺失档案</button>
      <button>重新归档当前</button>
      <button class="primary">导出 Excel（已勾选 N 人）</button>
      <button>下载 MD</button>
    </div>
  </header>

  <div class="bp-run" hidden>            <!-- 真实进度，不用假日志 -->
    <div class="bp-run__bar"><i style="width:27%"></i></div>
    <ol class="bp-run__log"></ol>
  </div>

  <div class="bp-cols">
    <aside class="bp-list">
      <div class="bp-list__head">用户列表 · 63 人 · 已勾选 2</div>
      <input class="bp-list__search" placeholder="搜索编号 / 城市 / 车型">
      <ul class="bp-list__items"><!-- 63 项 --></ul>
    </aside>

    <main class="bp-doc">
      <div class="bp-doc__head">
        <h3>用户洞察档案</h3>
        <span class="bp-doc__meta">R012 · 广州 · 唐L · 换购 · 生成于 2026-11-06 20:10</span>
      </div>
      <div class="bp-doc__table"><!-- 按模板渲染：分组数 × 维度数 rowspan 表 --></div>
      <section class="bp-raw"><!-- 定性解析数据（节选） --></section>
      <section class="bp-quote" hidden><!-- 找原话结果 --></section>
    </main>
  </div>
</section>
```

### 5.2 状态机

| 状态 | 触发 | 表现 |
|---|---|---|
| `blocked_no_template` | scope 无模板 | 空态卡片 + 「去选择模板」按钮（切回 tab ①） |
| `blocked_template_invalid` | 模板校验失败 | 错误原因 + 不显示表格 |
| `loading` | 首次进入 | 骨架条；不显示"正在分析"等伪文案 |
| `no_archive` | 当前人未生成 | 表格显示维度结构，内容列显示「未生成」，主按钮「生成本人档案」 |
| `generating` | 有运行中 job | 进度条 + 逐人日志；表格只读，禁止重复提交 |
| `ready` | 档案存在 | 正常表格 + 证据 chip |
| `partial` | 缺必填 | 顶部提示「N 个必填维度未归档」，缺失行标黄 |
| `partial_source` | 当前模板无档案但有其他版本 | 提示「模板已升级/切换」，给重新归档按钮 |

### 5.3 渲染与性能

- 左侧 63 条、右侧按模板行数（当前两套模板均为 43 行），总量固定且小，**不做虚拟滚动**，一次 DOM 渲染即可；搜索仅过滤左侧列表。
- 表格用 `document.createElement` + `textContent` 构建，禁止把档案值拼进 `innerHTML`（模型输出不可信）。
- 列宽：模块 120px、子项 150px、内容自适应；`<colgroup>` 固定前两列，内容列 `word-break: break-word`。
- 表头 `position: sticky; top: 0`；模块列 `position: sticky; left: 0`，横向滚动时保持可读。
- 分组底色沿用现有蓝色系（`#EEF4FF` / `#F7FAFF`），不引入新主色；语义色只用 `--bci-ok` / `--bci-bad`。
- 字体与尺寸沿用 `bci.css`：正文 13px、辅助 11.5px、行高 1.65；不新设一套 token。
- 窄屏（<1100px）：左右栏上下堆叠，表格允许横向滚动，最小宽度 720px。

### 5.4 证据与原话

- 有 `evidence_refs` 的字段显示 `证据 N` 小 chip；点击弹出 popover：说话人、题号、原话、来源类型（答案/证据/标签证据）。`metadata` / `tag` 直取且无引语的字段不显示证据 chip，改为在行尾标注来源（如「来源：购车类型字段」「来源：标签 购车预算」）。
- `source_missing=true` 时 chip 变灰并显示「来源已失效」，仍可看快照。
- 「定性解析数据（节选）」按 `content_group` 分组展示标签与代表原话，默认每家 10 条，可「加载更多」；说话人已分离时用户/访员分色，与原型一致。
- 「找原话」：输入关键词 → 调 `/quote` → 结果列表按答案/证据/档案值分组，命中词用 `<mark>` 包裹（先 `textContent`，再用文本节点拆分，禁止整段 innerHTML）。

### 5.5 导出

- xlsx 结构：
  - Sheet `洞察档案`：第 1 行标题（合并单元格），第 2 行 `模块 | 子项 | R001 | R002 ...`，第 3–45 行 43 维内容；冻结 `C3`。
  - Sheet `口径与证据`：模板 id/版本、生成时间、模型、prompt 版本、每人覆盖率/完整率、无数据维度清单；证据明细（受访者/维度/证据 ID/原话）单独放 Sheet `证据`，避免主表过宽。
  - 单元格样式：模块列与表头深蓝底白字，子项列浅蓝底，内容 `wrap_text=True`，列宽 45，不合并数据行。
- md 结构：`# 用户洞察档案 · R012（广州 · 唐L）` + 按分组二级标题 + `- **子项**：值` + 末尾「证据索引」列表。
- 文件名：`用户洞察档案_<模板名>_<N>人_YYYYMMDD.xlsx` / `用户洞察档案_<编号>_<城市>.md`。
- 前端用 `fetch → response.blob() → URL.createObjectURL → a.download`，不使用服务端静态目录中转。

### 5.7 无来源维度与缺失评分的呈现（Q11/Q12 已拍板）

**无来源维度（8 个）**：`kol_influence`、`first_choice_ranking`、`rt_awareness_channel`、`rt_attraction_ranking`、`rt_concerns`、`rt_expectations`、`reception_expectation`、`loyal_repurchase_reason`。

- 页面**照常渲染这 8 行**，不隐藏、不合并、不让模型生成内容。
- 内容格显示固定文案：`本期无来源`，下一行用辅助字号写明具体原因，取自 `source-map.json` 的 `no_source_reason`，例如：
  - KOL/KOC：`85 题大纲无 KOL/KOC 相关提问，标签体系也未覆盖`
  - 首选率：`85 题无「按维度首选排序」题，现有车型清单无法计算首选率`
  - RT 四维：`63 位受访者中仅 3 人提及埃安，访谈未覆盖 RT 认知`
  - 接待期待：`Q63 只询问服务评价，未询问接待期待`
  - 老车主复购：`当前 63 人无埃安车主，该维度对样本不适用`
- 视觉：`--bci-nosource` 底色 + 左侧 3px 竖线，文字用正文色，不用"加载中/暂无数据"这类会让人以为是系统故障的措辞。
- 导出 xlsx 保留该行，内容写「本期无来源：<原因>」；不写空字符串。
- 后端这三态记为 `status=failed` + `coverage {should_check:63, checked:63, hit:0}`，接口不得把 0 省略成字段缺失。

**满意度评分（13/63）**：

- 有明确分数的 13 人：写入 `value_text`（如「8 分」）与 `value_json.score`，`fill_mode=llm` 且必须通过「该数字确实出现在 Q59 答案中」的硬校验，并附证据 ID。
- 其余 50 人：`fill_mode=none`，`no_data_reason` 按实际情况分两种：
  - `访谈中未给出明确评分`
  - `仅有描述性评价，无明确评分`
- 视觉：黄色/橙色警示块（`--bci-warn`），左侧竖线 + `no_data_reason` 全文，**不得用灰色弱化**；鼠标悬停不显示伪造分数。
- 接口返回 `score_source: "explicit" | "missing"`，前端据此配色，不靠文本判断。

### 5.8 明确不做

- 不做自由文本指令解析。原型输入框里的"重新归档李炜坤"等指令，v1 用明确按钮替代；若业务坚持保留输入框，需另立 Agent 意图解析任务（见 §8 Q3）。
- 不做假进度日志：只展示 `archive_run_item` 的真实状态。
- 不做伪 `.xls`（HTML 改后缀），不做客户端拼表格下载。
- 不做多人并排查看；多人只在导出时合并。

---

## 6. 数据来源现状

### 6.1 已核对的数据资产

来源：`reference_docs/03_数据底座说明/README_用户洞察智能体数据底座_v1.md`、`ops/import_user_insight.py`、`reference_docs/02_工程事实依据/用户洞察智能体_访谈Schema_20261030.sql`、BCI-001/BCI-002 任务记录。

| 资产 | 规模 | 状态 | 对本 tab 的作用 |
|---|---|---|---|
| 定性深访 | 63 人（项目 `2025H2-depth-interview`） | 已入库 | 档案的唯一样本来源 |
| 85 题答案 | 5355 条 = 63 × 85 | 已入库 | 维度取值与证据的主来源 |
| 访谈证据 | 81437 条 | 已入库 | 原话回溯；单人约 1293 条；61 人结构化答案、2 人 DOCX 回退，时间精度由 `time_precision` 区分 |
| 定性标签 | 5355 条 = 63 × 85 个标签位 | 已入库 | 结构化取值；标签名按题复用，distinct 数量由 S1 精确核对 |
| 标签证据 | 45244 条 | 已入库 | 标签级原话 |
| 定量问卷 2023/2024 | 未入库 | 无表 | 不参与本 tab |
| 定量问卷 2025 | 1380 行 · 1324 题项 | 已入库 | 不参与本 tab（档案只取定性） |
| 2026 定性深访 | 音频未解析 | 不可用 | 不参与本 tab |
| 增换购流水 | 未提供 | 无 | 不参与本 tab |
| 外部口碑/投诉 | 有表（public） | 与深访不同源；`user_insight_loader` 当前无权限 | 不参与本 tab |

补充事实（2026-11-06 只读实测，非预判）：

- `interview` 表有 `city`、`vehicle_model`、`purchase_type`、`respondent_code`、`metadata`，**没有姓名、年龄、性别、收入列**；`metadata` 只含 `doc_title`、`tag_workbook`、`source_result_dir` 与 2 人的 DOCX 回退告警，**不含任何人口统计字段**。人口统计只能来自答案（Q68/Q72 等）与标签。
- 对外只暴露 `respondent_code`，因此页面用编号 + 城市 + 车型标识人，不用原型里的姓名。
- 63 人分布于天津 / 沈阳 / 深圳 / 重庆；`vehicle_model` 无一台埃安，**埃安老车主 = 0 人**；`purchase_type` 覆盖首购 / 增购 / 换购。
- `question` 表恰好 85 题，编号 Q1–Q85，分「车辆购买及对比过程 / 市场认知 / 车辆使用过程 / 用户画像」四大段与 A/B/C 子段。
- `tag` 表 distinct `tag_name` = 85 个，与流水线第 3 步「全量标签」一一对应；`tag.mapped_question_ids` 给出标签允许题号白名单，`tag.trust_status` 给出可不可信（串题 / 格式失败）。
- 标签并非「63 人都有值」：85 个标签位 × 63 人 = 5355 行，其中 `extraction_status` 为 `not_asked` 1017 行、`not_applicable` 302 行；`trust_status≠可信` 623 行（其中 `不适用` 252、真实不可信 371，原因含串题、格式失败、value 混属性等）；`tag_value` 为「未提及。」1017 行。**行存在 ≠ 有可用值**，§6.2 的命中数已按「非空 + 非未提及 + trust_status=可信」过滤。
- 流水线第 2 步（85 题提取）产出的是**逐题答案 + 时间证据**，粒度是「人 × 题」；第 3 步产出的是**人 × 85 个标签**，粒度是「人 × 标签」，并回挂 `mapped_question_ids`。两者都没有「43 维」这一层，43 维是档案模板的**再聚合层**。
- 本机 2026-11-06 已可访问 `192.168.3.146:5432`（PostgreSQL 12.22），全部查询只读（`SELECT`），未建表、未改库。上轮记录的探查超时见 `outputs/competitor-insights/BCI-004/20261106-archive-design/db-probe.log`，本次实测结果见 `outputs/competitor-insights/BCI-004/20261106-coverage/`。

### 6.2 43 维覆盖实测

实测口径（与 BCI-005 三态一致）：

- **应查** = 63（当前项目全部受访者）；**实查** = 63（每维都执行了只读 SQL）；**命中** = 该受访者在该维有可用值。
- 标签口径：`tag_value` 非空、非 `未提及%`、非 `not_asked/not_applicable/拿不准`，且 `trust_status='可信'`。**`partial` 表示命中 > 0 但不足 63，不代表 0。**
- `success`：可直接落值且命中率 ≥ 90%；`partial`：命中 > 0 但有缺口，或该维必须由 LLM 生成；`failed`：命中 = 0，当前无来源。
- 完整逐维明细（含 source、direct_hit、llm_material_hit、note）见 [coverage.csv](coverage.csv)；下表为摘要。

**总计：43 维中 success 19（44%）、partial 16（37%）、failed 8（19%）。必填 38 维中 success 17、partial 14、failed 7。**

| 分组 | 维度 | 归档方式 | 三态 | 命中/应查 | 依据（表 / 标签 / 题号） |
|---|---|---|---|---|---|
| summary | 用户简要总结 | llm | partial | 63/63 | 全部答案可作原料；必须 LLM 生成并绑定证据 |
| profile | 年龄/性别 | tag | partial | 45/63 | 年龄 tag（Q68）45；**性别 tag 全量 not_asked（0/63），Q68 未问性别** |
| profile | 行业/职业 | tag | success | 62/63 | 行业 + 岗位 tag（Q68/Q77） |
| profile | 个人/家庭年收入 | tag | success | 59/63 | 家庭年收入 / 个人年收入 tag（Q72） |
| profile | 家庭结构 | tag | success | 60/63 | 婚姻状况 + 子女数量 tag；同住人数 tag 全量未提及 |
| profile | 性格/兴趣/社交 | tag | success | 61/63 | 性格特点 + 兴趣爱好 tag（Q82/Q79） |
| profile | 消费观念 | tag | success | 62/63 | 消费观 + 支出结构 tag（Q83/Q84/Q73） |
| ownership | 拥车情况 | tag | success | 63/63 | 当前 / 增购前 / 换购前 / 保有车型 + 充电桩安装 tag |
| ownership | 已购/下定车型 | metadata | success | 63/63 | `interview.vehicle_model` |
| ownership | 购车预算 | tag | success | 60/63 | 购车预算 / 裸车价 tag（Q2）；63 行有值，3 行可信度过滤 |
| ownership | 购车属性 | tag | success | 63/63 | 首增换购属性 tag（Q1），**不再用 metadata.purchase_type** |
| ownership | 购车动机 | tag | partial | 45/63 | 购车原因 tag；18 人因「Q4 必须标最重要」格式失败被过滤 |
| consideration | 购车考虑优先级 | llm | partial | 62/63 | 有 TOP5 原料；严格「价格 > 燃料 > 车身」三轴仅 2/63，须重排 |
| consideration | 燃料类型考虑原因 | tag | success | 63/63 | 能源偏好 6 类原因 tag（Q10–Q19） |
| attention | 品牌/产品/服务排序 | llm | partial | 52/63 | **无题项问三轴；Q20 同时含「品牌+产品+服务」者 0/63**，只能推断 |
| attention | 品牌关注 | tag | success | 62/63 | 具体品牌 / 品牌类型 / 品牌看法 tag（Q37–Q42） |
| attention | 产品关注TOP5及细项 | tag | partial | 48/63 | 本次购车关注 tag 有 ≥5 项者 48；「恰好 5 项 + 细项」须 LLM 补 |
| attention | 营销/销售关注 | llm | partial | 52/63 | Q63 有售前售后评述 52；无标签，须归纳为诉求 |
| channels | 信息获取渠道 | tag | success | 60/63 | 汽车触媒偏好 + APP偏好 tag（Q80/Q81） |
| channels | 内容形式偏好 | llm | partial | 18/63 | Q81 只到「垂媒 vs 短视频」；车评人 / 长视频 / 参数对比仅 18 人有原料 |
| channels | KOL/KOC影响力 | none | **failed** | 0/63 | **85 题无 KOL 题**；全库仅 6 人偶然提到达人/博主，无法成维 |
| comparison | 核心对比车型 | tag | success | 63/63 | 核心对比车型 / 最终核心对比车型 tag（Q26） |
| comparison | 首选率 | none | **failed** | 0/63 | **85 题无「按维度首选排序」题**；Q26 只有车型清单，不能算首选率 |
| comparison | 已购/下定车型（对比组） | metadata | success | 63/63 | 与拥车组同源 `vehicle_model` |
| comparison | 战胜原因 | tag | success | 62/63 | 选择当前车辆的原因 tag（Q29） |
| comparison | 妥协点 | llm | partial | 6/63 | 无标签；Q29/Q59 明确提「妥协/接受/牺牲」者仅 6 |
| comparison | 放弃车型 | derived | success | 63/63 | 核心对比车型 − 最终车型，确定性派生 |
| comparison | 放弃原因 | tag | partial | 21/63 | 放弃原因 tag；**42 人因串题/格式失败被过滤**，仅 21 可用 |
| brand_impression | 对埃安品牌的印象（网约车影响） | llm | partial | 3/63 | **全库仅 R003 / R050 / R057 提及埃安**；无埃安专有题 |
| rt_cognition | 了解渠道 | none | **failed** | 0/63 | 85 题无埃安 RT 题 |
| rt_cognition | 埃安RT吸引力排序 | none | **failed** | 0/63 | 同上 |
| rt_cognition | 顾虑 | none | **failed** | 0/63 | 同上 |
| rt_cognition | 期望 | none | **failed** | 0/63 | 同上 |
| rt_cognition | 转化机会/风险 | llm | partial | 63/63 | 无 RT 题；只能用再购意向 tag 外推，**不能当作 RT 转化结论** |
| usage_scenario | 高频场景 | tag | success | 63/63 | 用车场景 tag 63；单程/日均里程 53、行驶区域 52 |
| usage_scenario | 场景需求 | llm | partial | 58/63 | 用车过程关注 tag 58，须归纳「场景 → 需求」 |
| usage_scenario | 充电需求 | tag | success | 63/63 | 充电桩 / 频次 / 地点 / 方式 tag（并集 63，单项 59） |
| usage_scenario | 续航需求 | tag | success | 61/63 | 纯电续航需求 tag（Q50） |
| satisfaction | 满意度评分 | llm | partial | 13/63 | **Q59 明确给数字分者仅 13**；其余必须落 no_data，不许折算 |
| satisfaction | 满意点 | tag | partial | 55/63 | 满意点 tag；8 人可信度过滤 |
| satisfaction | 不满意点 | tag | partial | 54/63 | 不满意点 tag；9 人可信度过滤 |
| satisfaction | 接待期待 | none | **failed** | 0/63 | Q63 只问「评价」不问「期待」；含期待/希望/建议者 0/63 |
| loyal_repurchase | 作为埃安老车主 为什么继续再买 | none | **failed** | 0/63 | **63 人购买车型无埃安，该维对当前样本不适用** |

### 6.3 对核心问题的直接回答

**问题一：85 题提取 + 全量标签提取，到底支不支持按 43 维归档？**

**支持 19 维可直接归档，16 维只能"带风险地生成"，8 维完全不支持。** 定性流水线的产出粒度是「人 × 85 题」和「人 × 85 标签」，43 维是模板层再聚合，因此支持程度取决于模板维度与 85 题的重合度，而不是流水线是否"质量够好"。

- 可直接归档（19）：profile 的大部分、拥车情况、购车预算/属性/动机中的高可信部分、燃料类型原因、核心对比车型、放弃车型、战胜原因、信息渠道、高频场景、充电与续航需求。这些维度的共同点是**85 题里有对应题，且第 3 步已把答案压成结构化标签**。
- 只能生成（16）：摘要、考虑优先级、品牌/产品/服务排序、产品 TOP5 细项、营销关注、内容形式、妥协点、场景需求、转化机会、满意度评分、埃安品牌印象。这些维度的共同点是**模板要求的粒度比 85 题更细或更综合**。
- 完全不支持（8）：KOL/KOC、首选率、RT 了解渠道/吸引力排序/顾虑/期望、接待期待、老车主复购。共同点是**85 题里没有这道题**，不是标签质量问题。

**问题二：哪些维度必然要靠 LLM 归纳？风险是什么？**

必然 LLM 的 10 维：`archive_summary`、`consideration_priority`、`brand_product_service_rank`、`product_attention_top5`、`sales_marketing_attention`、`content_format_preference`、`compromise_points`、`scenario_needs`、`satisfaction_score`、`conversion_opportunity_risk`。

- 风险最高的是 `satisfaction_score`（仅 13/63 有数字分，其余 50 人如果让模型"给个分"就是纯编造）和 `brand_product_service_rank`（三轴齐备 0/63）。
- 次高是 `compromise_points`（6/63 有明确表述）、`content_format_preference`（18/63 有原料）、`conversion_opportunity_risk`（无 RT 题）。
- 控制手段（已写入 §2.5 与 §8.1 Q11）：LLM 只返回证据 ID，原话由服务端截取；**该维没有任何可用原料时，必须落 `no_data_reason`，不允许模型自由补全**；`satisfaction_score` 只接受问答中出现过的数字，出现不了就留空。

**问题三：哪些维度当前完全没有来源？补访还是补题？**

8 维无来源，分三类处理：

1. **必须补题（不改访谈对象，只需在 85 题大纲加题）**：`kol_influence`（KOL/KOC 影响）、`first_choice_ranking`（按维度首选排序）、`reception_expectation`（接待期待，Q63 扩问即可）。这三项都是"问一句就有"的结构化信息，成本最低。
2. **必须补访（现有 63 人没被问到，补题也救不回来）**：`rt_awareness_channel`、`rt_attraction_ranking`、`rt_concerns`、`rt_expectations`。埃安 RT 是本品，而这 63 人是竞品车主，只有 3 人顺带提过埃安。**这 4 维在 10 人试点里应显式留空**，否则模型必然编造。
3. **样本结构不适用**：`loyal_repurchase_reason`（0 位埃安老车主），不是缺数据，是缺人群；要做得单独招埃安老车主样本。

**问题四：10 人试点怎么选，才能覆盖最多维度？**

先说明：8 个 failed 维度（KOL、首选率、RT 了解渠道/吸引力排序/顾虑/期望、接待期待、老车主复购）**无论选谁都覆盖不了**，所以试点目标不是"覆盖 43 维"，而是"把 35 个有来源维度尽量跑满，并暴露生成质量问题"。

建议选法（按 63 人真实标签可信度贪心 + 城市/购车属性配额）：

| 受访者 | 城市 | 购车属性 | 车型 | 入选理由 |
|---|---|---|---|---|
| R003 | 天津 | 增购 | 零跑B10 | **全库 3 个提及埃安者之一**，且 Q25–Q28 有完整放弃链路 |
| R050 | 天津 | 换购 | 日产N7 | 提及埃安智驾体验，可验证 RT 认知维度的"有/无"边界 |
| R057 | 重庆 | 换购 | 日产N7 | 提及埃安并给出负面品牌印象，是 `aion_brand_impression` 唯一可用样本 |
| R030 | 沈阳 | 首购 | 夏 | 唯一首购 + 沈阳，补齐首购人群 |
| R025 | 沈阳 | 增购 | 奇瑞iCAR V23 | 沈阳第二个，可信标签 74（前列） |
| R037 | 深圳 | 换购 | 智界R7 | 深圳第一个，可信标签 70 |
| R046 | 深圳 | 增购 | 腾势N9 | 深圳第二个，补 MPV/大车场景 |
| R005 | 天津 | 换购 | 银河A7 | 天津第三个，可信标签 73 |
| R010 | 重庆 | 换购 | 比亚迪夏 | 重庆第二个，补插混/大车 |
| R062 | 重庆 | 换购 | 铂智3X | 重庆第三个，补合资纯电 |

覆盖：4 城市（天津 3 / 重庆 3 / 沈阳 2 / 深圳 2）、3 种购车属性（首购 1 / 增购 4 / 换购 5）、3 个埃安提及者全部纳入。

试点验收应分开看：**19 个 success 维要求 10 人全部有值；16 个 partial 维允许标注"无数据"；8 个 failed 维不纳入试点判定**，只验证页面是否如实显示"无数据（未问到）"。

### 6.4 补数原则

1. **无题项 ≠ 可以推断**：8 个无来源维（含 `first_choice_ranking`、`brand_product_service_rank`、`rt_attraction_ranking`）**本期不补题、不补访**，照常显示并标注「本期无来源」+ 具体原因，不按文本提及顺序生成顺序。
2. **RT 维度**：现有 63 人只有 3 人提及埃安，RT 四维本期留空标「本期无来源」；补访属于新数据采集，另立任务，不塞进本 tab。
3. **评分**：只对答案中出现明确分数的 13 人生成；其余 50 人留空并显示「访谈中未给出明确评分 / 仅有描述性评价」，用醒目色标注，不折算、不预测。下周与业务对接。
4. **老车主**：当前 0 人适用；单人档案按事实填「不适用」，不生成。
5. **可信度过滤是硬门槛**：标签 `trust_status≠可信` 的值不得直接进档案；`放弃原因`（21/63）、`购车动机`（45/63）损失最大，需在 UI 上标注"结构化标签不可用，已回退到原文"或直接留空。
6. **2026/定量/流水**：不在本 tab 补，不伪造 2025 数据的外推。

---

## 7. 开发任务拆分与顺序

本任务先交付方案；用户确认后按下列步骤开发。步骤编号 `S0–S9`，依赖关系如图；不新建任务编号（如需拆号，需用户确认）。

```
S0 方案确认
 └─ S1 覆盖盘点 + source-map
     ├─ S2 模板注册与校验
     │   └─ S4 生成器（确定性 + LLM + 硬门）
     │       ├─ S5 读取接口
     │       │   └─ S7 前端页面
     │       │       └─ S8 导出
     │       └─ S6 写入接口 + job
     └─ S3 存储层（可与 S2 并行）
```

| 步骤 | 交付物 | 依赖 | 验收标准（可判定） |
|---|---|---|---|
| S0 | 本文件 + 开放问题答复 | 无 | Q1/Q2/Q9 已拍板；其余项按 §8.1 的建议默认执行并记录 |
| S1 | `user_insight_archive.source-map.json`；`coverage.csv`（43 行） | S0；DB 可达 | 43 维全部有且仅有一条映射；每维给出样本命中数、证据数、判定（有/稀疏/无）；`question_ids` 全部存在于 `question` 表；脚本只读，无写库。**进度：`coverage.csv` 已完成（2026-11-06 实测 43 维）；`source-map.json` 待开发第 2 步落盘** |
| S2 | `template_registry.py` + 单测 | S1 | 合法模板加载成功；缺分组、重复维度、非法 type、版本不一致、路径越界 5 类错误均被拒绝；两套 ready 模板都能通过 |
| S3 | `archive_store.py` + DDL/文件后端 + 单测 | S2 契约 | 同一人同模板重复写入为幂等 upsert；事务失败不留半份档案；按模板/版本/状态查询正确 |
| S4 | `archive_generator.py` + 提示词 + 单测 | S3 | metadata/tag 维度不调用模型；LLM 只返回候选证据 ID；伪造 ID、跨人证据、非法枚举三类输出被硬门拒绝；单人 fixture 生成 43 行 |
| S5 | 5 个 GET 接口 | S4 | 63 人列表返回完整；无档案返回 `archive:null`；非法模板返回 `template_invalid`；接口响应不含姓名/路径 |
| S6 | generate/run + 并发与续跑 | S4 | 单人运行完成；重复提交返回 409；服务重启后 `running` 项恢复为 `queued` 并可续跑；失败项只重跑失败人 |
| S7 | `bci-profile.js/css` + `home.html` 接入 | S5 | 表头/分组/43 行完全由模板生成；删掉任一维度模板后页面不报错；8 个状态可复现；证据 popover 与找原话可用；无 `innerHTML` 注入档案值 |
| S8 | `export_service.py` + 前端下载 | S5、S7 | 63 人 xlsx 可被 Excel/LibreOffice 打开；2 人合并列正确、43 行不串位；md 单人结构正确；文件名中文正常；不含姓名与本地路径 |
| S9 | 浏览器验收 + 证据 | S6、S8 | 真实 63 人列表、单人查看、多人导出、模板切换、空态、运行进度、找原话 7 项断言通过；`check_board.py` 与 `workspace_hygiene.py` PASS |

建议批次：

- 批次 1（数据与契约）：S1–S3。先把"哪些维度真的有数据"和"模板能否被机器校验"定死，避免前端返工。
- 批次 2（生成与接口）：S4–S6。先做单人，再按 §6.3 的 10 人试点名单生成，最后全量。
- 批次 3（界面与导出）：S7–S9。前端可先用 3 人真实档案（含 1 个埃安提及者）联调，不造假数据。

**试点验收口径（Q9）**：10 人 × 43 维中，19 个 success 维必须人人有值；16 个 partial 维允许「有值或明确无数据」；8 个 failed 维只验证页面如实显示「本期无来源」及原因。任一 LLM 维出现无证据 ID 的值即判试点失败。

### 7.1 实施顺序、依赖与共用文件闸门（2026-11-06 更新）

Q11/Q12 已拍板，批准进入开发。因为另一会话正在做首次入库提交，实施必须分成"不碰共用文件"与"需改共用文件"两段：

| 顺序 | 步骤 | 可写文件 | 依赖 | 完成标志 |
|---|---|---|---|---|
| 1 | 文档同步 | `docs/`、`tasks/` | 无 | Q11/Q12 入档、步骤拆分完成（本步已完成） |
| 2 | 契约层 | `server/template_registry.py`、`server/source_map.py`、`templates/*.source-map.json`、`tests/` | S1 | source-map 校验器对 43 维全绿；8 个无来源维带 `no_source_reason` |
| 3 | 存储层 | `server/archive_store.py`、`server/db.py`（新增）、`tests/` | S2 | `bci.*` 四表建好；幂等 upsert；事务失败不留半份 |
| 4 | 生成器 | `server/archive_generator.py`、`server/evidence_gate.py`、`tests/` | S3 | 19 维直取不调模型；16 维 LLM 只回证据 ID；伪造/跨人证据被拒 |
| 5 | 导出与查询 | `server/archive_api.py`、`server/export_service.py`、`server/quote_service.py`、`tests/` | S4 | 5 个 GET + generate/run 可用（未挂路由，curl 直调模块）；xlsx/md 单测通过 |
| 6 | **前端新模块** | `web/bci-profile.js`、`web/bci-profile.css` | S5 | 模块自包含，`window.BciProfile.mount(el, scope)` 可在临时页面试跑 |
| 7 | **共用文件接线（需闸门）** | `app.py`、`home.html`、`bci.js`、`templates.json`、`home.css`、`home.js` | 用户确认「入库完成」 | tab 可用、路由注册、模板可选 |
| 8 | 浏览器验收 | 无（只读） | 7 | 单人查看、10 人试点生成、导出、无来源维、13 人评分 6 项断言通过 |

**闸门规则**：

- 第 2–6 步只新增文件，不修改 `app.py`、`home.html`、`home.css`、`home.js`、`web/bci.js`、`web/templates.json`。
- 第 6 步的 `bci-profile.js` 不 import `bci.js`，只读 `window.BCI_SCOPE` 与 `bci:scope-applied` 事件；避免对共用文件产生反向依赖。
- 第 7 步开始前必须收到用户"入库完成"的明确消息；未收到时只做本地模块自测，不启动 7860 做页面验收。
- 数据库写入也属第 3 步：需先确认 `bci` schema 与 4 表已由有 DDL 权限的账号建好；未建好不执行写入测试。

---

## 8. 风险与开放问题

### 8.1 需要用户/业务拍板的开放问题

| # | 问题 | 结论 / 建议默认 | 状态 |
|---|---|---|---|
| Q1 | 是否批准新建 `bci` schema 与 4 张表，并授予 `user_insight_loader` 读写权限？ | **已批准**：在 `192.168.3.146:5432/vectordb` 新建 `bci` schema + 4 张表；DDL 见 §2.1。剩执行时由有 DDL 权限的账号跑一次，Web 服务不执行建表 | 已拍板 |
| Q2 | 档案由模型自动生成，还是人工填写/人工校核后再发布？ | **已拍板**：模型自动生成 + 只读；不做人工填写入口，不做在线编辑 | 已拍板 |
| Q3 | 原型里的「分析指令」输入框是否必须保留？ | 不保留，改为 3 个明确按钮 | 待确认 |
| Q4 | 63 位受访者是否覆盖埃安RT？未覆盖的 RT 维度是留空、补访还是不做？ | **实测：仅 3/63 提及埃安，0 人是埃安车主**；按 Q11 结论，RT 四维本期标「本期无来源」，不补访；下周与业务对接 | 已拍板 |
| Q5 | 档案列表展示全部 63 人（含未生成），还是只展示已生成？ | 全部展示 + 状态标记，便于知道缺口 | 待确认 |
| Q6 | 页面与导出是否需要姓名？ | 不需要，只用受访者编号 | 待确认 |
| Q7 | 导出格式是否只需 xlsx + md？是否需要 Word/PPT？ | 只做 xlsx + md | 待确认 |
| Q8 | 是否需要"复核通过/驳回"的审批流与留痕？ | v1 不做，仅保留字段级 `review_status` | 待确认 |
| Q9 | 63 人全量生成的模型成本与时延是否接受？是否先 10 人试点？ | **已拍板**：先 10 人试点；选样见 §6.3 问题四；试点通过后再全量 | 已拍板 |
| Q10 | 模板升级后旧档案如何处理？ | 不迁移，保留旧版本并提示重新归档 | 待确认 |
| Q11 | 8 个无来源维度（KOL、首选率、RT 四维、接待期待、老车主复购）在页面上如何呈现？ | **已拍板**：不补题、不补访；页面照常显示这 8 维，标注「本期无来源」并写明无法归档的具体原因；不用模型兜。下周统一与业务对接 | 已拍板 |
| Q12 | `satisfaction_score` 仅 13/63 有明确分数，其余如何处理？ | **已拍板**：只对有明确分数的 13 人生成，其余留空；显示「访谈中未给出明确评分 / 仅有描述性评价」，用醒目颜色标注，不用中性灰。下周与业务对接 | 已拍板 |

### 8.2 技术风险

| 风险 | 表现 | 对策 |
|---|---|---|
| 模型编造原话 | 档案有结论但原文找不到 | 模型只返回证据 ID；服务端截取原话；无证据字段判失败 |
| 证据 ID 失效 | 源数据重导入后 ID 变化 | `evidence_refs` 存快照；读取时校验并标 `source_missing` |
| 数据库可达性 | 2026-11-06 已连通并完成实测，但 LAN 库可能再次波动 | 生成前做连通性预检；不可达时不伪造覆盖率，直接返回 `partial` + 原因 |
| 无鉴权 + 局域网 | 任何能访问 7860 的人可读访谈原话/导出 | 沿用现状但显式记录风险；建议后续加访问控制（需用户决定，不在本任务擅自改） |
| 批量生成阻塞服务 | 63 人 × 多批模型调用 | 后台线程 + 2 并发；不占用 `AGENT_RUN_LOCK`；限制同一时间一个运行 |
| 模板与映射漂移 | 模板改了但 source-map 未改 | 启动/请求时校验维度全覆盖；不一致直接阻断 |
| 导出串列 | 多人列与 43 行顺序错位 | 以模板维度顺序为唯一行序；导出单测固定 2 人 × 43 行断言 |
| 无数据被当成结论 | 空值被模型"补全" | `mode=none` 直接落 `no_data_reason`；质量门禁止空值转推测 |

---

## 9. 方案阶段验收清单

| # | 用户原始要求 | 本文件位置 |
|---|---|---|
| 1 | 整体架构与三个 tab 的边界 | §1 |
| 2 | 数据模型（长表/JSON、受访者绑定、证据、模板升级） | §2 |
| 3 | 模板驱动机制（表头、分组、校验） | §3 |
| 4 | 后端接口清单（路径、入参、出参、权限） | §4 |
| 5 | 前端设计（结构、组件、设计语言、大数据量、真导出） | §5 |
| 6 | 数据来源现状（有数据/无数据分开） | §6（v2 实测，逐维见 `coverage.csv`） |
| 7 | 任务拆分、依赖、验收标准 | §7 |
| 8 | 风险与开放问题 | §8 |

**下一步**：用户复核 `coverage.csv` 与 §6 实测结论，并对 §8.1 的 Q3/Q5–Q8/Q10–Q12 给出意见（未答按建议默认）；确认后落 `source-map.json`，再按 §7 进入开发。方案未确认前不写业务代码、不建表、不启动 7860。
