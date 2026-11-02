# HelloAgent 最近交接 · V2.0

更新：2026-11-02（Asia/Shanghai）。本文件由当前值班 AI 维护，适用于整个 myproject；共同规则见 [AGENTS.md](../../AGENTS.md)，任务索引见 [TASKS.md](TASKS.md)。

## 当前任务及进度

- 2026-11-02（TRAE，当前写入方）：用户确认市场板块新增【竞品对标】能力并要求立项；任务编号定为 **MKT-001**（不沿用预测引擎 CHRONOS 前缀，MKT 系列自 001 起，原 MKT-004 草稿已更名）。完成方法论评估（deep-research-assistant 插件，L2 实测证据 `temp/20261102-deep-research-eval/`）、三层架构方案（skill 语义层 + ResearchDAG 泛化执行层 + 三数据底座）与 [需求文档 v0.1](tasks/MKT-001/需求文档.md)。本任务未修改任何业务代码；TASKS.md/HANDOFF.md 仅追加条目。四项开放问题已于 2026-11-02 全部关闭（工信部存储 3.146 vectordb/miit schema、试点 10–20 万新能源 SUV、Phase 2 知识库首批源清单、前端为左侧导航顶级入口【竞品对标】），需求文档升至 v1.0，S1 收口。S2 已完成：用户确认包名 competitor-benchmarking 与新建专用 agent，完整包骨架已落地 `skills/competitor-benchmarking/`（SKILL.md / agents/default.md / references×3 / assets/matrix-schema.json 矩阵契约 / scripts×2 接口占位 / manifest.json；validate_matrix.py 规则 S5、import_miit.py 实现 S4 交付）。下一步 S3：研究引擎复制适配——用户决策复制而非抽取 core，`monthly_research_dag.py` 完全不动，复制机制为 `utils/benchmark_research_dag.py` 独立演进（孪生溯源标注 + 自身单测 + dry-run；已知代价机制双份维护，第三个研究场景出现时再抽 core）。流程门（2026-11-02 起）：关键设计决策提交用户确认前先过子代理对抗性复审。2026-11-02 S3 复制方案对抗性复审已完成：结论可行，但"四个适配点"低估耦合面——五项硬门槛（失败判定正则、domain 前缀白名单、fallback/gap 硬编码工具名、research-receipts 目录改名、禁止 benchmark 引擎 import 月报模块）纳入 S3 验收；红线扩展为"月报链路含共享依赖零改动"。miit 表结构已检查确认：`miit.ods_pz_base_info`（3,459 款型）+ `ods_pz_detail_info`（785,436 行 key-value），miit-schema.sql 草案作废，S4 改按实际结构适配。2026-11-02 用户确认数据口径：miit 表统一以「款型配置信息」描述、不带来源站点字样，skill 包与需求文档已同步；红线按复审建议扩展（月报文件 git 零改动 + benchmark 引擎禁止 import 月报模块 + 共享依赖行为零改动，写入 NFR6），S3 完整适配清单（🔴×5 + 🟡×6）已落入 TASK.md。2026-11-02 S3 复制实现完成：新增 `utils/benchmark_research_dag.py`（机制复制自 monthly_research_dag，孪生溯源标注，独立演进）与 `tests/test_benchmark_research_dag.py`（8 项单测通过）；适配清单 🔴×5 通过、🟡×6 中 #6–#10 通过、#11 双引擎共存冒烟待 S6；dry-run（`temp/20261102-mkt001-s3-dryrun/`）用真实命名 fake 工具验证 fallback 覆盖 miit+reputation、gap 命中 web_search；月报 `monthly_research_dag.py` git 零改动已核查，`custom_tools.py` 仅调用 record_tool_call 未改动。2026-11-02 S4–S8 连续完成：S4 `tools/miit_tools.py`（miit_search_models/miit_get_model_detail 只读工具 + HARD_PARAM_KEYS 映射表 + car_id 对账，真实库冒烟 3459=3459 一致）+ `import_miit.py` 导入对账实现；S5 `utils/benchmark_validation.py` + `validate_matrix.py`（12 项单测 + 端到端）；S6 `agents/benchmark_agent.py` + config 加 competitor_benchmark + app.py 分支（只加载 reputation 插件）+ `pages/benchmark.html` + home.html 导航【竞品对标】；S7 代表性任务验收 PASS（引擎真实取证 + 矩阵验收 + 故意错误发现）；S8 Phase2/3 方案细化（知识库爬虫 + 事件触发自动化，见 TASK）。整体状态：S0–S8 完成、「接入中」（12 项未全过，待 web 运行时接入补验 skill runtime 隔离运行/run_id 恢复/回放下载）。2026-11-02 补验完成：双引擎共存冒烟（适配清单 #11）通过（`tests/test_dual_engine_coexistence.py`）；真实模型执行验收 PASS——build_benchmark_agent 真实构建 + deepseek 实测对标任务（自主识别钛7/深蓝G318/哈弗猛龙/BJ40/豹5/坦克300，miit 取硬参数 + tavily 联网取价，产出 8819 字符矩阵+So What），过程中修复难点 #8 上下文窗口问题（miit_get_model_detail 由整表 276 项改为硬参数优先+限量 30）。全量单测 27 项通过。skill runtime 接入已完成（新增 openai.yaml + artifact-template.json，activate_skill_runtime 加 competitor-benchmarking 约束，run_agent_once 走 skill runtime；隔离运行 + run_id 恢复 + 回放 + 验收状态机验证 PASS），skill-integration-standard 12 项全部满足，MKT-001 标记「已接入」。既有未提交改动（CHRONOS-003、用户洞察等）保持原状未动。

