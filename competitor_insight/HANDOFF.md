# 竞品洞察 · 最近交接

更新：2026-11-09（Asia/Shanghai）。新条目追加在最上面。写法见 [RULES.md](RULES.md) 第 9 节；本文件与 TASK.md 冲突时以 TASK.md 为准。

## 2026-11-09 · BCI-004 第二轮反馈：生成写错模板根因修复 + 找原话范围改版

- **根因（回答用户"为什么生成后还是未生成"）**：`ArchiveGenerator.__init__` 写死 `load_ready(ARCHIVE_TEMPLATE_ID)`，无视请求模板。用户在「新能源用户洞察模板」下点生成，任务显示完成，档案实际写到「用户洞察档案」名下——NEV 视图永远显示未生成。实测：R004 两次运行（16:38/16:40）completed 1/1，archive 行却是 user_insight_archive。另：用户截图选的 R003 从未生成过（它是试点 10 人之一，2026-11-07 已有档案）。
- **修复**：`generate()` 对缺 source-map 的模板直接抛 `template_not_generatable`（NEV 尚无题项映射，本就不能自动生成）；前端 NEV 模板下两个生成按钮禁用+提示、空态不出现生成按钮。要支持 NEV 生成需先补其 source-map（另立工作量）。
- **找原话范围（按用户拍板实现）**：勾选谁查谁（可多选，SQL `= ANY`），未勾选查全部 63 人；结果条目附受访者编号（tag_evidence 无受访者列，该类结果全局/多人检索下编号为空）；单人检索保留档案值联动。
- **按钮**：主按钮（primary）从「导出 Excel」换到第一位「生成本人档案」；已生成人禁用（只读），提示改用「重新归档当前」；导出 Excel 在无勾选时维持禁用。
- **数据说明**：R004 的 2 份档案按 user_insight_archive 语义生成、数据有效，**保留未删**（删除业务数据需用户授权）。
- **验证**：单测 125/125（新增 NEV 拒绝生成、全局检索、多人范围 3 例）；Playwright 7861 实测 12/12（徽标、守卫、主按钮、禁用态、两种检索范围、无 JS 错误）。未触碰 7860 与月报浏览器。
- **注意**：本轮含后端改动（`quote_service.py`/`archive_api.py`），**7860 重启后才生效**；前端 `bci-profile.js` 强刷（Ctrl+F5）即生效。是否重启 7860 待用户授权。
- **证据**：[20261109-feedback-fixes](outputs/competitor-insights/BCI-004/20261109-feedback-fixes/)（manifest 入库；verify.log 仅本机）。

## 2026-11-09 · BCI-004 用户 6 点反馈收口（3 处前端修复 + Q3/Q8 拍板）

- **拍板入档**：Q3「分析指令输入框」**不保留**、Q8「审批流」**暂不做**（设计文档 §8.1 与 TASK L01/L04 已更新）。
- **修复 1（状态标记）**：用户列表每行常显徽标——已归档/部分/失败/旧版/未生成；此前无档案的行不显示任何标记，用户无法判断是否已生成。
- **修复 2（联动）**：勾选列表复选框即把主区域切换到该受访者（此前勾选只影响批量导出、不联动查看，被误认为 bug）。
- **修复 3（按钮）**：右上按钮「生成缺失档案」改名「生成本人档案」，行为同步改为**只生成当前受访者**——原名实为批量补齐全量 63 人，与新名矛盾且有误触发全量模型费用的风险；全量批量仍可走接口（等用户放开）。
- **重要澄清（用户问"R001 没标记/未生成"）**：R001 已于 2026-11-08T23:28 生成，但 11 份档案全部属于「用户洞察档案模板」（`user_insight_archive`）；用户截图时页面选的是「新能源用户洞察模板」（`nev_user_insight`），该模板下 63 人均未生成，空态展示是正确行为。两套模板是不同的 43 维。
- **找原话范围（已核实，待用户定）**：当前实现=只检索**当前选中的那一位受访者**（未选人提示"请先选择一位受访者"），数据源为定性深访解析结果（`user_insight.answer/evidence/tag_evidence`），与列表勾选和 tab① 筛选无关；"不选人→全部用户检索"是新增需求，等用户拍板。
- **验证**：临时 7861 服务 + Playwright 5/5 PASS（徽标、联动、按钮名、无 JS 错误）；未触碰 7860，`bci-profile.js` 按请求从磁盘读取，**浏览器 Ctrl+F5 强刷即可生效，无需重启**。
- **证据**：[20261109-feedback-fixes](outputs/competitor-insights/BCI-004/20261109-feedback-fixes/)（`manifest.json` 入库；`verify.log` 仅本机）。

## 2026-11-09 · BCI-004 L10 已解除（schema 属主转交完成）

- **执行**：DBA 用 `postgres` 账号执行 `ALTER SCHEMA bci OWNER TO user_insight_loader;`，用户在数据库 GUI 实测成功（240ms、返回 0 行）。此前 `vectordb` 账号 2/2 次失败（42501，两角色均非 superuser、无成员关系，无法自我授权）。
- **验证**：复跑 `ops/bci_schema_owner.py` —— owner=`user_insight_loader`、alter=skipped(already owner)、loader 建表/插入/查询/删除/删表冒烟 **PASS**；`bci.archive` 11 行、`bci.archive_field` 473 行（较 2026-11-08 的 10/430 增加 1 份档案 43 行，应为 7860 页面新生成）。
- **盘点（顺带回答用户）**：实例内 2 个数据库（`postgres` 系统默认、`vectordb` 业务库）；`vectordb` 内用户 schema 7 个——本项目只用 `user_insight`（9 表，只读源）与 `bci`（4 表，档案存储，属主已转 loader）；其余 `miit`(4)/`policy_monitor`(18)/`policycrawlerdb`(44)/`public`(33)/`staging`(4) 属其他功能。
- **状态**：L10 关闭；BCI-004 未关闭项剩 L01（开放问题）与 L05/L07/L08（数据缺口，已决策维持）。全量 63 人仍未跑。
- **证据**：[20261109-owner-close](outputs/competitor-insights/BCI-004/20261109-owner-close/)（`manifest.json` 入库；`verify.log` 受 `.gitignore` 仅本机）。

## 2026-11-09 · BCI-001 越界修复、BCI-002 查看模板、BCI-003 收敛为决策记录

