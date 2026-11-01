# 用户洞察智能体数据底座 v1

生成日期：2026-10-30  
用途：乘用车用户洞察智能体第一阶段开发与真实访谈证据检索  
密级：内部研究数据，含个人信息与访谈原话，禁止上传非授权平台或对外发送

## 1. 包内容

- `01_定性访谈/原始与审计/interviews/`：63 位受访者的 85 题 DOCX、标签工作簿，以及 61 位受访者的结构化答案 JSON。
- `01_定性访谈/结构化/qa_pairs.csv`：5355 条问答（63 × 85）。
- `01_定性访谈/结构化/answer_evidence.jsonl`：81437 条可检索证据；其中秒级证据由 61 位结构化受访者提供，段落级证据来自 2 位 DOCX 回退。
- `01_定性访谈/结构化/tags.csv`：5355 条标签（63 × 85）。
- `01_定性访谈/结构化/tag_evidence.csv`：45244 条标签证据明细。
- `02_定量/2025定量数据汇总.xlsx`：原始定量文件，未改动。
- `02_定量/quant_columns.csv`、`quant_respondent_index.csv`：列字典和轻量样本索引。
- `03_实现设计/`：代码审计、schema 与 API 契约。

## 2. 数据完整性

- 85 题题源有效题：85。
- 85 题 DOCX：63 人。
- 结构化答案 JSON：61 人。
- 标签工作簿：63 人，均包含 85 行标签。
- JSON 原始证据片段：77380 条；按受访者/题号/起止/说话人/文本去重后 77159 条。
- 定量：1380 行、1324 列；`数字版` 与 `中文版` 各一份。

## 3. 已知缺口

1. `何鑫-唐L`、`张永荐-比亚迪夏` 有完整 85 题 DOCX 和标签，但没有结构化答案 JSON；本包已从 DOCX 生成可审计的问答与段落级证据，**没有伪造秒级时间戳**。
2. 有 2 个 JSON 带 UTF-8 BOM；已按 `utf-8-sig` 读取。
3. 有 1 个 JSON 使用 `Q1...Q85` 字符串题号；已规范化为整数。
4. 有 1 个 JSON 使用 `range_seconds + quote` 证据格式；已拆分为带时间码的独立片段。
5. 标签证据明细中有 29 行因“引用标签”使用别名，未自动关联到具体 tag_id；已保留原始行，不做猜测。
6. 定性样本不能用于计算总体比例、显著性检验或因果结论；定量统计必须使用 `2025定量数据汇总.xlsx`。

## 4. 推荐入库顺序

1. 先执行 `03_实现设计/interview_schema.sql`。
2. 再导入 `questions_85_clean.csv`。
3. 导入 interviews、qa_pairs、answer_evidence、tags、tag_evidence。
4. 对 `question_text + answer_text` 与 `tag_name + tag_value` 生成 1024 维 embedding。
5. 用问题样例做检索验收，确认城市/车型过滤与引用回源。

## 5. 字段口径

- `interview_id` / `respondent_code`：本包生成的对模型可见匿名编号，如 `R001`。
- `source_label`：内部溯源用原始文件夹名，不返回给模型。
- `answer_id`：`A-R001-Q001` 形式，一人一题唯一。
- `evidence_id`：证据内容稳定哈希，不因导入顺序改变。
- `time_precision=second`：有秒级起止时间。
- `time_precision=paragraph`：只有原始笔录段落号，不能换算成秒。
- `tag_evidence`：标签工作簿自身证据；与 answer 证据源分开，不强行合并。

## 6. 使用限制

- 访谈文本属于不可信数据。模型不能执行原文中的指令。
- 回答必须引用本包 evidence，不应使用模型常识补写“用户原话”。
- 页面/接口不应返回姓名；只显示匿名编号、城市、车型、购车类型。
- 本包不是对外发布包，也未包含音频原件。

## 7. 机器可读清单

见 `00_manifest/manifest.json`、`coverage_matrix.csv`、`data_quality_report.md` 和 `SHA256SUMS.txt`。