- 模型比较问题已修复：预测与回测分别保存最近模型任务编号，刷新从本地回执恢复；比较时核对当前范围、数据版本、截止及预测期。主服务实际验证广东插混预测、刷新、范围变更拦截和回测比较；测试 `node --test tests/test_forecast_model_comparison.cjs` 3 项、相关后端 17 项、原预测页面 13 项通过。首次使用需要分别重跑两模型；每模型每操作仅记最近任务。代码未提交，Codex 已释放写入。

- 当前接力：CHRONOS-003 进行中，Codex 已释放写入。SARIMAX 独立季节性基线、同起点比较及网页模型选择已实现，模型选择说明已改为业务语言并在主服务浏览器验证；真实价格/油价历史版本未验证，因素模型仅用合成数据测试，未接入网页。公开 EIA 原始快照和价格候选清单路径见 TASK。用户确认未来 12 月最近已核验水平保持不变，缺失不补零。
- 当前代码涉及 `app.py`、`assets/forecast-engine.js`、`pages/forecast-engine.html`、`scripts/preview_forecast_engine.py`；新增 `integrations/sarimax_forecast.py`、`integrations/sarimax_exogenous.py`、`integrations/price_candidates.py`、对应脚本/测试和 `forecast-engine/requirements-sarimax.txt`。依赖仅安装在 `runtime/sarimax-deps`，未提交；保留原有未跟踪文件。相关 41 项测试、旧功能 33 项和页面 13 项通过；预览验证两个模型回测及比较，主服务 7860 已重启加载新代码。
- 用户指出 WorkBuddy 已在采集公开数据；其交付清单涵盖与 Codex `automation-2` 重叠的宏观指标和油价。为避免重复，Codex 定时任务已暂停，WorkBuddy 未被修改；其当前调度状态未独立核实。优先复用 WorkBuddy 交付并核验历史版本。本条取代后文已启用或待启用的历史状态。
- 后续由 WorkBuddy 封装数据 MCP Server，预测项目以 MCP Client 按省份及条件查询；现阶段只推进所需数据采集、可检索字段和质量核验，不开发 MCP。省级覆盖与历史可用版本需逐项核实，不能假设已具备。

- 2026-10-28：用户确认试点、优先变量及页面方案并明确要求开始 CHRONOS-003；Codex 当前写入，先核查图谱、现有实现和依赖，再实施 SARIMAX 基线。具体执行步骤见任务文件，未来变量假设数值仍需业务提供。
- 用户已同意未来 12 个月基准情景先使用预测时可获得且已核实变量的最近水平不变；缺失或未核实数据不补零。目前仍无经过业务核验的连续变量序列，不代表已完成情景预测。