- **当前任务与阶段**：[BCI-003](tasks/BCI-003/TASK.md) → `TESTED`（纯文档，LIVE 不适用）；BCI-001 / BCI-002 维持 `TESTED`。
- **BCI-003 收敛**：`docs/harness-study.md` 由 250 行学习报告降格为 **44 行 / 约 1472 字**的三块决策记录——已采纳 4 条（每条含落点文件 + 提交 `1bd7eee` + 现在拦得住什么）、已推翻 4 条（原结论 → 修正 + 日期依据）、不立项 5 条（逐条写理由与重议条件）。删除五问、过程分析、逐文件行号摘录；保留三个证据目录链接；写明定位与状态真源，不保留"由谁维护"承诺。校验脚本 `check_decisions.py` **20/20 PASS**。
- **BCI-001 / BCI-002（同日已入库）**：选源页删除越界的「本次分析口径」「报告输出」两块，`acc8e96`，浏览器断言 39→**41/41 PASS**；洞察档案模板新增「查看模板」只读弹窗，`17c2193`，新增断言 **21/21 PASS**。`app.py` 的模板只读路由与 `home.html` 引用仍为共享文件 hunk，按规则不入 `commit_paths`，已在各自 TASK 人工登记。
- **已改文件**：`competitor_insight/docs/harness-study.md`、`tasks/BCI-003/TASK.md`、`tasks/tasks.md`、`BOARD.md`、本文件、`outputs/competitor-insights/BCI-003/20261109-decision-record/`（`check_decisions.py`、`check.log`、`manifest.json`）。全部同批提交并推送。
- **测试**：`check_decisions.py` 20/20；`check_board.py` 与 `workspace_hygiene.py` 结果见 `20261109-decision-record/check.log`。未跑应用测试（本轮未改业务代码）。
- **未解决**：BCI-003-L02 官方 23 个 `SKILL.md` 正文未读（不阻塞任何结论）；BCI-003-L04 交接包缺 5 个项目与 `_template/`。
- **下一步**：用户抽样复核三块决策记录；如无异议 BCI-003 关单。**最后更新：2026-11-09。**

## 2026-11-08 · BCI-004 L10/L11 按用户拍板收口（L10 未关闭，转 DBA）

- **L10（未关闭）**：按用户拍板用 `vectordb` 账号执行 `ALTER SCHEMA bci OWNER TO user_insight_loader`，2026-11-08T23:43:00+08:00 复测仍返回 `42501 must be member of role "user_insight_loader"`。根因：`vectordb` 与 `user_insight_loader` 均非 superuser、均无 CREATEROLE，`pg_auth_members` 中两角色无成员关系，故 `vectordb` 无法自我授权（`ALTER TABLE`/`REASSIGN OWNED` 同样受此限制）。
- **复测后实测**：`owner_before=vectordb`、`owner_after=vectordb`（未变更）；schema ACL `vectordb=UC`、`user_insight_loader=UC`；4 张表属主均为 `user_insight_loader`；loader 建表/插入/查询/删除/删表冒烟 **PASS**；`bci.archive` 10 行、`bci.archive_field` 430 行读取正常。**转属主未执行，应用功能不受影响**。
- **解除条件**：DBA/superuser 执行一条 `ALTER SCHEMA bci OWNER TO user_insight_loader;`，或先 `GRANT user_insight_loader TO vectordb;` 后复跑 `ops/bci_schema_owner.py`；两条路径应用均无需改代码。
- **L11（已决策）**：用户 2026-11-08 决定**不轮换 `vectordb` 口令**，接受公开仓库 `1bd7eee` 暴露风险；从待决清单移除，不再每轮追问。
- **证据**：[20261108-owner-alter](outputs/competitor-insights/BCI-004/20261108-owner-alter/)（`manifest.json` 入库；`apply.log` 受 `.gitignore` 仅本机）；首次尝试见 `20261107-owner-alter/apply.log`。
- **状态不变**：BCI-004 仍 `TESTED`；仍为 10 人试点，全量 63 人未跑。

## 2026-11-08 · BCI-007 报告输出 tab：方案与业务清单完成（CREATED，未写业务代码）

- **当前任务与阶段**：[BCI-007](tasks/BCI-007/TASK.md) → `CREATED`。方案轮已交付，等用户确认 `docs/report-output-design.md` §11 的 Q1–Q10 后进入 `EXECUTING`。
- **交付物**：`docs/report-output-design.md`（逐页数据契约、PPT 模板落地、导出优先级、改稿、版本、hunk 归属、实施顺序）；`docs/report-output-business-inputs.md`（业务开会用，P0/P1/P2 三档 + 10 条数据缺口 + 10 条业务口径问题）。
- **核心结论**：原型 11 页 → **8 页（7 正文 + 1 数据边界附录）**，删 P02/P03（前车来源，无中汽数据）、P06（首选率，无排序题）、P09（本品吸引力，本品 0 样本）；P05 改名为「竞品选择原因与核心对比」（`Q3_23` 是"选择当前车型的原因"，不是"战胜竞品"）；P04 改口径为 16 维多选勾选率。**本品（埃安RT）侧本期整体不出。**
- **导出顺序**：HTML 先行（可页面内验收、无模板依赖）；PPT 二期，先标准模板后业务模板。
- **PPT 可行性（本机实测 python-pptx 1.0.2）**：`.pptx` 可读可写；`.potx` 直读失败、改写 `[Content_Types].xml` 后可读；表格/原生图表（柱/条/饼/环/线/散点/雷达/面积）/图片占位符均可写；**本机无 soffice/PowerPoint，无法把 PPT 渲染成图**；模板自定义表格样式与图表配色不能完全继承。
- **改稿**：本轮明确不做，页面不出现输入框；结构化改稿（限定 lead/bullets、数字白名单、可回滚）写入遗留 L07，并给出解除条件。
- **版本**：新增 `bci.report` + `bci.report_version`，用 `data_fingerprint`（大纲/分析配置/逐车型样本/逐档案 revision/模板/渲染器版本）判定 stale；**只标记、不自动重算、不删除旧版**。
- **共用文件**：`app.py`、`home.html`、`web/bci.js` 三处按 hunk 归属本任务，**不写进 `commit_paths`**；`tasks.md`/`BOARD.md`/`HANDOFF.md` 为共享状态文件，不整目录声明。
- **证据**：`outputs/competitor-insights/BCI-007/20261108-pptx-probe/`（probe.log + manifest.json）；只读探针脚本在 `temp/20261108-bci007-probe/`。
- **本轮改动文件**：新增两份 docs、`tasks/BCI-007/TASK.md`、证据目录与 `temp` 探针；修改 `tasks/tasks.md`、`BOARD.md`、本文件。**未改任何业务代码，未执行 `git add`/`commit`/`push`。**
- **测试**：仅运行 PPT/Excel 能力探针；未运行应用测试（无业务代码）。`workspace_hygiene.py` PASS（24 根文件 / 38 根目录均有用途说明）。
- **看板检查**：`check_board.py` = `failed`，唯一原因是 `TASK-COMMITTED`：BCI-004 与 BCI-006 在 `commit_paths` 里声明了 `BOARD.md`/`HANDOFF.md`/`tasks.md`，而本轮按规则同步了这三个共享文件，导致两条已 `TESTED` 任务出现"未入库"。**不是 BCI-007 的问题，也未擅自修改他人 `commit_paths`**（属 BCI-005-L06 的已知结构问题）。
- **下一步**：用户拍板 Q1–Q10（尤其：是否只做竞品侧、11→8 页、HTML 先行、改稿不做），然后从 S1（大纲与契约固化）开工。

