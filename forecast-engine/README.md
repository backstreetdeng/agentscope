# 乘用车销量预测引擎（MVP）

中国乘用车市场预测引擎：指标库 + 事件库 + L1/L2/L3 三层预测 + 回测框架 + Agent 工具层。

> **迁移/交接/集成到智能体系统：先读 [MIGRATION.md](MIGRATION.md)**（含系统设计洞见、
> 评测结果、迁移验收命令、新笔记本踩坑备忘、战略智能体集成契约）。

## 快速开始

```bash
cd forecast-engine
python data/make_sample_data.py      # 生成示例数据（结构真实，数值为模拟占位）
python ingest/ingest.py              # 建库入库 + 校验
python eval/backtest.py              # 滚动起点回测（M1基线 vs M2 LightGBM分位数）
python run_forecast.py               # 端到端：预测2026-10~2027-12，三情景输出
python run_province.py               # 分省下钻（需先运行 run_forecast.py）
python agent/tools.py demo           # 模拟网页智能体的4个工具调用
```

## 架构（对应七周路线的 W1-W4）

- data/retail_monthly.csv —— 原始数据（当前为模拟占位，替换乘联会真实数据即可）
- data/events.csv —— 事件库（购置税/以旧换新/L3国标/周期/油价，三情景系数）
- db/market.db —— SQLite：indicators / events / metric_dict / forecast_runs
- ingest/ingest.py —— W1：入库+口径校验（动力加总=总量恒等式）
- features/build_features.py —— W3：特征工厂（滞后/滚动/春节/日历）
- models/m1_baseline.py —— W2：季节naive基线
- models/m2_lgbm_quantile.py —— W3：LightGBM分位数（P10/P50/P90）
- eval/backtest.py —— W2：滚动起点回测（MAPE + 区间覆盖率）
- reconcile/reconcile.py —— W5-lite：分量对账到总量（middle-out）
- events/adjust.py —— W4：L2事件修正引擎（机械聚合，可审计）
- run_forecast.py —— 端到端预测入口
- run_province.py —— 分省下钻（份额法，31省×动力，加总恒等于全国）
- agent/tools.py —— 暴露给网页智能体的4个工具
- api/main.py —— FastAPI服务（可选）

## 数据口径（锁死）

- 指标：`retail`（乘联会零售口径），单位：辆
- 动力：`bev`(纯电) / `phev`(插混含增程) / `hev`(普混) / `ice`(燃油) / `total`
- 恒等式：bev + phev + hev + ice = total（入库时强校验）
- point-in-time：每行带 collected_at 时间戳与来源，禁止回填修订值

## 当前数据状态（重要）

`data/retail_monthly.csv` 为**模拟占位数据**：趋势/季节/政策冲击结构按真实市场
特征构造（NEV渗透率 2021~15% → 2026~58%、2025-12购置税末班车冲量、春节月低谷），
但具体数值不可用于对外引用。**替换为乘联会真实月度数据后无需改任何代码。**

## 验收标准（对齐方案）

- 全国月度总量回测 MAPE ≤ 10%（M2，h=1..6）—— 实测 6.65% ✅
- P10-P90 区间覆盖率 80% ± 10 —— 实测 86.1% ✅（conformal带宽校准）
- 动力份额和 = 100%（对账保证）—— 恒等式入库+对账双重保证 ✅
- 每个预测可解释：数据截止日 / 模型版本 / 事件修正链 —— explain工具 ✅

## 已知问题 / 下一步

1. **年度区间偏宽**：annual P10/P90 目前=月度区间直接加总（完全相关假设），
   后续改为相关性折中（sum 与 sqrt-sum 之间）；
2. **真实数据替换**：把乘联会真实月度零售按 `ym,total,bev,phev,hev,ice`
   列结构写入 `data/retail_monthly.csv`，SOURCE 改为 `CPCA_RETAIL_V1`，
   重跑 ingest -> backtest -> run_forecast 即可，无需改代码；
3. **W5-W7 待做**：Chronos-2 基础模型进集成 / 分省维度（份额法）/
   数据采集 Agent 定时任务 / 自动月度回测记分卡；
4. 事件系数（events.csv）目前来自调研假设，正式使用前应由分析师评审并补 evidence_url。

## 分省维度（V2，已交付）

```bash
python data/make_province_sample.py   # 分省模拟数据（31省，占位）
python ingest/ingest_province.py      # 分省入库（校验：分省加总=全国）
python eval/backtest_province.py      # 份额法回测
python run_province.py                # 2027分省预测（三情景）
```

- **方法**：省份份额（滚动12月均值×阻尼趋势）× 全国预测 —— 精度路由，
  把总量层精度传导到每个省，分省加总恒等于全国；
- **回测**（模拟数据）：全省平均 MAPE **3.58%** vs 省级naive直接预测 7.27%，
  大/中/小省精度几乎一致（3.5~3.7%），验证份额法对小省的价值；
- 输出：`outputs/province_forecast_{base,bull,bear}.csv`

## 真实数据采集结论（2026-10-26 调研）

- **公开可采**：月度零售总量、NEV零售、常规燃油零售、渗透率（乘联会月报，
  各媒体转载）→ 已存 `data/cpca_real_anchors.csv`（含来源）；
- **公开不可采**：BEV/PHEV零售拆分、HEV零售（仅批发口径有拆分）→ 完整5序列
  需乘联会会员数据或人工逐月整理月报PDF；
- 真实锚点显示2026年市场比模拟假设更严峻（YTD -21%、9月渗透率67.1%），
  替换真实数据后预测结论会显著下修，代码无需改动。

## Chronos-2 集成状态（W5）

**已完成（2026-10-26）**。用户终端安装 chronos-forecasting 1.5.3（绕开Codex沙箱），
模型权重经 hf-mirror.com 下载，本地缓存离线推理。

- chronos-forecasting **1.5.3 不含 Chronos2Pipeline 类**（Chronos-2 需更新版本），
  当前自动降级使用 **amazon/chronos-bolt-base**（Apache-2.0，同族前代最强）；
  后续 `pip install -U chronos-forecasting` 后无需改代码自动切换 chronos-2；
- **回测对比**（模拟数据，12 origins × h=1..6）：

| 序列 | M1季节naive | M2 LightGBM | M3 Chronos-Bolt | M2+M3集成 |
|---|---|---|---|---|
| total | 5.07% | 6.65% | 7.21% | 6.75% |
| bev | 5.10% | 6.84% | 9.83% | 7.73% |
| phev | 8.80% | 7.71% | 9.77% | **6.61%** |
| ice | 15.03% | 11.16% | **5.98%** | 8.27% |

- **结论**：M3 零样本在急速下滑的 ice 序列上全场最优（5.98%），集成在 phev 上
  最优，无单一模型全面领先 —— 印证"集成+多样性"论断；
- `run_forecast.py` 中 `USE_M3_ENSEMBLE` 开关控制是否进集成（当前默认关闭，
  待真实数据回测后再定权重；原则：只在优于 M2 时进入）。