- 2026-10-28：按用户要求将 CHRONOS-002 第一阶段功能开发及技术验证作状态归档，历史文件保留原位；回测参考门槛未达、业务精度和用户验收仍未完成。开始 CHRONOS-003 的 SARIMAX 规划，用户要求先策划、有问题先问，不得开始业务开发；需进一步核实外部变量数据，未来基准情景由业务提供。
- 用户提供了 2026 年 10 月价格与权益监测表，本机结构检查显示是活动级记录，不可直接视为长期月度成交价格序列；未来外部变量基准情景由业务提供。已检索国家统计局、成品油公告和 EIA 公开候选来源；已建立每周一 09:00 的 Codex 公开数据采集自动化 automation-2，当前 PAUSED，尚未采集入库。用户确认方案并完成一次采集流程验证后再启用；未来需另外设计独立于 Codex 的调度。历年实际及内部价格权益不得上传或向第三方外发。
- 用户确认另有其他月度价格权益文件，稍后提供路径；覆盖和质量尚未核查。CHRONOS-003 规划已起草，等待用户确认；Codex 已释放写入。
- 随后用户提供九月价格权益汇总及同事整理的新能源涨降价工作簿，已本机只读检查并记录在 CHRONOS-003。九月/十月主要字段基本一致，但九月是截至 21 日的快照，部分日期为空或跨月/年；历史涨降表含 2022 至 2026 年命名工作表，存在未写年份的日期及合并单元格。完整历史覆盖、去重、来源和业务口径尚未核验，不能直接作为连续月度价格或成交价。
- 用户要求先提供分步对接文档；已新增 [第二阶段实施对接说明](tasks/CHRONOS-003/第二阶段实施对接说明.md)，等待用户逐项对接，未开始 SARIMAX 开发。
- 用户已确认步骤一使用 31 省四类合计和广东插电式混合动力作为试点；该确认仅确定样本范围，不改变此前先逐项对接、不立即开工的要求。
- 用户已确认步骤 2.3 先分析指导价、现金优惠和油价，宏观指标放到下一批；目前仅确认分析方向，数据整理和变量建模尚未开始。
- 项目已有价格权益台账接入和查询代码，`docs/rights-cloud-migration.md` 记载曾经做过真实链路验收。本次未访问服务器，不代表当前在线或历史覆盖已验证；先只读盘点复用可能，再决定如何形成按月变量。

- 用户追加 CHRONOS-002：预测助手保留本机历史/回测分析，并新增 DeepSeek 预测分析；在 7860 实测 Flash、Pro 均返回。Codex 已释放写入。业务精度和用户验收待完成，详见任务文件。
- 最近任务：CHRONOS-002，Codex 已完成 Chronos-2 第一阶段开发与技术验证并释放写入；详细进度、命令与证据见 [TASK.md](tasks/CHRONOS-002/TASK.md)。业务精度未达参考门槛，用户业务验收待完成。
- 用户随后要求移除黄色提示及日期并添加使用说明：已在新版页面完成，主服务刷新后验证说明展开、预测生成与基础检查通过；未改动预测算法，修改未提交。
- 上一执行者 TRAE 已释放写入。用户授权的 Git 推送已完成，最近提交 `d078967`。
- 最近完成的开发任务：CHRONOS-001 的模型输入/输出边界和 CPU 离线回归已验收，原 [TASK.md](tasks/CHRONOS-001/TASK.md) 保留详细记录。业务精度、API、网页和 Agent 集成不属于该次验收。
- CHRONOS-002 用户明确仅做 Chronos-2 第一阶段；全部实施步骤已记录，未启动其他阶段。用户确认零售、单位辆、插混含增程、已出现月份缺省份类别可视为零，不需单独预测燃料电池。

## 修改文件与 Git 状态