## 2026-11-07 · BCI-006 即时分析 tab 完成（S3–S7，TESTED）

- **当前任务与阶段**：[BCI-006](tasks/BCI-006/TASK.md) → `TESTED`，等用户 7860 业务验收；五车范围与「放弃核心对比车型的原因」口径已由用户确认。
- **实现**：`config/analysis_models.json`（五车 + 跨源别名，换组只改配置）；`server/analysis_service.py`（四磁贴 + 确定性结论 + 空态原因 + 样本基数）；`app.py` 仅新增 `/api/bci/analysis/*` 两路由与惰性单例；`home.html` 启用 tab ③；`web/bci-analysis.js|css` 自包含渲染；`web/bci.js` 仅加 tab ③ 初始化。
- **口径**：Q1 只作人群分类；Q29 ↔ `Q3_23__1..16`；Q27/Q28 ↔ `Q3_24_1__1..16`；两边同名同序 16 维，实测无对不上的维度。页面主标签为「选择当前车辆的原因」「放弃核心对比车型的原因」，并注明本库无未购车样本。
- **更正**：`Q5_5` 推荐意愿并非 0 作答，实为文本分值（如「9十分推荐」），已实现均值/分档；`Q3_13/Q3_23` 的 `601/1380`、`521/1380` 是单选项人数，16 键并集作答为 1380/1380。
- **验收**：`unittest` 18/18；真实库 API E2E `ALL PASS`；Playwright 浏览器 E2E `ALL PASS`（四磁贴、五车下拉、n=41/30、空态原因、无比例为引语、逐人人数）。截图与五车数字见 `outputs/competitor-insights/BCI-006/20261107-analysis/`。
- **数据缺失未做**：关注第一排序（无排序题）、对手为什么赢（无对手视角题/无未购车样本）、进攻点/被进攻点（需跨车推导）、生活状态分型占比与定性强度比例（深访 3–4 人，只出原话）。详见 TASK.md §8。
- **检查**：`check_board.py` 仍 failed，唯一原因是 BCI-004 的 `commit_paths` 覆盖 `BOARD.md`/`HANDOFF.md`/`server/` 整目录；**按用户指示未修改他人声明**。
- **服务**：7860 由后台 `python -u app.py` 提供，`/api/bci/analysis/models` 与 `analyze` 实测 200；若进程被回收，按 `start_agent.cmd` 常规启动。
- **Git**：提交 `5e8f964`（27 文件：服务、配置、前端、测试、文档与证据）。`app.py` 只把 4 处 BCI 片段写入索引，深度调研等他处在途改动仍留在工作区；未夹带 `customer_insight/`、`forecast-engine/`。

## 2026-11-07 · BCI-004 D7d：互斥回退 + 信息渠道呈现层归并

- **互斥回退（用户认可 R046=增购）**：`value_normalizer.resolve_enum_with_fallback` 在标签多值互斥时查 `interview.purchase_type`，与候选唯一一致才取值、`review_status=ok`，并在 `source_ref.correction` 记 `from_raw_tag_value/metadata/rule/basis`；元数据缺失或与候选都不一致时保持 `suspect`，不猜。实测 R046 重跑为「增购 / ok」，不会再打回 suspect。
- **信息渠道归并（仅呈现/统计层）**：`server/channel_normalizer.py` + `templates/info_channel_aliases.json`。表覆盖全库 64 种写法（原报告 66 系同一条标签内重复计数，已更正），逐条含原写法、目标渠道、次数、依据（标准值/同义简称/子频道/模板未单列→其他/无法归并→未归类）。未知写法落「未归类」不丢弃；原始写法完整保留在 `archive_field.source_ref.raw_values/raw_parts`，未改 `value_json` 以外任何数据。
- **测试**：全量 `unittest` 104/104；只读联调 R003/R046 渠道归并与原始写法保留、R063/R046 枚举取值符合预期。
- **当前状态**：仍为 10 人试点，**全量 63 人未跑**；代码已就绪，等用户放开。
- **待用户决定**：① 全量 63 人是否放开；② 渠道归并口径（「其他 vs 未归类」划线）是否认可。

## 2026-11-07 · BCI-004 D7c：枚举值归一集中层完成（L12 解除）

- **结论**：用户拍板「实际增购」算「增购」。全库「首增换购属性」63 条实测：`换购。`31 / `增购。`20 / `首购。`10 直通（仅句号，去标点即标准）；`实际增购。`1 → `增购`（归一，`source_ref` 记原值与规则）；`换购；增购。`1 → 不取值、`review_status=suspect` + `no_data_reason`（R046 已按原话人工修正，档案值保留 `增购`）。
- **规则位置**：新增 `competitor_insight/server/value_normalizer.py`，单一入口 `resolve_enum` / `resolve_enum_or_raise`；`archive_generator._tag_field` 的 enum 分支改为调用，不再在生成器内散落判断；`unknown` 仍按 `invalid_enum` 整人失败。
- **同类标签**：模板仅 `purchase_attribute` 是 tag 驱动单选枚举；`kol_influence` 无来源；`info_channels`（汽车触媒偏好/APP偏好）是多值列表；其余 82 个带 `allowed_values` 的标签为自由文本，参考词表不参与单选归一。**发现**：`info_channels` 多值实际出现 64 种写法（去重后口径）、多数不在模板 options 内（如「哔哩哔哩」「视频号」「微信」），已在 D7d 做呈现层归并。
- **测试**：新增 `tests/test_value_normalizer.py` 9 项；全量 `unittest` 90/90 通过。只读联调：R063 生成 `增购` + 归一记录、R046 生成 `suspect` + 原因。
- **证据**：[enum_mapping.md](outputs/competitor-insights/BCI-004/20261107-enum-normalize/enum_mapping.md)（映射表）、`enum_mapping.json`、`generator_dryrun.json`。
- **注意**：`user_insight.tag` 源数据只读未改；D7d 起互斥值由 `purchase_type` 回退裁决，重跑不再回到 `suspect`。

## 2026-11-07 · BCI-006 即时分析 tab：可行性测评完成，车型范围待用户确认

