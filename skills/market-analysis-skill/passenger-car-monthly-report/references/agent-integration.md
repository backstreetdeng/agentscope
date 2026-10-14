# 市场战略 Agent 接入契约

## 产品标识

- 用户展示名：`乘用车月报智能生成`
- Skill Code：`skill_passenger_car_monthly_report`
- 前端能力ID：`passenger_car_monthly_report`
- 推荐分析类型：`passenger_car_monthly_report`
- 已下架旧入口：`skill_market_monthly_report`

## 路由边界

- Agent 入口必须先按精确任务类型 `passenger_car_monthly_report` 分流，再执行任何关键词自动路由。
- 该分支不得实例化或调用旧 `MarketAnalysisSkill.prepare()`，不得读取其默认 Excel、样例数据或数据摘要。
- 数据源采集、标准化数据包、证据包和确定性PPT更新均由后台任务编排；大模型不能自行决定跳过这些阶段。
- 洞察与主旨句在确定性PPT更新之前完成；PPT阶段只消费已通过门禁的数据包和证据包，不再次读取数据源或联网搜索。

## 调用参数

```json
{
  "agent": "market_strategy",
  "analysis_type": "passenger_car_monthly_report",
  "source_type": "data_source",
  "dashboard": "乘用车月报数据源",
  "report_month": "YYYY-MM",
  "mode": "data_ppt | analysis_ppt | validate_only",
  "mcp_plugins": ["policy", "rights", "new-car", "reputation"],
  "allow_public_search": true
}
```

`data_ppt` 不需要外部证据工具。`analysis_ppt` 默认挂载 `policy`、`rights`、`new-car`；`reputation` 仅在车型产品力或用户观望异常触发时调用。`allow_public_search=true` 仅授权查询公开信息，不得把内部卡片内容或未公开数据发往外网。

## 后台任务 API

月报技能使用持久化任务协议，不通过一个同步 `/api/chat` 请求等待全部卡片完成。

1. `POST /api/monthly-report/jobs`：提交上述任务参数，立即返回 HTTP 202 和 `run_id`。
2. `GET /api/monthly-report/jobs/{run_id}`：读取任务状态、真实阶段事件、检查点和最终结果。
3. `POST /api/monthly-report/jobs/cancel`：提交 `{"run_id":"..."}`，协作式取消并保留检查点。
4. `POST /api/monthly-report/jobs/resume`：提交 `{"run_id":"..."}`，从最近检查点继续。
5. `POST /api/ppt`：点击“生成PPT版”时必须同时提交 `run_id`；后端以该任务的数据包和证据包执行确定性更新，不得仅依赖前端Markdown正文。

状态包括 `running`、`completed`、`partial_completed`、`failed`、`cancelled`、`input_required`。`failed`、`cancelled` 和 `input_required` 在 `recoverable=true` 时可以恢复。`partial_completed` 表示核心数据或PPT已完成，但外部证据或非关键页面仍需复核，不得作为正式分析版。页面刷新后前端必须从本地保存的 `run_id` 重新查询，不得自动创建重复任务。

任务事件至少包含：

```json
{
  "seq": 4,
  "at": "2026-09-29T10:00:00",
  "phase": "data_collect",
  "subphase": "card_batch",
  "status": "running",
  "message": "正在读取第4/9批映射卡片并保存检查点",
  "progress": 36,
  "batch": {"kind": "cards", "index": 4, "total": 9, "completed_items": 20}
}
```

`progress` 是后端阶段进度，不是预计剩余时间。前端按 `seq` 增量显示事件，禁止用固定计时器模拟“模型仍在执行”。

## 检查点契约

观点代码与当前规则版本必须真实绑定。三个具名事实模块形成逐页事实包，`utils/monthly_report_narrative.py` 负责模型调用、语义门禁和页面检查点。版本或事实哈希不一致时重新验收/生成观点，不重采45张卡片。第5页本地生成页标题，跳过模型正文生成；内部库存关系仍用于反查和概述。`utils/monthly_ppt_layout.py` 只读核验库存原尺寸与图表标题，以及第7/8/12/13/15页全年结构参照、第17页同期累计的不同契约。旧 `ppt_comparison_facts` 不再驱动图表改写；chart和embed保持已核验母版原样。

网页导出函数 `generate_passenger_monthly_pptx` 必须真实调用 `validate_narrative_package`，只读本轮数据与观点检查点，再核验应更新分析页及映射推导的滞后保留页、月份、规则版本、具名事实和版式后才写PPT。旧规则包不能自动改版本冒充通过：未完成任务可恢复观点阶段；已完成历史任务保持原档案，新建任务生成新版观点并复用同月已验卡片。不能提示已完成任务点击无效的恢复入口。连接状态接口返回当前加载的规则版本，任务进度留下同版规则日志。

