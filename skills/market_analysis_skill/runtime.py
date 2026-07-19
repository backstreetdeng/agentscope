"""中国乘用车市场月报分析 Skill 运行时。

本模块把业务专家提供的 ``SKILL-improved`` 从写作说明转化为可执行能力：

1. 识别月报/季度市场分析任务；
2. 读取 xlsx 验数表，生成可审计的数据摘要；
3. 在调用模型前执行输入数据门禁；
4. 将报告规范、数据边界和已验证数据注入市场战略 Agent；
5. 在模型输出后复核章节完整性与可追溯性。

设计约束：
- 使用 Python 标准库解析 .xlsx，避免为该 Skill 额外污染现有虚拟环境；
- 不把展示型交叉表误判为车型/品牌明细数据；
- 缺少 TOP 车型、品牌集中度时，要求模型明确披露数据缺口而非补造数据。
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile


SKILL_NAME = "china-passenger-vehicle-market-analysis"
SKILL_VERSION = "1.0.0"
ANALYSIS_TYPE = "market_monthly_report"

PROJECT_DIR = Path(__file__).resolve().parents[2]
BUSINESS_SOURCE_DIR = PROJECT_DIR / "skills" / "market-analysis-skill"
DEFAULT_SAMPLE_DATASET = BUSINESS_SOURCE_DIR / "1-5月报 AI验数.xlsx"

WORKBOOK_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "package_rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}

MONTHLY_TRIGGER_TERMS = (
    "月报",
    "月度报告",
    "月度市场",
    "市场走势",
    "车型类别",
    "车型级别",
    "细分市场结构",
    "top车型",
    "top 车型",
    "销量结构",
)

REPORT_SECTIONS = (
    "核心数据速览",
    "01 当月乘用车市场走势解读",
    "02 当月乘用车市场结构特征分析",
    "2.1 车型类别",
    "2.2 车型级别",
    "2.3 轿车级别分析",
    "2.4 SUV级别分析",
    "2.5 MPV级别分析",
    "03 下月乘用车市场展望",
    "数据来源",
)

# 展示型验数表并不包含这些解释变量。若没有明确标为风险变量、待核验假设或数据
# 缺口，月报不得把它们写成已经验证的市场因果。
UNSUPPORTED_ATTRIBUTION_TERMS = (
    "新能源",
    "燃油",
    "纯电",
    "共享出行",
    "排产",
    "渠道",
    "经销商",
    "库存",
    "促销",
    "政策",
    "价格带",
    "合资",
    "微型客货",
    "终端需求",
    "产能",
    "交付",
    "批发",
    "零售",
    "出口",
    "上险",
    "首次",
    "连续",
    "新车型",
    "上市",
    "改款",
    "换代",
    "终端总需求",
    "主动收缩",
    "抗周期",
    "主要拖累",
)
ATTRIBUTION_DISCLOSURE_TERMS = (
    "数据缺口",
    "未提供",
    "不生成",
    "不作",
    "不进行",
    "待核验",
    "若",
    "可能",
    "预计",
    "无法",
    "未明示",
    "无可比",
)


@dataclass
class SkillCheck:
    """单项输入或输出质量检查结果。"""

    check_id: str
    name: str
    status: str
    evidence: str
    suggestion: str

    def as_dict(self) -> dict[str, str]:
        return {
            "id": self.check_id,
            "name": self.name,
            "status": self.status,
            "evidence": self.evidence,
            "suggestion": self.suggestion,
        }


@dataclass
class SkillEvent:
    """前端和控制台可直接消费的真实 Skill 执行审计事件。"""

    stage: str
    status: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"stage": self.stage, "status": self.status, "detail": self.detail}


@dataclass
class SheetSnapshot:
    """一个 Excel 工作表的轻量快照，只保留 Skill 所需的可读数据。"""

    name: str
    rows: list[list[str]]

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def column_count(self) -> int:
        return max((len(row) for row in self.rows), default=0)

    def text(self) -> str:
        return " ".join(cell for row in self.rows for cell in row if cell)


@dataclass
class MarketSkillContext:
    """一次市场月报 Skill 调用的完整上下文。"""

    active: bool
    trigger_mode: str
    question: str
    dataset_path: Path | None = None
    dataset_label: str = ""
    selected_sheet: str = ""
    snapshots: list[SheetSnapshot] = field(default_factory=list)
    input_checks: list[SkillCheck] = field(default_factory=list)
    output_checks: list[SkillCheck] = field(default_factory=list)
    events: list[SkillEvent] = field(default_factory=list)
    prompt_context: str = ""

    def input_gate(self) -> str:
        return calculate_gate(self.input_checks)

    def output_gate(self) -> str:
        return calculate_gate(self.output_checks) if self.output_checks else "待生成"

    def as_response(self) -> dict[str, Any]:
        """返回给 Web 前端的安全摘要，不返回任何环境变量或模型密钥。"""

        return {
            "name": SKILL_NAME,
            "version": SKILL_VERSION,
            "active": self.active,
            "trigger_mode": self.trigger_mode,
            "dataset": {
                "label": self.dataset_label,
                "path": relative_display_path(self.dataset_path),
                "selected_sheet": self.selected_sheet,
                "sheet_count": len(self.snapshots),
                "sheets": [item.name for item in self.snapshots],
            },
            "input_gate": self.input_gate(),
            "output_gate": self.output_gate(),
            "input_checks": [item.as_dict() for item in self.input_checks],
            "output_checks": [item.as_dict() for item in self.output_checks],
            "events": [item.as_dict() for item in self.events],
        }


class MarketAnalysisSkill:
    """把业务月报方法论封装为可由市场战略 Agent 调用的 Skill。"""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        self.settings = dict(config.get("skills", {}).get("market_analysis", {}))

    def should_activate(self, question: str, analysis_type: str = "") -> tuple[bool, str]:
        """判断是否进入月报分析模式。

        显式下拉选择优先级最高；自动模式仅在题目含月报类关键词时启用，避免把
        15-20 万新能源 SUV 的战略机会问答错误套入长篇月报模板。
        """

        if analysis_type == ANALYSIS_TYPE:
            return True, "explicit"
        if not self.settings.get("auto_trigger", True):
            return False, "disabled"

        normalized = normalize(question).lower()
        if any(term in normalized for term in MONTHLY_TRIGGER_TERMS):
            return True, "auto"
        return False, "not_matched"

    def prepare(
        self,
        question: str,
        analysis_type: str = "",
        dataset_path: str | Path | None = None,
        sheet_name: str | None = None,
    ) -> MarketSkillContext:
        """执行输入解析与数据门禁，并返回可注入模型的上下文。"""

        active, trigger_mode = self.should_activate(question, analysis_type)
        context = MarketSkillContext(active=active, trigger_mode=trigger_mode, question=question)
        if not active:
            return context

        context.events.append(SkillEvent("skill-dispatch", "success", f"已激活 {SKILL_NAME}，模式={trigger_mode}。"))
        source, source_label = self._resolve_dataset(dataset_path)
        context.dataset_path = source
        context.dataset_label = source_label

        if source is None:
            context.input_checks.append(
                SkillCheck(
                    "dataset_available",
                    "数据集可用性",
                    "阻断",
                    "未配置有效的月报数据集。",
                    "在 .env 设置 MARKET_ANALYSIS_DATA_PATH，或在 model_config/config.json 配置 skills.market_analysis.default_dataset。",
                ),
            )
            context.events.append(SkillEvent("dataset-resolve", "blocked", "未找到可读取的月报数据集。"))
            context.prompt_context = build_blocked_prompt(context)
            return context

        try:
            context.snapshots = read_xlsx_workbook(source)
        except (OSError, BadZipFile, ET.ParseError, ValueError) as exc:
            context.input_checks.append(
                SkillCheck(
                    "dataset_readable",
                    "Excel 读取能力",
                    "阻断",
                    f"无法读取 {source.name}：{type(exc).__name__}: {exc}",
                    "确认文件是未加密的 .xlsx，并检查是否被 Excel 占用或损坏。",
                ),
            )
            context.events.append(SkillEvent("dataset-parse", "blocked", f"Excel 解析失败：{type(exc).__name__}"))
            context.prompt_context = build_blocked_prompt(context)
            return context

        if sheet_name:
            target = normalize(sheet_name).lower()
            selected = next((item for item in context.snapshots if normalize(item.name).lower() == target), None)
            if selected is None:
                context.input_checks.append(
                    SkillCheck(
                        "selected_sheet",
                        "指定工作表",
                        "阻断",
                        f"未找到工作表：{sheet_name}。可用工作表：" + "、".join(item.name for item in context.snapshots),
                        "传入 Excel 中真实存在的工作表名称，例如“4月”。",
                    ),
                )
                context.events.append(SkillEvent("sheet-select", "blocked", f"未找到工作表：{sheet_name}"))
                context.prompt_context = build_blocked_prompt(context)
                return context
            context.snapshots = [selected]
            context.selected_sheet = selected.name
            context.dataset_label = f"{source_label} / 工作表={selected.name}"
            context.events.append(SkillEvent("sheet-select", "success", f"已选择工作表：{selected.name}"))

        context.input_checks = validate_input_dataset(context.snapshots, source)
        context.events.extend(
            [
                SkillEvent("dataset-resolve", "success", f"数据集={source.name}；工作表={len(context.snapshots)} 个。"),
                SkillEvent("data-gate", gate_event_status(context.input_gate()), summarize_checks(context.input_checks)),
                SkillEvent("context-build", "success", "已生成经数据边界约束的月报写作上下文。"),
            ],
        )
        context.prompt_context = build_agent_instruction(context)
        return context

    def validate_report(self, report: str, context: MarketSkillContext) -> list[SkillCheck]:
        """在 MiniMax-M3 返回后复核报告结构，结果同步到审计日志。"""

        if not context.active:
            return []
        context.output_checks = validate_generated_report(report, context)
        context.events.append(
            SkillEvent("report-gate", gate_event_status(context.output_gate()), summarize_checks(context.output_checks)),
        )
        return context.output_checks

    def status(self) -> dict[str, Any]:
        """提供调试接口使用的静态能力和默认数据源状态。"""

        source, label = self._resolve_dataset(None)
        payload: dict[str, Any] = {
            "name": SKILL_NAME,
            "version": SKILL_VERSION,
            "analysis_type": ANALYSIS_TYPE,
            "source_material": str(BUSINESS_SOURCE_DIR.relative_to(PROJECT_DIR)).replace("\\", "/"),
            "default_dataset": {
                "label": label,
                "path": relative_display_path(source),
                "exists": bool(source and source.is_file()),
            },
            "activation": {
                "explicit": ANALYSIS_TYPE,
                "auto_trigger_terms": list(MONTHLY_TRIGGER_TERMS),
            },
            "capabilities": [
                "xlsx 展示型交叉表解析",
                "数据输入门禁",
                "MiniMax-M3 报告上下文注入",
                "报告章节与数据缺口复核",
            ],
        }
        if source and source.is_file():
            preview = self.prepare("请生成月度乘用车市场报告", ANALYSIS_TYPE)
            payload["input_gate"] = preview.input_gate()
            payload["input_checks"] = [item.as_dict() for item in preview.input_checks]
        return payload

    def _resolve_dataset(self, dataset_path: str | Path | None) -> tuple[Path | None, str]:
        """按显式参数、环境变量、配置、业务验数样本依次确定数据来源。"""

        candidates: list[tuple[str, str | Path | None]] = [
            ("本次调用指定的数据集", dataset_path),
            ("环境变量 MARKET_ANALYSIS_DATA_PATH", os.getenv("MARKET_ANALYSIS_DATA_PATH")),
            ("模型配置默认数据集", self.settings.get("default_dataset")),
            ("业务提供的验数样本", DEFAULT_SAMPLE_DATASET),
        ]
        for label, candidate in candidates:
            if not candidate:
                continue
            path = Path(candidate)
            if not path.is_absolute():
                path = PROJECT_DIR / path
            if path.is_file() and path.suffix.lower() == ".xlsx":
                return path.resolve(), str(self.settings.get("default_dataset_label") or label)
        return None, "未配置"


def read_xlsx_workbook(path: Path) -> list[SheetSnapshot]:
    """读取未加密 xlsx 的文本/数值单元格。

    业务验数文件是面向 PPT 制图的交叉表，不依赖 pandas 的表头推断；这里直接读取
    OpenXML 单元格坐标，可稳定保留“车型类别、车型级别、同比、环比”等版式语义。
    """

    with ZipFile(path) as workbook:
        shared_strings = read_shared_strings(workbook)
        workbook_root = ET.fromstring(workbook.read("xl/workbook.xml"))
        relationship_root = ET.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
        relationship_targets = {
            item.attrib.get("Id", ""): item.attrib.get("Target", "")
            for item in relationship_root.findall("package_rel:Relationship", WORKBOOK_NS)
        }

        sheets: list[SheetSnapshot] = []
        for sheet in workbook_root.findall("main:sheets/main:sheet", WORKBOOK_NS):
            name = sheet.attrib.get("name", "未命名工作表")
            relationship_id = sheet.attrib.get(f"{{{WORKBOOK_NS['rel']}}}id", "")
            target = relationship_targets.get(relationship_id, "")
            if not target:
                continue
            worksheet_path = normalize_worksheet_path(target)
            if worksheet_path not in workbook.namelist():
                continue
            root = ET.fromstring(workbook.read(worksheet_path))
            sheets.append(SheetSnapshot(name=name, rows=read_sheet_rows(root, shared_strings)))

    if not sheets:
        raise ValueError("工作簿中未发现可读取的工作表。")
    return sheets


def read_shared_strings(workbook: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in workbook.namelist():
        return []
    root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
    return ["".join(item.itertext()).strip() for item in root.findall("main:si", WORKBOOK_NS)]


def normalize_worksheet_path(target: str) -> str:
    cleaned = target.replace("\\", "/").lstrip("/")
    if cleaned.startswith("xl/"):
        return cleaned
    return "xl/" + cleaned.lstrip("./")


def read_sheet_rows(root: ET.Element, shared_strings: list[str]) -> list[list[str]]:
    values: dict[tuple[int, int], str] = {}
    max_row = 0
    max_col = 0
    for cell in root.findall(".//main:sheetData/main:row/main:c", WORKBOOK_NS):
        cell_ref = cell.attrib.get("r", "")
        row_number, column_number = parse_cell_reference(cell_ref)
        if row_number <= 0 or column_number <= 0:
            continue
        values[(row_number, column_number)] = read_cell_value(cell, shared_strings)
        max_row = max(max_row, row_number)
        max_col = max(max_col, column_number)

    rows: list[list[str]] = []
    for row_number in range(1, max_row + 1):
        rows.append([values.get((row_number, column_number), "") for column_number in range(1, max_col + 1)])
    return rows


def parse_cell_reference(reference: str) -> tuple[int, int]:
    match = re.fullmatch(r"([A-Z]+)([0-9]+)", reference.upper())
    if not match:
        return 0, 0
    letters, row_value = match.groups()
    column = 0
    for letter in letters:
        column = column * 26 + ord(letter) - ord("A") + 1
    return int(row_value), column


def read_cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t", "")
    if cell_type == "inlineStr":
        inline = cell.find("main:is", WORKBOOK_NS)
        return "".join(inline.itertext()).strip() if inline is not None else ""

    value_node = cell.find("main:v", WORKBOOK_NS)
    raw_value = value_node.text.strip() if value_node is not None and value_node.text else ""
    if cell_type == "s" and raw_value.isdigit():
        index = int(raw_value)
        return shared_strings[index] if 0 <= index < len(shared_strings) else ""
    if cell_type == "b":
        return "是" if raw_value == "1" else "否"
    if raw_value:
        return raw_value

    formula = cell.find("main:f", WORKBOOK_NS)
    return "=" + formula.text if formula is not None and formula.text else ""


def validate_input_dataset(sheets: list[SheetSnapshot], source: Path) -> list[SkillCheck]:
    """面向行业报告的输入质量门禁，而非泛化的 Excel 完整性检查。"""

    workbook_text = " ".join(sheet.text() for sheet in sheets)
    numeric_count = len(re.findall(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?(?:E[-+]?\d+)?", workbook_text, flags=re.IGNORECASE))
    has_category = all(token in workbook_text for token in ("轿车", "SUV", "MPV"))
    has_trend = all(token in workbook_text for token in ("同比", "环比"))
    has_level = any(token in workbook_text for token in ("A00", "A0", "C+"))
    top_model_table_count = count_top_model_tables(sheets)
    has_top_model = top_model_table_count > 0
    has_brand = "品牌" in workbook_text or "CR5" in workbook_text.upper()

    checks = [
        SkillCheck(
            "dataset_readable",
            "数据文件可读取",
            "通过",
            f"已读取 {source.name}，包含 {len(sheets)} 个工作表。",
            "保留原始文件版本和数据提取日期，确保报告可复算。",
        ),
        SkillCheck(
            "period_coverage",
            "统计周期覆盖",
            "通过" if len(sheets) >= 1 else "阻断",
            f"识别到工作表周期：{'、'.join(sheet.name for sheet in sheets)}。",
            "正式月报建议同时提供当月、上月、去年同期与年累计口径。",
        ),
        SkillCheck(
            "market_dimension",
            "市场结构维度",
            "通过" if has_category and has_level else "待补充",
            "已识别车型类别、车型级别等结构字段。" if has_category and has_level else "未完整识别车型类别或车型级别字段。",
            "至少提供轿车/SUV/MPV与 A00-A0-A-B-C+ 的可比口径。",
        ),
        SkillCheck(
            "trend_metric",
            "趋势指标完整性",
            "通过" if has_trend and numeric_count >= 30 else "待补充",
            f"同比/环比字段识别={has_trend}，数值单元格约 {numeric_count} 个。",
            "若需形成趋势判断，应补充同比、环比、累计同比和份额变化。",
        ),
        SkillCheck(
            "model_rank_data",
            "车型 TOP15 数据",
            "通过" if has_top_model else "待补充",
            f"已识别 {top_model_table_count} 个车型 TOP15 明细表。" if has_top_model else "当前验数表未识别车型 TOP15 明细表。",
            "车型 TOP15 可用于细分市场竞品观察；若无明细，请接入车型销量表。",
        ),
        SkillCheck(
            "brand_concentration",
            "品牌集中度数据",
            "通过" if has_brand else "待补充",
            "已识别品牌或 CR5 相关字段。" if has_brand else "未识别品牌归属、品牌份额或 CR5 集中度字段。",
            "如需输出品牌集中度和 CR5，需接入车型品牌映射及品牌销量汇总表。",
        ),
        SkillCheck(
            "data_scope",
            "数据口径边界",
            "待补充",
            "文件名与表内文字未包含完整的零售/批发/上险口径、区域范围和提取日期说明。",
            "在数据源登记中明确口径、覆盖区域、统计截止日、单位和修订版本。",
        ),
    ]
    return checks


def build_agent_instruction(context: MarketSkillContext) -> str:
    """构造给 MiniMax-M3 的运行时业务约束，避免复制整个业务文档进提示词。"""

    if context.input_gate() == "阻断":
        return build_blocked_prompt(context)

    data_excerpt = build_data_excerpt(context.snapshots)
    source = context.dataset_label or "业务月报数据集"
    checks = "；".join(
        f"{item.name}={item.status}" for item in context.input_checks if item.status != "通过"
    ) or "输入数据门禁通过"
    model_rank_available = any(
        item.check_id == "model_rank_data" and item.status == "通过"
        for item in context.input_checks
    )
    dataset_shape = (
        "按月份 Sheet 的交叉表，已包含车型类别/级别与轿车、SUV、MPV 的 TOP15 车型明细；"
        "未提供完整品牌归属和品牌集中度。"
        if model_rank_available
        else "按月份 Sheet 的展示型交叉表，适合车型类别/级别的同比环比与结构解读；不是完整车型、品牌明细库。"
    )
    return f"""