- **当前任务与阶段**：[BCI-006](tasks/BCI-006/TASK.md)，`CREATED`；S1（数据探查）与 S2（可行性测评）完成，S3 起未开始。
- **结论文档**：[docs/analysis-tab-feasibility.md](docs/analysis-tab-feasibility.md)。核心结论：原型五车三项数据为零（埃安RT/深蓝L06/银河TT/MG07 定量均为 0，小鹏M03 深访为 0），改用五款 10–15 万 SUV（零跑B10 41/4/392/6、铂智3X 39/3/66/10、奇瑞iCAR V23 30/3/78/14、海狮05 EV 31/3/39/4、钛3 30/3/730/3，口径为定量/深访/口碑提及/配置款型）。
- **不可做项**：关注「第一排序」结构无排序题；`Q5_5` 推荐意愿 0 条作答；竞品侧胜出逻辑无直接观测题。均已写入 §8 与遗留 L01–L03。
- **已改文件**：新增 `competitor_insight/tasks/BCI-006/TASK.md`、`competitor_insight/docs/analysis-tab-feasibility.md`、`outputs/competitor-insights/BCI-006/20261107-feasibility/`；修改 `tasks/tasks.md`、`BOARD.md`、本文件。**未执行 `git add`/`commit`/`push`。**
- **测试**：只读探查 11 个脚本（`temp/20261107-bci006/`）；未运行应用测试（无业务代码）。
- **未解决问题**：BCI-006-L01（排序题缺失）、L02（Q5_5）、L03（竞品胜出逻辑）、L04（车型名称多源不一致）、L05（级别字段缺失）。
- **下一步**：用户确认五款车型范围与「战败」口径后，进入 `EXECUTING`，按 S3 实现 `analysis_service`。负责人：用户确认 → TRAE 实现。
- **最后更新**：2026-11-07。

## 2026-11-07 · BCI-004 D7b：R046 购车属性互斥值已核实修正

- **结论**：R046（腾势N9，深圳）按模板题 1「已婚以小家庭（不含父母）为单位」应为**增购**。链路为 `fill_mode=tag` ← 标签「首增换购属性」`TAG-377357cc173d61c8ce47`（原值「换购；增购。」）；原话 `TEI-91315ed80cf5faca5d12`（3055.8–3089.4）说明旧车本田雅阁购入当时仍由妻子使用、没有卖掉，家庭口径是添置；`interview.purchase_type=增购` 交叉一致。个人视角的「换购」不适用于该口径。
- **改动**：`bci.archive_field(R046, purchase_attribute)` → `value_text=增购`、`fill_mode=tag`、`review_status=ok`；原值（含标签原值）、原原因、判断依据、证据 ID 与时间段写入 `source_ref.correction`，可回溯。该档案覆盖率 68.42→71.05（27/38），状态仍 `partial`。
- **影响面**：全库仅 1 条多值互斥（R046）；`R046` 与 `RE010` 不是同一人，库中无 `RE010`（早前报告笔误，实为 `R010`）。另发现 `R063 = 实际增购。` 非标准枚举，若生成会触发 `invalid_enum` 导致整人失败 → 记 [BCI-004-L12](tasks/BCI-004/TASK.md)。
- **脚本**：`ops/fix_bci_r046_purchase_attribute.py`（幂等，可重跑）；证据 `outputs/competitor-insights/BCI-004/20261107-r046-verify/`。

## 2026-11-07 · BCI-004 入库提交（`7dc91aa` 已推送）

- **当前任务与阶段**：[BCI-004](tasks/BCI-004/TASK.md) 保持 `TESTED`，等用户验收 7860 页面与 10 人试点数据。
- **提交内容**：59 个文件——`competitor_insight/server/`（10 个模块）、`tests/`（4 套 41 项）、`web/bci-profile.js|css`、`templates/user_insight_archive.source-map.json`、`ops/`（3 个 DDL/执行脚本）、BCI 文档、`outputs/competitor-insights/BCI-004/` 证据。
- **共用文件**：`app.py` 仅 4 处 BCI hunk（141 行，用 HEAD + BCI 块构造索引，深度调研等他处改动留在工作区）；`home.html`、`web/bci.js` 只含 tab ② 接线。
- **未纳入**：`.gitignore`、`AGENTS.md`、`competitor_insight/tasks/BCI-002/TASK.md`、`customer_insight/*`、`forecast-engine/*`、`skills/*` 等白名单外改动。
- **日志去向**：`*.log` 被 `.gitignore` 第 20 条排除（`apply.log`/`pilot.log`/`check.log` 只在本机 `outputs/competitor-insights/BCI-004/`）；是否调整 `.gitignore` 由用户决定。
- **顺带修正**：`20261106-coverage/coverage.py` 硬编码口令改为读 `.env.new-car`；历史提交 `1bd7eee` 中仍有旧值，已记入 TASK §8 L11。
- **检查**：`unittest` 81/81；`check_board.py` 内容一致性通过，`TASK-COMMITTED` 仅剩他任务的 `competitor_insight/tasks/BCI-002/TASK.md` 未提交。
- **7860 已重启**：先跑 `scripts/start_agent.ps1 -NoOpen`（未打开浏览器；核验时无月报专用 Chrome 进程），但其子进程随会话结束被回收，遂改用 `Win32_Process.Create` 分离启动 `python -u app.py`（工作目录 `myproject`，日志 `logs/app-20261107-bci.out.log`）。实测 `/api/bci/archive/template` 43 维/12 组、`respondents` 63 人其中 10 人有档案、`detail?interview_id=R003` 43 维、首页已引入 `bci-profile.js|css`。若明早 7860 无响应，按 `start_agent.cmd` 常规启动即可。

## 2026-11-07 · BCI-004 D7/D8 完成，状态 TESTED

- **当前任务与阶段**：[BCI-004](tasks/BCI-004/TASK.md) 已推进到 `TESTED`；D1–D8 全部完成，待用户验收上线。
- **D7 真实入库**：新增 `competitor_insight/server/llm_client.py`（固定 `api.deepseek.com`，优先读 `.env` 的 DeepSeek 凭证，避免误用进程里另一把阿里云 key）。10 人（R003/R050/R057/R030/R025/R037/R046/R005/R010/R062）生成 10/10 成功，每人 43 维；19 个 success 维 183/190 命中（12 维满员、7 维 9/10，缺口均写 `no_data_reason`）；8 个无来源维全部「本期无来源」；LLM 值证据 ID 全部有效；R046 购车属性因「换购；增购」互斥标 `suspect`。覆盖率 65.79%–76.32%。
- **D8 浏览器验收**：真实服务跑在 `127.0.0.1:7861`（未重启 7860、未触碰月报浏览器），Playwright 18/18 PASS：63 人列表、R003 43 维、8 个无来源维、R010 9 分、R003 评分缺失、找原话 50 条、勾选 2 人下载 xlsx（45 行/3 Sheet/证据页含两人）、模板切换重载、0 JS 错误。
- **回归**：`unittest` 81/81；`check_board.py` 仅剩跨任务约束（BCI-002 的 TASK.md 未提交）与本次 next 文本已同步；`workspace_hygiene.py` 仅报既存 `debug.log`。
- **遗留**：`bci` schema 属主仍是 `vectordb`（需 DBA 才能转给 loader）；`debug.log` 属他处产物未处理。
- **入库**：见上一条（`7dc91aa`）。

## 2026-11-07 · BCI-004 D6 完成（共用文件接线，临时端口探针 19/19）

