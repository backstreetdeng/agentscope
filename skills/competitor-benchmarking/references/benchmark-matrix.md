# 对标矩阵模板与验收清单

## 1. 结构

- 行：竞品池车型（含目标车型，`is_target=true`）
- 列：维度（L2 默认 8–12 个）
- 契约：[assets/matrix-schema.json](../assets/matrix-schema.json)

## 2. 默认维度集（L2）

| 类别 | 维度 | 数据源 |
|---|---|---|
| 硬参数（P0 锚定） | 纯电续航、整备质量、能耗、电池能量 | `miit_*` |
| 市场 | 指导价、限时价、上市权益、交付周期 | `web_*` |
| 智能 | 智驾方案、激光雷达等感知硬件 | `web_*` / 知识库 |
| 口碑（P2） | 口碑标签、主要好评/差评点 | `reputation_*` |
| 动态 | 最近 OTA、近期关键动作 | `web_*` |

维度可按任务调整（L3 扩展格局类维度），但硬参数四项不可缺省。

## 3. 竞品池入选规则

每款入选车型必须满足：

1. 至少 1 条 `receipt_id` 证据支持其与目标车型的竞争关系（价格带重叠 / 级别相同 / 定位相近，至少其一）。
2. 入选理由记入 `models[].pool_evidence`。
3. 池修正（增删）在迭代循环中显式记录，支持版本对比。

## 4. 验收清单（validate_matrix.py 门槛）

- [ ] `assets/matrix-schema.json` 契约校验通过
- [ ] 硬参数与 `miit.declaration` 一致率 100%（无申报记录者标 `insufficient`）
- [ ] 每格具备 `receipt_id`、`as_of`、`source_tier`、`status`
- [ ] `disputed` 格双边呈现（note 含双方值与口径）
- [ ] 缺失格标 `na` / `insufficient`，无编造值
- [ ] 每款竞品有入选证据
- [ ] So What 每条锚定 `evidence_receipt_ids`

## 5. 交付形式

- 主交付：矩阵 JSON（契约格式），存任务 `outputs/`
- 展示层：前端【竞品对标】页渲染（S6）
- 缺口声明：`gaps[]` 字段 + 交付说明中显式列出