【已激活业务 Skill：{SKILL_NAME}】
本轮任务是中国乘用车月度/季度市场报告，不使用默认的七章战略问答短模板，改按本 Skill 的月报结构输出。

数据来源与范围：
- 当前数据集：{source}（{relative_display_path(context.dataset_path)}）。
- 数据集形态：{dataset_shape}
- 数据门禁结论：{context.input_gate()}；待补充项：{checks}。

报告写作规则：
1. 以下标题必须逐行、逐字作为独立 Markdown 标题输出，禁止把 2.3/2.4/2.5 合并在一个段落：
   `## 核心数据速览`、`## 01 当月乘用车市场走势解读`、`## 02 当月乘用车市场结构特征分析`、`### 2.1 车型类别`、`### 2.2 车型级别`、`### 2.3 轿车级别分析`、`### 2.4 SUV级别分析`、`### 2.5 MPV级别分析`、`## 03 下月乘用车市场展望`、`## 数据来源与数据缺口`。
   当前数据集总量覆盖轿车、SUV、MPV、交叉型乘用车四类；总量只能按这四类加总，不得写成“狭义乘用车”或静默排除交叉型乘用车。
2. 每个可分析层级先给数据事实，再回答“为什么”和“意味着什么”；“为什么”只能指向表内的同比、环比、份额、级别或已提供的 TOP15 车型，不得补充未给出的能源、产品属性、品牌、渠道、政策或价格原因。不得把销量变化写成“终端总需求主动收缩”“抗周期能力”或“主要拖累”等未做贡献测算的因果判断；可改为“同比降幅最小”“份额上升”“绝对量下降”等表内描述。
3. 每个层级写一段结构小结。TOP15 仅可陈述已注入的车型名称、销量、同比/环比和排名；原始表有完整 TOP15，但摘要只列前三。正文可写“仅引用前三，完整 TOP15 可回溯至原始表”，禁止声称 TOP4-15 缺失、未提供或未注入。若去年同期值不可比，只能写“去年同期无可比值”，不得推断为新车型、上市、改款或进入市场。没有车型排名或品牌集中度明细时，明确写“当前数据集未提供，不生成虚构 TOP15/CR5 结论”。
4. 用户未明确要求实时政策、竞品、新品或新闻时，只基于当前数据集完成报告并披露解释性数据缺口，不调用外部检索工具。用户明确要求实时信息时，所有不来自当前数据集的政策、新品、油价、竞品原因必须调用公开检索工具取得证据；无法取得时标为“待核验假设”。
   当前数据未明示批发/零售/出口/上险口径，不得自行判定；也不得以单月或本年累计数据声称“首次”“连续”等跨期结论。