- **当前任务与阶段**：[BCI-004](tasks/BCI-004/TASK.md) 保持 `EXECUTING`；D1–D6 完成，下一步 D7（10 人试点生成写库）。
- **路由**：`app.py` 新增 `/api/bci/archive/template|respondents|detail|run|quote`（GET）与 `/generate|export`（POST，导出二进制）。`ArchiveService` 惰性单例，数据库首次请求才连接；`ApiError` 保留状态码（400/404/409），`DatabaseUnavailable` → 503；生成走服务自身线程，不占 `AGENT_RUN_LOCK`。
- **前端**：`home.html` 启用 tab ②、新增 `[data-bci-profile]` 容器、引入 `bci-profile.css/js`；`bci.js` 切到 tab ② 时才 `BciProfile.init`；`bci-profile.js` 面板未展开不预加载，避免首页立即查库。
- **验收**：临时端口（非 7860、未动浏览器会话）探针 19/19 PASS：模板 43 维/12 组、真实库 63 人、R001 详情空态、找原话命中、缺档案导出 409、非法 mode 400、未知接口 404、静态资源与首页接线。`unittest` 81/81。证据：`outputs/competitor-insights/BCI-004/20261107-d6-wiring/probe.log`。
- **下一步**：D7 按 §6.3 名单生成 10 人档案并写 `bci.*`；写库前确认 loader 仍具 USAGE/CREATE，失败不留半份。**未执行 `git add` / `commit` / `push`。**

## 2026-11-07 · BCI-004 D5 完成（洞察档案前端模块，离线浏览器验收 17/17）

- **当前任务与阶段**：[BCI-004](tasks/BCI-004/TASK.md) 保持 `EXECUTING`；D1–D5 完成，下一步 D6（共用文件接线）。
- **代码**：`web/bci-profile.js`（`window.BciProfile.init/destroy`，支持 `[data-bci-profile]` 自动初始化；模板驱动 43 行、模块列按连续同组 `rowspan`、无来源 / 评分缺失行、证据浮层、找原话、搜索、生成轮询、xlsx/md 下载）、`web/bci-profile.css`（本地 token + 两栏布局 + 响应式）。
- **契约要点**：scope 统一按完整对象 `{version,datasources}` 解析（`localStorage['bci.scope']` → `window.BCI_SCOPE` → `bci:scope-applied`）；档案值 / 原话只用 `textContent`，高亮走文本节点 + `<mark>`；导出走二进制响应，与 D4 `POST /export` 对齐。
- **验收**：Playwright 加载 `file://` 夹具（不启 7860、不连库），17 项断言全 PASS；截图 `profile.png`（43 行档案表）与 `profile-run.png`（生成完成态）。证据：`outputs/competitor-insights/BCI-004/20261107-d5-frontend/`。
- **环境**：Playwright 浏览器已安装到 `%USERPROFILE%\.cache\ms-playwright`（默认 `AppData\Local\ms-playwright` 不存在）；`check_frontend.py` 启动前设置 `PLAYWRIGHT_BROWSERS_PATH`。
- **下一步**：D6 接线 `app.py` 路由（`/api/bci/archive/*` GET/POST、白名单、二进制响应）、`home.html` tab 启用与静态引入、`web/bci.js` 最小联动；动共用文件前先核对工作区。**未执行 `git add` / `commit` / `push`。**

## 2026-11-07 · BCI-004 D4 完成（接口 / 原话 / 导出服务，真实库只读验证）

- **当前任务与阶段**：[BCI-004](tasks/BCI-004/TASK.md) 保持 `EXECUTING`；D1–D4 完成，下一步 D5（前端新模块）。
- **代码**：`server/archive_api.py`（模板 / 受访者 / 详情 / 生成 / 轮询 / 原话 / 导出，可直接调用，未挂路由）、`server/quote_service.py`（答案 / 证据 / 标签证据 / 档案值检索；`tag_evidence` 经 `JOIN tag` 归属过滤；按 ID 刷新原话，失效标 `source_missing`）、`server/export_service.py`（openpyxl 真 xlsx 三 Sheet + 单人 md，全内存 bytes）。
- **导出口径**：无来源维保留整行写「本期无来源：原因」；满意度缺失写原因并带 `score_source=missing`；`md` 多人返回 `md_single_only`，缺档案返回 `archive_missing` 并列出编号。
- **测试**：`tests/test_archive_service.py` 25 项（模板、受访者、详情三态、生成跳过/失败/运行锁/轮询、xlsx 结构、md 单人、缺档案、关键词校验、真实库找原话）；全量 `unittest` 81/81 通过。
- **真实库（只读，不写库）**：模板 43 维 / 12 组；63 人；R001 详情空态；`空间` 找原话命中 5 条。证据：`outputs/competitor-insights/BCI-004/20261107-d4-api/probe.log`。
- **下一步**：D5 `web/bci-profile.js` / `web/bci-profile.css`（自包含，不 import `bci.js`，不碰共用文件）。**未执行 `git add` / `commit` / `push`。**

## 2026-11-07 · BCI-004 D3 完成（生成器 + 证据硬门，真实库单人已验证）

- **当前任务与阶段**：[BCI-004](tasks/BCI-004/TASK.md) 保持 `EXECUTING`；D1–D3 完成，下一步 D4。
- **代码**：`server/evidence_gate.py`（只索引本受访者、去重、最多 5 条、quote 截 300 字、枚举校验；新增公开 `ids_for_question()`）；`server/archive_generator.py`（`PostgresInterviewSource` 只读 interview/answer/tag/evidence/tag_evidence；tag/metadata/derived 直取不调模型；llm 维只接受证据 ID）。
- **实现约定（D4/D5 需遵守）**：个人层面无值也落 `fill_mode=none` + `no_data_reason`；用 `source_ref.no_source_scope` 区分 `template`（8 个「本期无来源」维）与 `interview`（该受访者未提及）；`coverage_required` 只统计真实值，`satisfaction_score` 成功时 `fill_mode=derived`。
- **测试**：`tests/test_archive_generator.py` 24 项（43 行、8 个无来源、伪造 ID / 跨人证据 / 非法枚举 / 超 5 条 / 非 JSON 全部拒绝、满意度三态、quote 截断）；全量 `unittest` 56/56 通过。
- **真实库（只读，不落库）**：R003/R001/R002 各生成 43 维，coverage 68.42/78.95/76.32；R001 满意度 `7-8分`→7.5 并保留区间，R002/R003 落描述性原因。证据：`outputs/competitor-insights/BCI-004/20261107-d3-generator/generate-probe.log`。
- **检查**：`workspace_hygiene.py` PASS。**未执行 `git add` / `commit` / `push`。**

## 2026-11-07 · BCI-004 D2 完成（bci schema + 存储层，真实库已验证）

