# 枚举取值归一映射表（BCI-004-L12）

数据源：`user_insight.tag` 全库 63 位受访者（只读扫描，2026-11-07）。
规则实现：`competitor_insight/server/value_normalizer.py`（唯一归一处）。

## purchase_attribute（标签「首增换购属性」，模板唯一单选枚举）

| 原值 | 全库次数 | 建议归一值 | 判定 | 依据 | 处置 |
|---|---|---|---|---|---|
| 换购。 | 31 | 换购 | 直通 | 去标点即命中模板选项 | 保留 |
| 增购。 | 20 | 增购 | 直通 | 去标点即命中模板选项 | 保留 |
| 首购。 | 10 | 首购 | 直通 | 去标点即命中模板选项 | 保留 |
| 实际增购。 | 1 | 增购 | 归一（同义/修饰） | 口语/修饰写法归一：实际增购 → 增购 | 保留归一值，source_ref 记原值 |
| 换购；增购。 | 1 | — | 互斥多值（回退元数据） | 标签含多个互斥取值：换购；增购，无法确定单一选项（候选：换购、增购） | 先回退 `interview.purchase_type`：与候选唯一一致取值 + `source_ref.correction`；缺失/冲突落 suspect |

合计 63 条；无空值/「未提及」/「不适用」写法。

## 同类标签扫描结果

| 类别 | 标签数 | 是否参与单选归一 | 说明 |
|---|---|---|---|
| 模板单选枚举（tag 驱动） | 1 | 是 | 「首增换购属性」 |
| 模板单选枚举（无来源） | 1 | 否 | `kol_influence`，fill_mode=none |
| 模板多值列表（tag 驱动） | 2 | 否（拆列表） | APP偏好、汽车触媒偏好 |
| 其余声明 allowed_values 的标签 | 82 | 否 | 自由文本抽取，allowed_values 仅作参考词表 |

### info_channels 多值覆盖（汽车触媒偏好、APP偏好）

模板 options 11 项；标签实际出现 66 种写法，其中 60 种不在 options 内。

未覆盖写法（次数，按降序前 15）：视频号(13)、未提及(10)、微信(9)、哔哩哔哩(6)、快手(6)、线下门店(6)、微博(5)、淘宝(4)、今日头条(3)、微信朋友圈(3)、京东(2)、公众号(2)、拼多多(2)、百度(2)、腾讯新闻(2)

当前按原词入列表（符合“未覆盖不要臆测”），未做词表映射；是否映射待用户决定。

## 规则与测试

- 判定顺序：空值/无数据标记 → `no_value`；否定表述 → `unknown`；多片段 → 互斥 `ambiguous` / 同选项 `normalized` / 含未识别片段 `unknown`；单片 → 精确 `exact`、去修饰前缀或唯一包含 `normalized`、否则 `unknown`。
- 生成器分流：`exact`/`normalized` 取值并写 `source_ref.normalized_from`；`no_value` 落 `fill_mode=none`+`review_status=missing`；`ambiguous` 先回退 `interview.purchase_type`（一致取值 + `correction`，缺失/冲突仍 `suspect`）；`unknown` 抛 `invalid_enum` 整人失败。
- 单测：`tests/test_value_normalizer.py`（含回退三分支）+ `tests/test_channel_normalizer.py`；全量 104 项通过。