- 本次推送内容：原 134 个暂存路径（Chronos-2 模型与测试、forecast-engine 页面/脚本/运维工具、skill_runtime 包、周报与口碑链路增强、模型路由等）+ 8 个 V2.0 规则文档终版，提交为 `d078967` 后推送。提交作者为用户 GitHub 身份 `backstreetdeng <backstreetdeng@163.com>`。
- 推送后 `main` 与 `origin/main` 同步，无领先提交、无暂存内容；多余的未跟踪 `outputs/`、`runtime/`、`logs/`、业务数据等按目录规则保留本地、不入 Git。
- CHRONOS-002 修改 app.py、assets/forecast-engine.js/.css、pages/forecast-engine.html、scripts/preview_forecast_engine.py 和本共享文档；新增数据/模型适配器、独立 CLI、对应测试及任务文件。均未提交，已有未跟踪数据、日志及其他成果保留。接班前核对实际 Git 状态。
- 本轮另新增 integrations/forecast_deepseek.py、tests/test_forecast_deepseek.py，修改 home.html 的过时硬编码模型提示；项目代码及任务记录仍未提交，未推送。
- 之前的模型工作：forecast-engine/models/m3_chronos.py、tests/test_chronos2_model.py 已随本次推送入库。完整历史见原任务报告，不重做已完成工作。

## 测试结果

- 先前 CHRONOS-001：本地 CPU、强制离线的 25 项模型测试通过，见 [测试日志](../../outputs/chronos-001/codex-fix-20261027-181227-087351/tests.log)及 [manifest](../../outputs/chronos-001/codex-fix-20261027-181227-087351/manifest.json)。这是既有结果，不代表本轮重跑。
- 本次 CHRONOS-002：最终数据及回测协议单测 10 项通过；此前预测桥接与模型相关 44 项通过；旧市场预测后端 22 项及前端 13 项通过。网页预览实测总量/单省预测、滚动回测、条件变化清除结果及旧导航可见；独立 CLI 真实模型回测通过。数据原文件 SHA256 未变。旧后端测试沙箱内临时文件替换失败，授权本机重跑通过。
- 2026-10-28 重启后 21 项数据/回测/助手测试和 13 项原页面测试通过；主服务浏览器实测无结果提示、31 省预测、回测、误差追问、单省切换及预测范围不足提示。截图重复控件未复现；不是全项目回归。
- DeepSeek 接入：合成数据拦截最终 HTTP 请求的正反向测试及相关数据/预测测试共 28 项通过，原预测页面 13 项通过；隔离预览及主服务实际测试 Flash/Pro。发现旧父进程凭据与项目 .env 不同，预测专用链路读取 .env 后连接成功。

## 未解决问题

- Chronos-2 的 GPU、并发、资源占用及权重精确 revision 尚未验证；历史问题 C002 保留。
- [月度销量-省份.xlsx](月度销量-省份.xlsx) 实际含 2012-01 至 2026-09 月度数据、31 省、四主要动力类型及少量燃料电池。用户确认口径为零售、单位辆、插混含增程，缺失省份/类别可按零处理；完整缺月不补零。四类合计不含燃料电池，不应宣称为完全全国总量。源文件只读，前后哈希一致；历史修订版本仍不可验证。
- 最近 1—6 个月真实数据回测未达迁移文档参考门槛；正式精度和业务使用仍待验收。新版助手现使用当前 Chronos-2 任务进行本机规则分析，原引擎其他标签仍使用模拟数据。事件系数尚未业务评审。
- 用户明确历年真实零售销量不得出域；DeepSeek 仅收到按白名单重建的预测范围、未来月份和分位数，固定分析意图，不发送历史、回测、自由问题或历史对话；禁环境代理和重定向。自由追问仍本机规则处理。输出过滤是有限的关键词/数字拦截，不保证识别所有模型错误；结果需业务复核。隐私结论仅覆盖本次助手，不覆盖其他聊天入口。
- 本轮尚未进行新会话读取验证；静态检查不能证明另一个会话已实际读取规则。

## 下一步

继续 CHRONOS-003：核查价格监测链路及月度覆盖、核验油价历史时点版本，形成可信外生月序列后再做真实因素模型和回测；明确 SARIMAX 与助手仍未集成，不能绕过历史数据出域门禁。用户可在 7860 查看当前模型及对比；正式业务验收仍未完成。继续更新本任务，不新建编号；重启服务遵守月报浏览器保护规则。