- **当前任务与阶段**：[BCI-004](tasks/BCI-004/TASK.md) 保持 `EXECUTING`；D1、D2 完成，下一步 D3。
- **schema 与表**：`bci` schema 已建；`archive_run`、`archive_run_item`、`archive`、`archive_field` 四表、主键/唯一/外键/CHECK 与 3 个索引、`archive_archive_id_seq` 全部在真实库核对通过。
- **权限实测**：`vectordb` 有 database CREATE；但**不是** `user_insight_loader` 成员、也非 superuser，`CREATE SCHEMA ... AUTHORIZATION user_insight_loader` 报 `must be member of role`。已改为 `CREATE SCHEMA bci` + `GRANT USAGE, CREATE ON SCHEMA bci TO user_insight_loader`；表由 loader 创建并持有。loader 实测 `has_database_create=False`、`has_schema_usage/create(bci)=True`。记录为 BCI-004-L10（若必须 loader 持有 schema 属主，需 DBA 执行 `ALTER SCHEMA ... OWNER TO`）。
- **冒烟**：loader 完成 insert/select/delete，级联清理后 4 表残留均为 0。
- **代码**：`server/db.py`（loader 连接 + 事务）、`server/archive_store.py`（`PostgresArchiveStore` + `FileArchiveStore`，revision 递增、旧档案 stale、单事务、三态 `QueryResult`）、`tests/test_archive_store.py`（9 项，含真实库）。
- **脚本**：`ops/bci_archive_ddl_owner.sql`、`ops/bci_archive_ddl.sql`、`ops/apply_bci_archive_ddl.py`（可重复执行，含权限/结构/冒烟校验）。
- **测试**：`unittest` 32/32 通过（D1 23 + D2 9，含 2 项真实库用例）。
- **下一步**：D3 生成器与证据硬门（`archive_generator.py`、`evidence_gate.py`）。**未执行 `git add` / `commit` / `push`。**

## 2026-11-07 · BCI-004 D1 完成（source-map 契约层）

- **当前任务与阶段**：[BCI-004](tasks/BCI-004/TASK.md) 保持 `EXECUTING`；D1 完成，下一步 D2。用户已确认首次入库完成（`1bd7eee` 已推送），D6 共用文件闸门解除。
- **本次改动（只新增，未碰共用文件）**：
  - `templates/user_insight_archive.source-map.json`：43 维逐维映射；fill_mode = tag 22 / metadata 2 / derived 1 / llm 10 / none 8。
  - `server/source_map.py`：结构校验（缺维/重复维/顺序/分组/非法题号/`none` 必须带原因且不得声明来源）。
  - `server/template_registry.py`：只读 `web/templates.json`，加载定义 + `<template_id>.source-map.json` 并交叉校验。
  - `tests/test_source_map.py`：23 项，全部通过。
  - `docs/archive-tab-design.md`：§2.1 `fill_mode` 增加 `derived`；§3.1/§3.2 改为实际契约。
- **库侧校验**：61 个 distinct 题号、56 个 distinct 标签全部命中真实库（`user_insight.question` 85 行、`user_insight.tag` 85 个标签）。证据：`outputs/competitor-insights/BCI-004/20261107-d1-sourcemap/validate.log`。
- **8 个无来源维**：`kol_influence`、`first_choice_ranking`、`rt_awareness_channel`、`rt_attraction_ranking`、`rt_concerns`、`rt_expectations`、`reception_expectation`、`loyal_repurchase_reason`，每维均带具体 `no_source_reason`，且未声明任何题号/标签。
- **新阻塞**：实测 `user_insight_loader` 无 database CREATE 权限（`has_database_create=False`），`CREATE SCHEMA bci` 会失败；D2 的 DDL 需有权限账号执行。证据：`20261107-d1-sourcemap/db-privilege.log`。
- **已运行检查**：`unittest` 23/23 OK；`check_board.py` 仍 failed，但仅剩 BCI-001/002 的 TASK.md 入库后又被改动（非本任务）；`workspace_hygiene.py` 见下条执行结果。
- **下一步**：D2 先写 `ops/` DDL 与存储层（文件后端契约测试），数据库路径待权限到位再验收。**未执行 `git add` / `commit` / `push`。**


## 2026-11-06 · BCI-005 追加 TASK-COMMITTED（任务必须入库）

- **当前任务与阶段**：[BCI-005](tasks/BCI-005/TASK.md) 仍为 `DEV_DONE`（`blocked: no`），本轮只追加"入库"约束，未改任何任务阶段；BCI-001/002 仍 `TESTED`，BCI-003/004 仍 `DEV_DONE`。
- **本次改动**：只改任务机制，**未碰业务代码**，未重启 7860。`config/bci_protocol.json` 增第 5 条 `TASK-COMMITTED`；`config/verify/verify_constraints.py` 增 `check_task_committed()`；`RULES.md` §6 增"入库是阶段准入硬条件"、§5 增 `commit_paths` 字段、§12 增"看板可能因未入库如实变红"；`tasks/_TEMPLATE/TASK.md` 增 `commit_paths`；BCI-001~005 的 TASK.md 各补 `commit_paths`；`BOARD.md` 增「入库状态」栏；`tasks/tasks.md`、本文件同步。
- **判定方式**：对 `TESTED`/`LIVE` 任务，取其 `commit_paths` 在仓库根执行 `git status --porcelain -- <paths>`；有任何输出（含未跟踪）即 FAIL。`LIVE` 追加 `git rev-list --count @{u}..HEAD`，无上游一律 FAIL。`commit_paths` 留空/`none` 直接 FAIL，不能靠不写绕过。
- **已运行测试与结果**：临时 git 仓库 6/6 反向用例符合预期（干净 PASS、已跟踪未提交 FAIL、未跟踪 FAIL、提交后 PASS、LIVE 无上游 FAIL、未声明 FAIL）；原有 9 个反向用例仍 9/9；`check_board.py` 当前如实 `status: failed`（应查 177 / 命中 1），失败原因就是 BCI-001 7 处、BCI-002 6 处未入库；`workspace_hygiene.py` PASS。
- **未解决问题**：L05 存量任务全部未入库、看板为红（用户将在 BCI-004 完成后统一入库）；L06 `commit_paths` 靠人工声明，写窄会漏判；L01~L04 见 TASK.md §6。
- **下一步与负责人**：用户复核并通过后，先完成统一入库，再让 BCI-005 转 `TESTED`；BCI-001/002 在入库前不得转 `LIVE`。
- **Git**：全部未提交；`competitor_insight/` 整体未跟踪；未执行 `git add` / `commit` / `push`。

## 2026-11-06 · BCI-004 进入开发（Q11/Q12 已拍板）

- **阶段**：BCI-004 → `EXECUTING`；本轮只改 `docs/` 与 `tasks/`，**未写业务代码、未建表**。
- **Q11**：8 个无来源维不补题、不补访；页面照常显示，标「本期无来源」+ 具体原因，不用模型兜。下周与业务对接。
- **Q12**：满意度评分只对有明确分数的 13 人生成，其余留空并显示「访谈中未给出明确评分 / 仅有描述性评价」，醒目色标注，不用中性灰。
- **文档**：`docs/archive-tab-design.md` 增 §5.7（呈现规则）、§7.1（实施顺序与共用文件闸门），并更新 §0 D9/D10、§6.4、§8.1 Q4/Q11/Q12；`tasks/BCI-004/TASK.md` §10 新增 D0–D8 步骤、依赖与验收。
- **共用文件闸门**：D6 之前禁止改 `app.py`、`home.html`、`home.css`、`home.js`、`web/bci.js`、`web/templates.json`；D1–D5 只新增文件，不启动 7860。需用户确认「入库完成」后接线。
- **下一步**：TRAE 执行 D1（source-map 契约层），完成即回报。