5. 展望必须列出结论、确定性（高/中/低）、证据和风险变量。不得将推测表述成已验证事实。
6. 文末仅统一标注一次数据来源；正文关键数值必须与下面数据摘要一致。

【已验证数据摘要】
{data_excerpt}
""".strip()


def build_blocked_prompt(context: MarketSkillContext) -> str:
    return """
【市场月报 Skill 数据门禁阻断】
当前未获得可读取的 .xlsx 月报数据。不要输出任何看似精确的销量、同比、份额、TOP 排名或品牌集中度；请列出所需数据字段、统计口径和补数清单，并将所有市场判断标注为待验证。
""".strip()


def build_data_excerpt(sheets: list[SheetSnapshot]) -> str:
    """将展示型工作表压缩为模型可消费的、带工作表出处的文本。"""

    blocks: list[str] = []
    for sheet in sheets[:12]:
        sheet_blocks = extract_sheet_blocks(sheet)
        if sheet_blocks:
            blocks.append(f"### {sheet.name}\n" + "\n".join(sheet_blocks))
    return "\n\n".join(blocks)[:18000] or "未识别到可用的市场结构数据。"


def extract_sheet_blocks(sheet: SheetSnapshot) -> list[str]:
    """从业务验数表中提取“板块 - 年份/同比/环比 - 指标”的可读摘要。"""

    if sheet.row_count < 4:
        return []
    section_row_index = next(
        (index for index, row in enumerate(sheet.rows[:5]) if any(cell in {"车型类别", "车型级别", "轿车-级别", "SUV-级别", "MPV-级别"} for cell in row)),
        0,
    )
    label_row_index = min(section_row_index + 2, sheet.row_count - 1)
    metric_row_indexes = [
        index
        for index, row in enumerate(sheet.rows)
        if row and normalize(row[0]) in {"2025", "2026", "同比", "环比", "份额"}
    ][:8]
    section_starts = [
        index
        for index, value in enumerate(sheet.rows[section_row_index])
        if normalize(value) in {"车型类别", "车型级别", "轿车-级别", "SUV-级别", "MPV-级别"}
    ]
    if not section_starts:
        return []

    blocks: list[str] = []
    for start_position, start_column in enumerate(section_starts):
        end_column = section_starts[start_position + 1] if start_position + 1 < len(section_starts) else sheet.column_count
        title = normalize(sheet.rows[section_row_index][start_column])
        labels = sheet.rows[label_row_index][start_column:end_column]
        metric_lines: list[str] = []
        for row_index in metric_row_indexes:
            row = sheet.rows[row_index]
            metric_name = normalize(row[0])
            pairs: list[str] = []
            for offset, label in enumerate(labels):
                column = start_column + offset
                normalized_label = normalize(label)
                if not normalized_label or normalized_label.startswith("左图") or normalized_label in {"总计", "累计"}:
                    continue
                value = row[column] if column < len(row) else ""
                if not normalize(value):
                    continue
                pairs.append(f"{normalized_label}={format_metric(value, metric_name)}")
            if pairs:
                metric_lines.append(f"- {metric_name}：" + "；".join(pairs))
        if metric_lines:
            blocks.append(f"{title}\n" + "\n".join(metric_lines))
    blocks.extend(extract_top_model_blocks(sheet))
    return blocks


def count_top_model_tables(sheets: list[SheetSnapshot]) -> int:
    """识别“车型、销量、同比、环比”表头组合，不依赖表内是否写有 TOP15 字样。"""

    return sum(
        1
        for sheet in sheets
        for row in sheet.rows
        for column in range(max(0, len(row) - 1))
        if normalize(row[column]) == "车型" and normalize(row[column + 1]) == "销量"
    )


def extract_top_model_blocks(sheet: SheetSnapshot) -> list[str]:
    """提取每个细分市场 TOP15 表的前三车型，供月报正文进行有限竞品观察。"""

    blocks: list[str] = []
    for row_index, row in enumerate(sheet.rows):
        for model_column in range(max(0, len(row) - 1)):
            if normalize(row[model_column]) != "车型" or normalize(row[model_column + 1]) != "销量":
                continue
            segment_column = model_column - 1
            segment = normalize(cell_value(sheet.rows, 0, segment_column)) if segment_column >= 0 else "细分市场"
            items: list[str] = []
            for data_row_index in range(row_index + 1, min(row_index + 16, len(sheet.rows))):
                rank = normalize(cell_value(sheet.rows, data_row_index, segment_column))
                model = normalize(cell_value(sheet.rows, data_row_index, model_column))
                volume = normalize(cell_value(sheet.rows, data_row_index, model_column + 1))
                yoy = normalize(cell_value(sheet.rows, data_row_index, model_column + 2))
                if not rank.isdigit() or not model:
                    break
                item = f"{rank}.{model}={format_metric(volume, '销量')}"
                if yoy:
                    item += f"（同比{format_metric(yoy, '同比')}）"
                items.append(item)
                if len(items) == 3:
                    break
            if items:
                blocks.append(
                    f"{segment} TOP15 车型明细（原始表含第4-15名，本摘要仅列前三）\n- "
                    + "；".join(items),
                )
    return blocks


def cell_value(rows: list[list[str]], row_index: int, column_index: int) -> str:
    """安全读取展示型工作表单元格，空白列和不规则行统一返回空字符串。"""

    if row_index < 0 or column_index < 0 or row_index >= len(rows):
        return ""
    row = rows[row_index]
    return row[column_index] if column_index < len(row) else ""


def format_metric(value: str, metric_name: str) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if metric_name in {"同比", "环比", "份额"}:
        return f"{number * 100:+.1f}%" if metric_name != "份额" else f"{number * 100:.1f}%"
    # 业务验数表中部分销量以“辆”存储，MPV、交叉型等小体量市场常低于 10 万辆。
    # 以 1,000 为阈值统一转为万辆展示，避免 96,054 辆被错误显示成 96054 个表内单位。
    if abs(number) >= 1000:
        return f"{number / 10000:.2f}万辆"
    return f"{number:.3f}（沿用表内单位）"


def validate_generated_report(report: str, context: MarketSkillContext) -> list[SkillCheck]:
    normalized_report = normalize(report)
    missing_sections = [section for section in REPORT_SECTIONS if normalize(section).lower() not in normalized_report.lower()]
    has_source = "数据来源" in normalized_report and any(
        term in normalized_report for term in ("中汽", "终端零售", context.dataset_label, "验数") if term
    )
    has_disclosure = any(term in normalized_report for term in ("待补充", "待核验", "未提供", "数据缺口"))
    has_outlook_confidence = "确定性" in normalized_report and any(term in normalized_report for term in ("高", "中", "低"))
    has_false_top_risk = (
        any(check.check_id == "model_rank_data" and check.status != "通过" for check in context.input_checks)
        and "TOP15" in normalized_report.upper()
        and not has_disclosure
    )
    model_rank_available = any(
        check.check_id == "model_rank_data" and check.status == "通过"
        for check in context.input_checks
    )
    top15_source_mismatch = model_rank_available and find_top15_source_mismatch_claims(report)
    unsupported_attributions = find_unsupported_attribution_sentences(report)
    has_cross_category = any("交叉型乘用车" in sheet.text() for sheet in context.snapshots)
    scope_inconsistent = has_cross_category and "狭义乘用车" in normalized_report

    return [
        SkillCheck(
            "report_structure",
            "月报章节完整性",
            "通过" if not missing_sections else "待补充" if len(missing_sections) <= 3 else "风险",
            "已覆盖固定月报结构。" if not missing_sections else "缺少章节：" + "、".join(missing_sections),
            "补齐核心数据速览、结构分析、展望和数据来源章节后再用于正式月报。",
        ),
        SkillCheck(
            "source_traceability",
            "数据来源可追溯性",
            "通过" if has_source else "待补充",
            "已标注当前数据来源。" if has_source else "未识别到与当前月报数据集对应的数据来源标注。",
            "文末统一标注数据来源、统计口径和提取周期。",
        ),
        SkillCheck(
            "outlook_confidence",
            "展望确定性",
            "通过" if has_outlook_confidence else "待补充",
            "展望包含确定性表达。" if has_outlook_confidence else "展望缺少高/中/低确定性及风险变量。",
            "为总量、轿车、SUV、MPV 和关键变量标注确定性与论据。",
        ),
        SkillCheck(
            "missing_data_disclosure",
            "数据缺口披露",
            "风险" if has_false_top_risk else "通过" if has_disclosure else "待补充",
            "存在基于缺失明细的未披露 TOP15 结论。" if has_false_top_risk else "已披露数据缺口。" if has_disclosure else "未见数据缺口/待核验说明。",
            "没有车型/品牌明细时，不输出具体排名或集中度；改为列出补数需求。",
        ),
        SkillCheck(
            "top15_source_fidelity",
            "TOP15 数据边界一致性",
            "风险" if top15_source_mismatch else "通过",
            (
                "原始表含完整 TOP15，报告却写为：" + "、".join(top15_source_mismatch)
                if top15_source_mismatch
                else "车型明细引用范围与原始表一致。"
            ),
            "正文可仅引用前三，但应注明完整 TOP15 可回溯至原始表，不得把摘要范围误写为数据缺失。",
        ),
        SkillCheck(
            "evidence_boundary",
            "解释性证据边界",
            "风险" if unsupported_attributions else "通过",
            (
                "发现未由当前验数表支撑的归因：" + "、".join(unsupported_attributions)
                if unsupported_attributions
                else "结构解读未发现未披露的外部归因。"
            ),
            "将该类原因改写为销量/份额结构描述，或单独标注为待核验假设并补充外部证据。",
        ),
        SkillCheck(
            "scope_consistency",
            "车型范围一致性",
            "风险" if scope_inconsistent else "通过",
            "数据集包含交叉型乘用车，但报告将总量写为狭义乘用车。" if scope_inconsistent else "总量口径与当前四类车型范围一致。",
            "总量统一按轿车、SUV、MPV、交叉型乘用车四类加总，并在正文保持同一口径。",
        ),
    ]


def find_unsupported_attribution_sentences(report: str) -> list[str]:
    """找出未做证据披露的能源、渠道、政策等外部归因关键词。"""

    violations: list[str] = []
    for sentence in re.split(r"(?<=[。！？])", normalize(report)):
        if not sentence or any(marker in sentence for marker in ATTRIBUTION_DISCLOSURE_TERMS):
            continue
        for term in UNSUPPORTED_ATTRIBUTION_TERMS:
            if term in sentence and term not in violations:
                violations.append(term)
    return violations


def find_top15_source_mismatch_claims(report: str) -> list[str]:
    """防止把“摘要仅列前三”误写成原始 TOP15 数据缺失。"""

    normalized_report = re.sub(r"\s+", "", normalize(report)).upper()
    patterns = (
        r"TOP4[-—–至到]15(?:排名|排名信息)?(?:缺失|未提供|未注入|没有)",
        r"第4[-—–至到]15名(?:缺失|未提供|未注入|没有)",
        r"(?:完整)?TOP15(?:排名|排名信息|明细)?(?:缺失|未提供|未注入|没有)",
    )
    return [pattern for pattern in patterns if re.search(pattern, normalized_report)]


def normalize_top15_summary_wording(report: str, context: MarketSkillContext) -> tuple[str, list[str]]:
    """仅修正摘要范围的误披露，不改写任何销量、同比或业务判断。"""

    model_rank_available = any(
        check.check_id == "model_rank_data" and check.status == "通过"
        for check in context.input_checks
    )
    if not model_rank_available:
        return report, []

    full_sentence = re.compile(
        r"摘要\s*仅列前三\s*[，,；;]?\s*(?:TOP\s*)?4\s*[-—–至到]\s*15\s*"
        r"(?:排名|排名信息)?\s*(?:未注入|缺失|未提供|没有)"
        r"(?:\s*[，,；;]\s*不生成虚构结论)?[。.]?",
        re.IGNORECASE,
    )
    compact_phrase = re.compile(
        r"(?:TOP\s*)?4\s*[-—–至到]\s*15\s*(?:排名|排名信息)?\s*"
        r"(?:未注入|缺失|未提供|没有)",
        re.IGNORECASE,
    )
    normalized_report, full_count = full_sentence.subn(
        "正文仅引用前三，完整 TOP15 可回溯至原始表。",
        report,
    )
    normalized_report, phrase_count = compact_phrase.subn(
        "完整 TOP15 可回溯至原始表",
        normalized_report,
    )
    if not full_count and not phrase_count:
        return report, []

    return normalized_report, ["已将 TOP15 摘要范围误披露修正为可回溯原始表的表述。"]


def calculate_gate(checks: list[SkillCheck]) -> str:
    if any(item.status == "阻断" for item in checks):
        return "阻断"
    if any(item.status == "风险" for item in checks):
        return "风险"
    if any(item.status == "待补充" for item in checks):
        return "待补充"
    return "通过"


def gate_event_status(gate: str) -> str:
    return {"通过": "success", "待补充": "warning", "风险": "warning", "阻断": "blocked"}.get(gate, "success")


def summarize_checks(checks: list[SkillCheck]) -> str:
    summary = [f"{item.name}={item.status}" for item in checks]
    return "；".join(summary)[:360] or "未执行检查。"


def normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def relative_display_path(path: Path | None) -> str:
    if not path:
        return ""
    try:
        return str(path.relative_to(PROJECT_DIR)).replace("\\", "/")
    except ValueError:
        return str(path)
