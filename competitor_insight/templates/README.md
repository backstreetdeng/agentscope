# templates/ · 洞察档案模板定义

本目录存放「深访用户洞察档案模板」的**定义文件**，供后端按维度校验档案、也供人阅读培训。前端下拉不读这里，读 `competitor_insight/web/templates.json`（经 `/competitor-insight/templates.json` 提供）。

## 文件说明

| 文件 | 用途 |
|---|---|
| `nev_user_insight_template.json` | 新能源模板 v1 机器可读定义（8 组 / 43 维，后端唯一事实来源） |
| `nev_user_insight_template.md` | 同结构人读版：维度清单、填写说明与合格标准、埃安RT 抽取示例 |
| `user_insight_archive_template.json` | 用户洞察档案模板 v1 机器可读定义（12 组 / 43 维，对齐原型 `P.TROWS`） |
| `user_insight_archive_template.md` | 同结构人读版：与原型 43 项的对齐校验、维度清单、柏君谕案例填写示例 |

## 新增一套模板（不改前端 JS）

1. 在本目录放两个文件：`<id>_template.json`（机器可读）+ `<id>_template.md`（人读）。
2. 在 `competitor_insight/web/templates.json` 的 `templates` 数组追加一条，`status` 填 `ready`；未就绪填 `pending` 并写 `reason`（说明卡在业务还是开发）。
3. 刷新页面即可在下拉中看到；`pending` 项自动不可选，并展示 `reason`。
4. 前端 `restore()` 会用清单里的 `id` 过滤已存选择，**禁止随意改已有 `id`**，否则用户上一次选择会失效。

## 版本管理

- 模板内容变更就升 `version`（v1 → v2），旧版本不原地改写；需要并存时分文件保留。
- `status: ready` 表示可用；`pending` 表示不可选，必须带 `reason`。
- 模板定义里的 `source_baseline` 记录结构基线：`nev_user_insight` 为埃安RT 本竞品用户洞察报告 P1–P11；`user_insight_archive` 为交互原型第 386 行 `P.TROWS`。
- 两套模板并存、互不替代，各自 43 维但分组依据不同；逐项差异见 [docs/template-vs-prototype-mapping.md](../docs/template-vs-prototype-mapping.md)。