## 2026-11-06 · BCI-004 43 维覆盖率只读实测（续）

- **当前任务与阶段**：[BCI-004](tasks/BCI-004/TASK.md) → `DEV_DONE`（`blocked: no`）；本轮只做可行性核实与方案修订，**未写业务代码、未建表**。
- **本次改动**：新增 `competitor_insight/docs/coverage.csv`（43 维逐维：应查 63 / 实查 63 / 命中 / 三态 / 直接命中 / LLM 原料 / note）；更新 `docs/archive-tab-design.md`（header 记录 Q1/Q2/Q9 决议；§6.1 改实测；§6.2 预判表整体替换为实测表；新增 §6.3 四问直答与 10 人试点名单；§6.4 补数原则；§8.1 增加 Q11/Q12；§0 增加 D8/D9）；新增 `outputs/competitor-insights/BCI-004/20261106-coverage/`（`manifest.json`、`coverage.py`、4 份日志）；同步 `tasks/BCI-004/TASK.md`、`tasks/tasks.md`、`BOARD.md`、本文件。
- **实测结论**：43 维 success 19 / partial 16 / failed 8；必填 38 维 17/14/7。8 个无来源维度 = KOL/KOC、首选率、RT 了解渠道/吸引力排序/顾虑/期望、接待期待、老车主复购。全库仅 3 人提及埃安、0 人是埃安车主；满意度有明确分数者 13/63；性别标签全量未提及。
- **10 人试点**：R003/R050/R057（全库仅 3 个埃安提及者）+ R030/R025/R037/R046/R005/R010/R062，覆盖 4 城市 3 种购车属性。
- **已运行检查**：数据库全部为只读 `SELECT`；`check_board.py`、`scripts/workspace_hygiene.py` 结果见下条。
- **未解决问题**：L01（Q3/Q5–Q8/Q10–Q12 待确认）、L03（DDL 未执行）、L05/L07/L08（无来源、性别缺失、评分稀疏）、L06（未提交）。明细见 TASK.md §8。
- **下一步与负责人**：用户复核 `coverage.csv` 与方案 §6；确认后 TRAE 落 `source-map.json`，再按 §7 进入开发。**未执行 `git add` / `commit` / `push`。**

## 2026-11-06 · BCI-005 任务机制 Harness 化（契约 / 三态 / 冻结）

- **当前任务与阶段**：[BCI-005](tasks/BCI-005/TASK.md) → `DEV_DONE`（`blocked: no`），等用户复核机制输出；BCI-001/002 仍 `TESTED`，BCI-003/004 仍 `DEV_DONE`，本轮未改它们的状态。
- **本次改动**：只改任务机制，**未碰业务代码**（`app.py`、`home.html`、`web/bci.js`、`bci.css`、`templates.json`、`templates/*` 均未改），未重启 7860。新增 `competitor_insight/config/bci_protocol.json`（4 条约束，含 id/statement/reader/verify）与 `config/verify/verify_constraints.py`（只读真断言脚本）；改 `check_board.py`（协议 reader/verify 校验、敷衍 verify 拦截、`Tally` 三态计数、`frozen_paths` 越界、`port` 冲突、`--freeze`）；改 `tasks/_TEMPLATE/TASK.md`（增加 `port`/`frozen_paths`）、`RULES.md` §5/§12、`tasks/tasks.md`、`BOARD.md`、本文件；新增 `tasks/BCI-005/` 与 `tasks/BCI-005/frozen.sha256`。
- **兼容策略**：`port`/`frozen_paths` 为可选字段，存量 BCI-001~004 未声明时按「未声明 = 不限制」处理；运行后仍全部 PASS（应查 171 / 命中 0）。
- **已运行测试与结果**：4 条协议约束单跑 success；`check_board.py` success（命中 0）；9 个反向验证用例全部符合预期（4 条 verify 破坏→FAIL→恢复→PASS、reader 符号缺失→FAIL、敷衍 verify→FAIL、冻结文件越界→FAIL 且按字节还原后 PASS、port 非整数→FAIL、port 冲突→FAIL）；`workspace_hygiene.py` PASS。证据：`outputs/competitor-insights/BCI-005/20261106-harness-adoption/`（`verify.log`、`reverse-verify.log`、`git-status.txt`、`manifest.json`）。
- **未解决问题**：BCI-005-L01 业务接口三态未落地；L02 reader 仅词法存在性检查；L03 冻结基线未纳入 Git；L04 未提交。
- **下一步与负责人**：用户复核 `check_board.py` 的三态输出与 `reverse-verify.log`，确认后 TRAE 转 `TESTED`。
- **Git**：全部未提交；`competitor_insight/` 整体未跟踪，工作区还有其他任务改动，不得整体暂存。

## 2026-11-06 · BCI-004 用户洞察档案 tab 技术方案（首轮，已被上条取代）

- **当前任务与阶段**：[BCI-004](tasks/BCI-004/TASK.md) → `DEV_DONE`（`blocked: no`），只交付方案，等用户拍板；[BCI-001](tasks/BCI-001/TASK.md)、[BCI-002](tasks/BCI-002/TASK.md) 仍为 `TESTED`，[BCI-003](tasks/BCI-003/TASK.md) 仍为 `DEV_DONE`，本轮未改它们的状态。
- **本次改动**：只新增文档与证据，**未改任何业务代码、未改模板/`templates.json`/`bci.js`/`bci.css`/`home.html`/`app.py`、未建表、未启动 7860**。新增 `competitor_insight/docs/archive-tab-design.md`（8 部分：架构、数据模型、模板驱动、接口、前端、数据现状、任务拆分、风险）；新增 `tasks/BCI-004/TASK.md`；新增 `outputs/competitor-insights/BCI-004/20261106-archive-design/`（`db-probe.log`、`manifest.json`）；改 `tasks/tasks.md`、`BOARD.md`、本文件；修正 `tasks/BCI-003/TASK.md` 两处把 Harness 落地建议编为 BCI-004 的文字（编号改为另行确认）。
- **关键决策**：档案存 PG 长表（`bci.archive` + `bci.archive_field`，模板版本 + 模板快照，升级不覆盖）；维度 → 题号/标签/元数据的映射放独立 `source-map.json`；确定性直取优先，LLM 只做综合且只返回候选证据 ID；后台 job + 轮询；导出真 xlsx（openpyxl）+ 单人 md；v1 不做自由指令与多人并排。
- **已运行测试与结果**：`check_board.py` PASS；`scripts/workspace_hygiene.py` PASS。未跑：任何业务测试（本轮无业务代码）；数据库只读探查因 192.168.3.146:5432 超时未成功，已记录在 `db-probe.log`。
- **未解决问题**：BCI-004-L01（10 个开放问题待用户拍板）、L02（数据库不可达，S1 阻塞）、L03（`bci` schema DDL 未获批）、L05（排序类/RT 类维度可能无数据）、L06（未提交 git），明细见 TASK.md §8 与 [BOARD.md](BOARD.md) 挂账表。
- **下一步与负责人**：用户确认方案 §8.1 的 Q1–Q10（至少 Q1/Q2/Q3/Q4/Q9），TRAE 再执行 S1 覆盖率盘点与 source-map。
- **Git**：全部未提交、未暂存；工作区仍混有其他任务改动，不得整体暂存。

