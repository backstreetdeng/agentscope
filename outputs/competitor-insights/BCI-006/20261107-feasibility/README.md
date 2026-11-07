# BCI-006 · 即时分析 tab 可行性测评证据（20261107-feasibility）

- 任务：[BCI-006](../../../competitor_insight/tasks/BCI-006/TASK.md)
- 结论文档：[analysis-tab-feasibility.md](../../../competitor_insight/docs/analysis-tab-feasibility.md)
- 数据时点：2026-11-07，只读直连 `192.168.3.146:5432/vectordb`
- 复现：在项目根执行 `E:/AI/data/envs/helloagent/Scripts/python.exe -B temp/20261107-bci006/probe_data.py` 等脚本（共 11 个，均为只读）

## 本目录内容

| 文件 | 说明 |
|---|---|
| `manifest.json` | 证据清单（用途/来源/可重建性/保留策略） |
| `four_source_counts.csv` | 库内全部定量车型 × 四源计数，由 `probe_pool.py` 生成 |

## 关键结论数字

- 原型五车：埃安RT 定量 0 / 深访 0；小鹏M03 定量 30 / 深访 0；深蓝L06 定量 0（L07 仅 2）/ 深访 0；银河TT 四源中仅配置 5 款型；MG07 定量 0 / 深访 0。
- 入选五款（10–15 万 SUV）：零跑B10（41/4/392/6）、铂智3X（39/3/66/10）、奇瑞iCAR V23（30/3/78/14）、海狮05 EV（31/3/39/4）、钛3（30/3/730/3）。括号内为定量/深访/口碑提及/配置款型。
- 不可做项：关注「第一排序」结构（无排序题）、`Q5_5` 推荐意愿（0 作答）、竞品侧胜出逻辑（无直接观测题）。

## 清理

结论已固化到测评文档与 TASK.md；本目录保留至 BCI-006 进入 TESTED。`temp/20261107-bci006/` 可在任务完成后清理。