- `preflight`：页面连接、登录态、报告月份、模板版本及快照路径。
- `data_collect/reuse`：跨任务复用时记录已确认的报告月份、数据源身份、历史数据包路径、45/45门禁结果、原始采集时间和 `same_report_month_verified` 复用原因。该记录只替代卡片采集，不自动替代当前任务尚未完成的洞察、主旨句或PPT阶段。
- `data_collect/card_batch/{batch}`：卡片范围、成功项、失败项、重试次数和批次文件路径。
- `data_collect/evidence_batch/{batch}`：异常对象、插件/Tavily查询、来源记录和批次文件路径。
- `data_gate/cross_validate`：标准化数据包、映射、完整性代码、交叉校验结果和是否允许继续。
- `result_prepare/anomaly_detect`：异常候选、历史窗口和候选优先级。
- `result_prepare/evidence_grade`：证据记录、等级、竞争性解释和缺口。
- `result_prepare/narrative`：逐页主旨句、正文观点和概述页汇总。
- `result_prepare/narrative_gate`：事实ID、跨期窗口、证据等级和因果措辞验证结果。
- `ppt_update`：由右侧“生成PPT版”触发，保存模板/数据/证据哈希、输出PPT路径、幂等键和写入状态。
- `output_gate`：结构、数据、视觉和可编辑性验证结果。
- `archive`：归档项目ID；同一 `run_id` 只能对应一条记录。

服务启动时自动恢复状态为 `queued` 或 `running` 的任务。恢复前必须验证检查点文件仍在许可输出目录内；无效检查点回退到对应只读阶段重新执行，不得读取旧版Excel。

## 运行阶段

1. `preflight`：确认登录态、数据源页面、目标月份和模板版本，保存检查点。优先使用请求中的 `report_month`；未指定月份时交叉检查总销量与库存等日期锚点，部分卡片滞后允许继续，记录实际月份并保留对应PPT页；只有月份无法确认、目标尚无有效数据或未来月份冲突才返回 `input_required`。确认后立即显示报告月份、处理方式和复用/未复用原因。明确指定历史月份且存在同来源完整数据包时可复用该包；不得把当前页面其他月份数值改标为目标月份。
2. `data_collect`：先按 `preflight` 确认的报告月份和数据源身份查找历史45/45已验收数据包；命中后写入 `data_collect/reuse` 并跳过卡片读取。未命中时才用 `card_batch` 分批读取卡片；再按异常对象用 `evidence_batch` 调用结构化插件，证据不足时定向调用Tavily。每批独立保存和重试。历史包不得跨月份复用，不能用固定的短时缓存窗口替代月份校验。
3. `data_gate/cross_validate`：合并标准化数据包，检查月份、覆盖率、口径、计算关系、来源时点和实体匹配。
4. `result_prepare`：依次执行 `anomaly_detect`、`evidence_grade`、`narrative` 和 `narrative_gate`，生成可追溯证据包并返回分析结果。
5. 用户点击“生成PPT版”，以原 `run_id` 进入 `ppt_update`：从检查点读取通过门禁的数据包和证据包，一次性更新母版副本；此阶段禁止再调用浏览器、插件或联网搜索。
6. `output_gate`：执行数据、结构、视觉、可编辑性和证据引用验证。
7. `delivery`：交付PPT及审计文件，并按 `run_id` 幂等归档。

数据门禁未通过时必须停止在第3阶段，保留逐卡片实际月份和失败原因，以可恢复的 `input_required` 结束，不得发出PPT准备或成功完成事件；外部证据不足时允许生成纯事实主旨句。分析门禁未通过时只能进入 `partial_completed` 并交付带风险标识的草稿，不得标为正式分析版。

单次浏览器或检索请求的360秒只是保护性超时。超时后重建对应连接并重试当前批次；任务总时长不受360秒限制。达到批次重试上限后保存失败信息并返回可恢复状态，不得清空已完成检查点。

## 工具路由

- `policy_*`：政策新增、到期、暂停、适用地区与有效期。
- `rights_*`：降价、金融方案、置换补贴、权益加码或减码。
- `new_car_*`：上市、改款、换代、配置、规划车型和销量爬坡。
- `reputation_*`：车型评价、用户顾虑和产品问题线索；不能替代销量或总体需求数据。
- Tavily：排产、交付、车展、油价、宏观指标及插件未覆盖的最新官方事件。当前项目工具名为 `tavily_search`；若平台以别名注册，则使用运行时实际工具名。

不要把四个插件和Tavily并行无差别调用。先由异常对象决定工具和查询窗口，插件返回不足时才补外网。每次调用都写入工具审计记录。

## 登录态边界

开发验证阶段可由用户在Codex内置浏览器登录后运行。产品化接入应提供本地数据采集连接器或官方导出接口，使AgentScope工具链可以获得结构化快照；不得把账号密码写入技能配置。