## 2026-11-06 · BCI-003 Harness 工程方法学习与适用性评估

- **当前任务与阶段**：[BCI-003](tasks/BCI-003/TASK.md) → `DEV_DONE`（`blocked: no`），等用户阅读确认；[BCI-001](tasks/BCI-001/TASK.md)、[BCI-002](tasks/BCI-002/TASK.md) 仍为 `TESTED`，等 7860 验收。
- **本次改动**：只新增文档与证据，**未改任何业务代码**。新增 `competitor_insight/docs/harness-study.md`（五问结论 + 三源可信度标注 + 未验证清单）；新增 `outputs/competitor-insights/BCI-003/20261106-harness-study/`（官方三份原文快照、同事工程读取清单、`manifest.json`）；改 `tasks/tasks.md`、`BOARD.md`、本文件，新增 `tasks/BCI-003/TASK.md`。
- **已运行测试与结果**：`check_board.py` PASS；`scripts/workspace_hygiene.py` PASS。未跑：同事工程 44 个离线测试（交接副本无虚拟环境，不在他人目录装依赖）。
- **未解决问题**：BCI-003-L01（Q3 五条均未落地，等用户决定是否立项）、L02（同事 Skill 与官方 SKILL.md 正文未核验）、L03（未提交 git）。
- **下一步与负责人**：用户读 `docs/harness-study.md` §2 Q3/Q5，确认是否另立任务落地机器契约（TRAE 执行）。
- **Git**：全部未提交，工作区仍有其他任务改动，不得整体暂存。

## 2026-11-06 · BCI-002 模板 v1 交付 + 模板下拉改为读清单

- **当前任务与阶段**：[BCI-001](tasks/BCI-001/TASK.md) → `TESTED`（`blocked: no`）；[BCI-002](tasks/BCI-002/TASK.md) → `TESTED`（`blocked: no`）。两者均等用户 7860 验收。
- **本次改动**：新增 `competitor_insight/templates/`（`nev_user_insight_template.json` 8 组 43 维、`nev_user_insight_template.md` 人读版、`README.md`）；新增 `competitor_insight/web/templates.json` 下拉清单；改 `bci.js`（模板选项改为运行时 fetch 清单，`enter()` 先加载再 `restore()`，加载失败走不可选降级）；`bci.css` 上一轮已改 2×2 布局，本轮未动。
- **已运行测试与结果**：`validate_template.py` 25/25 PASS（`outputs/competitor-insights/BCI-002/20261106-template-v1/`）；`verify_selector.py` 39/39 PASS（`outputs/.../BCI-001/20261106-datasource-selector-r2/`，含 4 张截图与 manifest）；`check_board.py` PASS；`scripts/workspace_hygiene.py` PASS。已知基线：`GET /api/health` 404。
- **未解决问题**：BCI-001-L02～L08、BCI-002-L02～L03（L01 已关闭）；模板尚无后端校验器消费维度定义。
- **下一步与负责人**：用户在 7860 验收模板下拉可选并确认上线（TRAE 转 `LIVE`）；未获指令不开发 tab ②。
- **Git**：全部未提交，工作区还有其它任务改动，不得整体暂存。

## 2026-11-06 · 工作区改名 + 代码收拢 + 任务总表 + BCI-001 重做完成

- **当前任务与阶段**：[BCI-001](tasks/BCI-001/TASK.md) 竞品洞察 · 数据源筛选 tab → `TESTED`（`blocked: no`）；[BCI-002](tasks/BCI-002/TASK.md) 新能源用户洞察模板 → `CREATED`（`blocked: no`）。
- **结构调整**：目录 `competitor_insights` → `competitor_insight`；前端资源收进 `competitor_insight/web/`（`bci.js`、`bci.css`），由 `app.py` 的 `/competitor-insight/` 路由提供；新增 `tasks/tasks.md` 任务总表；`check_board.py` 改为校验 `tasks.md` ↔ `BOARD.md` ↔ 各 `TASK.md` 三方一致。
- **已改文件与 git 状态**：新增 `competitor_insight/`（含 README、RULES、BOARD、HANDOFF、check_board.py、tasks/、web/，未跟踪）；修改 `app.py`（新增 `/competitor-insight/` 静态路由与 `_send_file` 白名单，删除 `POST /api/bci/datasource/availability` 及白名单项）、`home.html`（左导航 `bci`、视图骨架、资源引用、四类选择器瘦壳）、`assets/home.js`（删除内联 BCI 模块，仅保留挂载桩）、`assets/home.css`（BCI 样式移出）、`docs/root-files.json`（根目录名同步）。**全部未提交**，工作区同时存在其他任务改动，不得整体暂存。
- **已运行测试与结果**：`verify_selector.py` 29/29 PASS，EXIT=0（证据 `outputs/competitor-insights/BCI-001/20261106-datasource-selector-r2/`，含 `verify.log`、2 张截图、`manifest.json`）；`check_board.py` PASS；`scripts/workspace_hygiene.py` PASS。已知基线：`GET /api/health` 404，与本次改动无关。未跑：多用户/并发口径、tab ②③④（未开发）、全项目回归。
- **未解决问题**：BCI-001-L01～L08、BCI-002-L01，明细见各自 TASK.md 与 [BOARD.md](BOARD.md) 的遗留挂账表。
- **下一步与负责人**：用户在 7860 验收「竞品洞察 → 数据源筛选」并确认上线（TRAE 转 `LIVE`）；BCI-002 由 TRAE 按埃安RT 报告章节产出模板。未获指令前不主动开发 tab ②。
- **环境提示**：`app.py` 启动时把 `home.html` 读进内存，前端结构改动必须重启 7860；`competitor_insight/web/*`、`assets/home.js`、`assets/home.css` 按请求读盘。重启前先确认月报专用浏览器状态，遵守根 AGENTS.md 保护规则。

## 机制落地说明（2026-11-06）

- 采用任务制机制，取代此前以临时对话推进的方式。
- 目录与入口：`competitor_insight/README.md`、`RULES.md`、`BOARD.md`、`HANDOFF.md`、`check_board.py`、`tasks/_TEMPLATE/TASK.md`、`tasks/BCI-001/TASK.md`、`tasks/BCI-002/TASK.md`、`tasks/tasks.md`；`docs/root-files.json` 登记根目录 `competitor_insight`。
- 此后竞品洞察的开发、修复、验证、上线一律先落任务再动手；成果物必须落成文件。
