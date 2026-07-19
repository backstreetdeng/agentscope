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

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from skills.agent_reach.adapter import EvidenceItem, search as agent_reach_search


SKILL_NAME = "china-passenger-vehicle-market-analysis"
SKILL_VERSION = "1.1.0"
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
)
STATISTICAL_SCOPE_TERMS = ("批发", "零售", "出口", "上险")
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


@dataclass(frozen=True)
class TopModelEvidence:
    """TOP15 中一条已统一为“万辆”口径的车型数据。"""

    segment: str
    rank: int
    name: str
    volume: float | None
    yoy: float | None
    mom: float | None
    level: str
    share: float | None
    rank_change: str
    cumulative_volume: float | None

    @property
    def yoy_delta(self) -> float | None:
        """由本期销量与同比反推的估算增减量，仅用于筛选代表车型。"""

        if self.volume is None or self.yoy is None or self.yoy <= -0.99:
            return None
        return self.volume - self.volume / (1 + self.yoy)


@dataclass(frozen=True)
class DriverSignal:
    """由 TOP15 计算出的代表车型信号，不把相关性伪装成外部因果。"""

    segment: str
    model: TopModelEvidence
    signal_type: str

    def as_dict(self) -> dict[str, str]:
        return {
            "segment": self.segment,
            "model": self.model.name,
            "signal_type": self.signal_type,
            "volume": format_volume_wan(self.model.volume),
            "yoy": format_percent(self.model.yoy),
            "mom": format_percent(self.model.mom),
            "estimated_delta": format_volume_wan(self.model.yoy_delta),
        }

    def to_prompt_line(self) -> str:
        metric = (
            f"本月{format_volume_wan(self.model.volume)}、同比{format_percent(self.model.yoy)}、"
            f"环比{format_percent(self.model.mom)}、排名变化{self.model.rank_change or '-'}"
        )
        if self.model.yoy_delta is not None:
            metric += f"、估算同比增减量{format_volume_wan(self.model.yoy_delta)}"
        return f"{self.segment} / {self.signal_type}：{self.model.name}（{metric}）"


@dataclass(frozen=True)
class ExternalEvidence:
    """经 Agent Reach 采集并编号后的外部证据。"""

    evidence_id: str
    item: EvidenceItem
    focus: str

    def as_dict(self) -> dict[str, str]:
        return {
            "id": self.evidence_id,
            "focus": self.focus,
            **self.item.as_dict(),
        }

    def to_prompt_block(self) -> str:
        published = f"；发布日期={self.item.published}" if self.item.published else ""
        return (
            f"{self.evidence_id}（{self.item.source_tier}级；用途={self.focus}{published}）\n"
            f"来源：{self.item.title}\nURL：{self.item.url}\n"
            f"摘要：{self.item.highlights[:700] or '未返回摘要'}"
        )


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
    top_model_records: list[TopModelEvidence] = field(default_factory=list)
    driver_signals: list[DriverSignal] = field(default_factory=list)
    external_evidence: list[ExternalEvidence] = field(default_factory=list)
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
            "deep_analysis": {
                "top_model_count": len(self.top_model_records),
                "driver_candidates": [item.as_dict() for item in self.driver_signals],
                "external_evidence": [item.as_dict() for item in self.external_evidence],
            },
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
        include_external_evidence: bool = False,
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

        selected, selection_note = select_report_sheet(context.snapshots, question, sheet_name)
        if selected is None:
            context.input_checks.append(
                SkillCheck(
                    "selected_sheet",
                    "指定工作表",
                    "阻断",
                    selection_note,
                    "传入 Excel 中真实存在的工作表名称，例如“4月”。",
                ),
            )
            context.events.append(SkillEvent("sheet-select", "blocked", selection_note))
            context.prompt_context = build_blocked_prompt(context)
            return context
        context.snapshots = [selected]
        context.selected_sheet = selected.name
        context.dataset_label = f"{source_label} / 工作表={selected.name}"
        context.events.append(SkillEvent("sheet-select", "success", selection_note))

        context.input_checks = validate_input_dataset(context.snapshots, source)
        context.top_model_records = extract_top_model_records(selected)
        context.driver_signals = select_driver_signals(context.top_model_records)
        context.events.extend(
            [
                SkillEvent("dataset-resolve", "success", f"数据集={source.name}；工作表={len(context.snapshots)} 个。"),
                SkillEvent("data-gate", gate_event_status(context.input_gate()), summarize_checks(context.input_checks)),
                SkillEvent(
                    "top15-parse",
                    "success" if context.top_model_records else "warning",
                    (
                        f"已解析完整 TOP15 明细 {len(context.top_model_records)} 条，并统一销量为万辆。"
                        if context.top_model_records
                        else "当前工作表未解析到可用 TOP15 明细。"
                    ),
                ),
                SkillEvent(
                    "driver-select",
                    "success" if context.driver_signals else "warning",
                    (
                        "已选出代表车型信号：" + "、".join(item.model.name for item in context.driver_signals[:8])
                        if context.driver_signals
                        else "未形成可比同期的代表车型信号，仅保留数据描述。"
                    ),
                ),
            ],
        )
        if include_external_evidence and self._external_evidence_enabled():
            context.external_evidence = collect_external_evidence(context, self._external_evidence_settings())
        else:
            reason = "预检或PPT生成不执行外部检索。" if not include_external_evidence else "配置未启用外部证据采集。"
            context.events.append(SkillEvent("evidence-search", "skipped", reason))
        context.events.append(SkillEvent("context-build", "success", "已生成含数据、车型贡献与证据边界的月报写作上下文。"))
        context.prompt_context = build_agent_instruction(context)
        return context

    def _external_evidence_settings(self) -> dict[str, Any]:
        return dict(self.settings.get("external_evidence", {}))

    def _external_evidence_enabled(self) -> bool:
        return bool(self._external_evidence_settings().get("enabled", False))

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


def select_report_sheet(
    sheets: list[SheetSnapshot],
    question: str,
    requested_sheet: str | None,
) -> tuple[SheetSnapshot | None, str]:
    """确定本轮月报唯一使用的 Sheet，避免跨月数据混写。

    显式参数优先；其次识别问题中的“X月”；最后选择工作簿内最新月份。每次只向
    模型注入一个月度快照，历史 Sheet 仍保留在原始文件中供后续指定调用。
    """

    requested = normalize(requested_sheet)
    if requested:
        target = requested.lower()
        selected = next((sheet for sheet in sheets if normalize(sheet.name).lower() == target), None)
        if selected is None:
            return None, f"未找到工作表：{requested}。可用工作表：" + "、".join(sheet.name for sheet in sheets)
        return selected, f"已按调用参数选择工作表：{selected.name}。"

    question_months = re.findall(r"(?<!\d)(1[0-2]|[1-9])月", normalize(question))
    if question_months:
        target = f"{int(question_months[-1])}月"
        selected = next((sheet for sheet in sheets if normalize(sheet.name) == target), None)
        if selected is not None:
            return selected, f"已从任务问题识别并选择工作表：{selected.name}。"

    selected = max(sheets, key=sheet_month_number, default=None)
    if selected is None:
        return None, "工作簿中没有可用于月报的工作表。"
    return selected, f"任务未指定月份，已选择最新工作表：{selected.name}。"


def sheet_month_number(sheet: SheetSnapshot) -> int:
    match = re.search(r"(1[0-2]|[1-9])月", normalize(sheet.name))
    return int(match.group(1)) if match else 0


def extract_top_model_records(sheet: SheetSnapshot) -> list[TopModelEvidence]:
    """读取轿车、SUV、MPV 的完整 TOP15 并统一销量/累计销量为万辆。"""

    records: list[TopModelEvidence] = []
    rows = sheet.rows
    for header_row, row in enumerate(rows):
        for model_column in range(max(0, len(row) - 1)):
            if normalize(row[model_column]) != "车型" or normalize(row[model_column + 1]) != "销量":
                continue
            rank_column = model_column - 1
            segment = normalize(cell_value(rows, 0, rank_column)) if rank_column >= 0 else "细分市场"
            if not segment:
                segment = "细分市场"
            for data_row in range(header_row + 1, min(header_row + 16, len(rows))):
                rank_text = normalize(cell_value(rows, data_row, rank_column))
                name = normalize(cell_value(rows, data_row, model_column))
                if not rank_text.isdigit() or not name:
                    break
                records.append(
                    TopModelEvidence(
                        segment=segment,
                        rank=int(rank_text),
                        name=name,
                        volume=normalize_sales_to_wan(to_number(cell_value(rows, data_row, model_column + 1))),
                        yoy=to_number(cell_value(rows, data_row, model_column + 2)),
                        mom=to_number(cell_value(rows, data_row, model_column + 3)),
                        level=normalize(cell_value(rows, data_row, model_column + 4)),
                        share=to_number(cell_value(rows, data_row, model_column + 5)),
                        rank_change=format_rank_change(cell_value(rows, data_row, model_column + 6)),
                        cumulative_volume=normalize_sales_to_wan(to_number(cell_value(rows, data_row, model_column + 7))),
                    ),
                )
    return records


def select_driver_signals(records: list[TopModelEvidence]) -> list[DriverSignal]:
    """按同比估算增减量、排名异动筛选每个细分市场的代表车型。

    该步骤只回答“哪些车型与市场变化同步、值得解释”，不把车型变化直接写成政策、
    产品换代或消费者动机等外部因果。
    """

    result: list[DriverSignal] = []
    segments = sorted({item.segment for item in records})
    for segment in segments:
        segment_records = [item for item in records if item.segment == segment]
        comparable = [item for item in segment_records if item.yoy_delta is not None]
        selected_names: set[str] = set()
        for model in sorted(comparable, key=lambda item: item.yoy_delta or 0)[:3]:
            if (model.yoy_delta or 0) < 0:
                result.append(DriverSignal(segment, model, "同比减量候选"))
                selected_names.add(model.name)
        for model in sorted(comparable, key=lambda item: item.yoy_delta or 0, reverse=True)[:1]:
            if (model.yoy_delta or 0) > 0 and model.name not in selected_names:
                result.append(DriverSignal(segment, model, "同比增量候选"))
                selected_names.add(model.name)
        for model in segment_records:
            if model.name in selected_names or abs(rank_change_number(model.rank_change)) < 5:
                continue
            result.append(DriverSignal(segment, model, "排名异动候选"))
            selected_names.add(model.name)
            break
    return result


def collect_external_evidence(context: MarketSkillContext, settings: dict[str, Any]) -> list[ExternalEvidence]:
    """按“宏观一条 + 细分市场三条”定向检索，并把来源固化为报告证据包。"""

    query_plan = build_evidence_query_plan(context, settings)
    if not query_plan:
        context.events.append(SkillEvent("evidence-plan", "warning", "未形成可执行的外部证据检索计划。"))
        return []

    max_results = max(1, min(int(settings.get("max_results_per_query", 3)), 5))
    timeout_seconds = max(10, min(int(settings.get("timeout_seconds", 35)), 60))
    max_items = max(1, min(int(settings.get("max_evidence_items", 8)), 12))
    per_focus_limit = max(1, min(max_results, max_items // len(query_plan)))
    context.events.append(
        SkillEvent(
            "evidence-plan",
            "running",
            "已生成定向检索计划：" + "；".join(focus for focus, _ in query_plan),
        ),
    )

    responses: dict[int, tuple[str, str, Any]] = {}
    with ThreadPoolExecutor(max_workers=min(4, len(query_plan))) as executor:
        future_map = {
            executor.submit(agent_reach_search, query, max_results, timeout_seconds): (index, focus, query)
            for index, (focus, query) in enumerate(query_plan)
        }
        for future in as_completed(future_map):
            index, focus, query = future_map[future]
            try:
                responses[index] = (focus, query, future.result())
            except Exception as exc:  # 防御第三方 CLI 异常，月报可降级为仅内部数据。
                responses[index] = (focus, query, exc)

    evidence: list[ExternalEvidence] = []
    seen_urls: set[str] = set()
    for index in sorted(responses):
        focus, query, response = responses[index]
        if isinstance(response, Exception) or not response.ok:
            fallback_query = build_fallback_evidence_query(context, focus)
            fallback = agent_reach_search(fallback_query, max_results, timeout_seconds)
            if fallback.ok:
                response = fallback
                context.events.append(SkillEvent("evidence-search", "success", f"{focus}首轮未命中，已通过行业级回退查询获取来源。"))
            else:
                reason = type(response).__name__ if isinstance(response, Exception) else response.error[:160]
                context.events.append(SkillEvent("evidence-search", "warning", f"{focus}未获取证据：{reason}"))
                continue
        usable = 0
        for item in response.items:
            if item.url in seen_urls or len(evidence) >= max_items or usable >= per_focus_limit:
                continue
            seen_urls.add(item.url)
            evidence.append(ExternalEvidence(f"E{len(evidence) + 1}", item, focus))
            usable += 1
        context.events.append(
            SkillEvent(
                "evidence-search",
                "success" if usable else "warning",
                f"{focus}：检索到 {len(response.items)} 条，纳入 {usable} 条可追溯来源。",
            ),
        )
    context.events.append(
        SkillEvent(
            "evidence-gate",
            "success" if evidence else "warning",
            f"外部证据包共 {len(evidence)} 条；仅可对带编号来源形成外部归因。",
        ),
    )
    return evidence


def build_evidence_query_plan(context: MarketSkillContext, settings: dict[str, Any]) -> list[tuple[str, str]]:
    """避免泛搜：每个查询都由当月、细分市场和代表车型共同约束。"""

    if not context.snapshots:
        return []
    sheet = context.snapshots[0]
    period = infer_report_period(sheet, context.question)
    plans: list[tuple[str, str]] = [
        (
            "行业宏观背景",
            f"{period} 中国乘用车市场终端表现 高油价 政策 促销 高基数 行业分析",
        ),
    ]
    for segment in ("轿车-级别", "SUV-级别", "MPV-级别"):
        names = [item.model.name for item in context.driver_signals if item.segment == segment][:3]
        if not names:
            continue
        display_segment = segment.replace("-级别", "")
        plans.append(
            (
                f"{display_segment}代表车型",
                f"{period} 中国 {display_segment} {' '.join(names)} 上市 改款 促销 交付 市场表现",
            ),
        )
    max_queries = max(1, min(int(settings.get("max_queries", 4)), 4))
    return plans[:max_queries]


def build_fallback_evidence_query(context: MarketSkillContext, focus: str) -> str:
    """车型组合检索失败时，退回到同月份、同细分市场的专业月度分析。"""

    period = infer_report_period(context.snapshots[0], context.question) if context.snapshots else "中国乘用车市场"
    segment = focus.replace("代表车型", "").replace("行业宏观背景", "乘用车")
    return f"{period} 中国 {segment} 市场 月度分析 行业报告"


def infer_report_period(sheet: SheetSnapshot, question: str) -> str:
    year_match = re.search(r"(20\d{2})年", normalize(question))
    if not year_match:
        for row in sheet.rows[:12]:
            for value in row[:3]:
                match = re.fullmatch(r"20\d{2}", normalize(value))
                if match:
                    year_match = match
                    break
            if year_match:
                break
    year = year_match.group(1) if year_match else str(datetime.now().year)
    return f"{year}年{sheet_month_number(sheet)}月"


def to_number(value: str) -> float | None:
    text = normalize(value)
    if not text or text.startswith("#"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def normalize_sales_to_wan(value: float | None) -> float | None:
    """兼容历史 Sheet 的“辆”和统一后的“万辆”，统一返回万辆。"""

    if value is None:
        return None
    return value / 10000 if abs(value) >= 1000 else value


def format_percent(value: float | None) -> str:
    return "无可比" if value is None else f"{value * 100:+.1f}%"


def format_volume_wan(value: float | None) -> str:
    return "-" if value is None else f"{value:+.2f}万辆" if value < 0 else f"{value:.2f}万辆"


def format_rank_change(value: str) -> str:
    text = normalize(value)
    if not text or text == "0":
        return "-"
    return text if text.startswith(("+", "-")) else f"+{text}"


def rank_change_number(value: str) -> int:
    try:
        return int(float(normalize(value)))
    except ValueError:
        return 0


def build_driver_context(signals: list[DriverSignal]) -> str:
    if not signals:
        return "未形成可比同期的代表车型信号；不得用车型名称补造原因。"
    return "\n".join("- " + signal.to_prompt_line() for signal in signals[:15])


def build_external_evidence_context(evidence: list[ExternalEvidence]) -> str:
    if not evidence:
        return "本轮未取得外部证据。政策、油价、促销、上市、产品换代、渠道等原因只能标为待核验，不得写成事实。"
    return "\n\n".join(item.to_prompt_block() for item in evidence)


def build_agent_instruction(context: MarketSkillContext) -> str:
    """构造给 MiniMax-M3 的运行时业务约束，避免复制整个业务文档进提示词。"""

    if context.input_gate() == "阻断":
        return build_blocked_prompt(context)

    data_excerpt = build_data_excerpt(context.snapshots)
    source = context.dataset_label or "业务月报数据集"
    driver_context = build_driver_context(context.driver_signals)
    evidence_context = build_external_evidence_context(context.external_evidence)
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
2. 每个“市场深度分析”必须按“总体判断 -> 代表车型贡献 -> 外部或结构解释 -> 业务含义”组织，不得逐项复述四类销量。优先从【代表车型贡献信号】中选择 2-3 个车型；同比增减量是由销量与同比反推的筛选量，写作中表述为“TOP15样本内估算减量/增量”，不得扩大为全市场精确贡献。
3. 完整 TOP15 已注入，包含车型、销量、同比、环比、级别、份额、排名变化、累计销量。不得再写“TOP4-15缺失/未注入”。若去年同期无可比，只能写“去年同期无可比值”，不得自行推断为新车型、上市、改款或进入市场。没有品牌归属/CR5 数据时，明确披露“当前数据集未提供，不生成品牌集中度结论”。
4. 政策、油价、促销、上市、产品换代、渠道、出口、产品生命周期等外部原因，仅能使用【外部证据包】中与该句匹配的来源。每个外部归因句末必须严格标注 `〔E1〕`；多条来源写成 `〔E1〕〔E2〕`，禁止写 `〔E1,E2〕` 或把“C级线索”等文字放进编号。A/B级来源可作为归因依据；C级来源只能写成“待核验行业线索（〔E7〕）”，不能单独支撑“主要受/核心驱动”等强因果。无匹配来源时改写为内部数据描述或“待核验假设”。不得以外部资料覆盖或改写当前中汽数据验数表的核心销量。
   当前数据未明示批发/零售/出口/上险口径，不得自行判定；也不得以单月或本年累计数据声称“首次”“连续”等跨期结论。
5. 展望必须列出结论、确定性（高/中/低）、证据和风险变量。不得将推测表述成已验证事实。
6. `### 2.1` 至 `### 2.5` 的每个章节第一段必须以 `◼` 开头，且控制在 120-200 个中文字符，采用“[月份]，[总体判断]；TOP15样本内[代表车型]变化；[外部证据或待核验说明]；[业务含义]”的咨询式句型。该首段是 PPT 直接使用的“市场深度分析”，禁止罗列全部销量、同比、环比。详细数据和补充说明可另起段。
7. 文末仅统一标注一次内部数据来源；如使用外部归因，在“数据来源与数据缺口”中追加“外部证据索引”，列出已使用的 E 编号、标题、URL、发布日期和用途。正文关键数值必须与下面数据摘要一致。

【已验证数据摘要】
{data_excerpt}

【代表车型贡献信号】
{driver_context}

【外部证据包】
{evidence_context}
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
    """把完整 TOP15 以稳定字段顺序写入模型上下文，杜绝“仅前三”信息截断。"""

    grouped: dict[str, list[TopModelEvidence]] = {}
    for record in extract_top_model_records(sheet):
        grouped.setdefault(record.segment, []).append(record)
    blocks: list[str] = []
    for segment, records in grouped.items():
        lines = []
        for item in records:
            lines.append(
                f"{item.rank}.{item.name}｜销量{format_volume_wan(item.volume)}｜同比{format_percent(item.yoy)}"
                f"｜环比{format_percent(item.mom)}｜级别{item.level or '-'}｜份额{format_percent(item.share)}"
                f"｜排名变化{item.rank_change or '-'}｜累计{format_volume_wan(item.cumulative_volume)}",
            )
        if lines:
            blocks.append(f"{segment} TOP15 车型明细（完整15名，销量统一为万辆）\n- " + "\n- ".join(lines))
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
    unsupported_attributions = find_unsupported_attribution_sentences(report, context)
    invalid_evidence_references = find_invalid_evidence_references(report, context)
    malformed_evidence_markers = find_malformed_evidence_markers(report)
    weak_evidence_claims = find_weak_evidence_claims(report, context)
    unmeasured_contribution_claims = find_unmeasured_contribution_claims(report, context)
    shallow_sections = find_shallow_deep_analysis_sections(report)
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
            "风险" if unsupported_attributions or unmeasured_contribution_claims or weak_evidence_claims else "通过",
            (
                "发现未由当前验数表或证据编号支撑的归因："
                + "、".join(unsupported_attributions + unmeasured_contribution_claims + weak_evidence_claims)
                if unsupported_attributions or unmeasured_contribution_claims or weak_evidence_claims
                else "结构解读未发现未披露的外部归因。"
            ),
            "将该类原因改写为销量/份额结构描述；若使用外部原因，补充匹配的〔E编号〕；若称“主要拖累”，必须点明已计算的代表车型。",
        ),
        SkillCheck(
            "ppt_deep_analysis",
            "PPT市场深度分析可用性",
            "风险" if shallow_sections else "通过",
            (
                "以下章节缺少以◼开头、可直接用于PPT的120-200字深度分析首段：" + "、".join(shallow_sections)
                if shallow_sections
                else "五个结构章节均包含可直接进入PPT的深度分析首段。"
            ),
            "每个2.1-2.5章节首段按“总体判断-代表车型贡献-证据/待核验-业务含义”重写，避免逐项数据罗列。",
        ),
        SkillCheck(
            "external_evidence_traceability",
            "外部证据编号可追溯性",
            "风险" if invalid_evidence_references or malformed_evidence_markers else "通过",
            (
                "；".join(
                    part
                    for part in (
                        "报告引用了不存在的证据编号：" + "、".join(invalid_evidence_references)
                        if invalid_evidence_references
                        else "",
                        "证据编号格式不符合逐个标注要求：" + "、".join(malformed_evidence_markers)
                        if malformed_evidence_markers
                        else "",
                    )
                    if part
                )
                if invalid_evidence_references or malformed_evidence_markers
                else ("外部归因编号均可回溯至本轮证据包。" if context.external_evidence else "本轮未使用外部证据编号。")
            ),
            "仅引用本轮证据包中实际存在的〔E编号〕，并在“数据来源与数据缺口”中列出来源索引。",
        ),
        SkillCheck(
            "scope_consistency",
            "车型范围一致性",
            "风险" if scope_inconsistent else "通过",
            "数据集包含交叉型乘用车，但报告将总量写为狭义乘用车。" if scope_inconsistent else "总量口径与当前四类车型范围一致。",
            "总量统一按轿车、SUV、MPV、交叉型乘用车四类加总，并在正文保持同一口径。",
        ),
    ]


def find_unsupported_attribution_sentences(report: str, context: MarketSkillContext) -> list[str]:
    """找出缺少有效〔E编号〕的外部归因，保留数据范围硬约束。"""

    violations: list[str] = []
    valid_evidence_ids = {item.evidence_id for item in context.external_evidence}
    for sentence in re.split(r"(?<=[。！？])", report_before_evidence_index(report)):
        if not sentence or any(marker in sentence for marker in ATTRIBUTION_DISCLOSURE_TERMS):
            continue
        evidence_ids = evidence_ids_in_text(sentence)
        for term in UNSUPPORTED_ATTRIBUTION_TERMS:
            if term in sentence and not (evidence_ids and evidence_ids.issubset(valid_evidence_ids)) and term not in violations:
                violations.append(term)
        # “本报告/当前数据/验数表”主动声明成批发、零售、出口、上险口径属于硬错误；
        # 外部证据索引中出现这些词不等同于篡改本地数据口径，因此不做全词拦截。
        if re.search(r"(?:本报告|当前数据|验数表|本月销量|报告数据).{0,12}(?:批发|零售|出口|上险)", sentence):
            for term in STATISTICAL_SCOPE_TERMS:
                if term in sentence and term not in violations:
                    violations.append(term)
    return violations


def find_invalid_evidence_references(report: str, context: MarketSkillContext) -> list[str]:
    valid_ids = {item.evidence_id for item in context.external_evidence}
    referenced_ids = evidence_ids_in_text(report_before_evidence_index(report))
    return sorted(referenced_ids - valid_ids)


def find_malformed_evidence_markers(report: str) -> list[str]:
    """外部证据必须逐个写为〔E1〕，避免一个括号混入多个来源或说明文字。"""

    malformed: list[str] = []
    for marker in re.findall(r"〔([^〕]+)〕", report_before_evidence_index(report)):
        compact = normalize(marker).replace(" ", "")
        if "E" in compact and not re.fullmatch(r"E\d+", compact):
            malformed.append(f"〔{compact}〕")
    return list(dict.fromkeys(malformed))


def find_weak_evidence_claims(report: str, context: MarketSkillContext) -> list[str]:
    """C级媒体线索不能单独承载“主要原因/核心驱动”类强因果。"""

    tiers = {item.evidence_id: item.item.source_tier for item in context.external_evidence}
    violations: list[str] = []
    for sentence in re.split(r"(?<=[。！？])", report_before_evidence_index(report)):
        evidence_ids = evidence_ids_in_text(sentence)
        if not evidence_ids or not any(term in sentence for term in ("主要受", "核心驱动", "核心解释", "导致")):
            continue
        if all(tiers.get(item) == "C" for item in evidence_ids):
            violations.append("C级线索被单独用于强因果")
    return violations


def evidence_ids_in_text(text: str) -> set[str]:
    """兼容模型偶发写出的〔E1,E2〕，同时可校验其中的未知编号。"""

    return set(re.findall(r"E\d+", " ".join(re.findall(r"〔([^〕]+)〕", text or ""))))


def report_before_evidence_index(report: str) -> str:
    """外部证据索引是元数据，不参与正文归因句的语义门禁。"""

    return re.split(r"(?:外部证据索引|##\s*数据来源与数据缺口)", report or "", maxsplit=1)[0]


def find_shallow_deep_analysis_sections(report: str) -> list[str]:
    """检查五页PPT对应章节是否已有可复用的咨询式首段。"""

    missing: list[str] = []
    for section in ("2.1 车型类别", "2.2 车型级别", "2.3 轿车级别分析", "2.4 SUV级别分析", "2.5 MPV级别分析"):
        pattern = re.compile(
            # 标题文字必须以业务规定的章节名开始；允许模型在同一行附加“（含义）”
            # 等非结构化说明，避免把可用的正文误判为缺失。
            rf"(?ms)^###\s*{re.escape(section)}[^\n]*\n(?P<body>.*?)(?=^###?\s+|\Z)",
        )
        match = pattern.search(report or "")
        body = match.group("body").strip() if match else ""
        first_paragraph = re.split(r"\n\s*\n", body, maxsplit=1)[0].strip()
        if not first_paragraph.startswith("◼") or not 80 <= len(normalize(first_paragraph)) <= 240:
            missing.append(section)
    return missing


def normalize_external_evidence_marker_format(
    report: str,
    context: MarketSkillContext,
) -> tuple[str, list[str]]:
    """将可验证的组合证据编号规范为逐个编号，不改动业务语句或未知编号。

    模型偶尔会把多条来源写成 ``〔E1,E2〕``，或把“C级线索”等说明混在同一
    括号中。这些写法不利于逐条审计，但其中已列出的编号本身仍可验证；因此仅当
    编号全部属于本轮证据包时，改写为 ``〔E1〕〔E2〕``。未知编号保留给门禁报错，
    绝不擅自替换成看似正确的来源。
    """

    valid_ids = {item.evidence_id for item in context.external_evidence}
    events: list[str] = []

    def replace_marker(match: re.Match[str]) -> str:
        marker = match.group(1)
        ids = re.findall(r"E\d+", marker)
        if not ids or not all(item in valid_ids for item in ids):
            return match.group(0)
        canonical = "".join(f"〔{item}〕" for item in dict.fromkeys(ids))
        if canonical != match.group(0):
            events.append(f"已将外部证据标记“〔{marker}〕”规范为“{canonical}”。")
        return canonical

    return re.sub(r"〔([^〕]+)〕", replace_marker, report or ""), events


def find_unmeasured_contribution_claims(report: str, context: MarketSkillContext) -> list[str]:
    """“主要拖累/核心拉动”必须能落到本轮贡献计算中的具体车型。"""

    candidate_models = {item.model.name for item in context.driver_signals}
    violations: list[str] = []
    for sentence in re.split(r"(?<=[。！？])", normalize(report)):
        if not sentence or not any(term in sentence for term in ("主要拖累", "核心拉动", "核心驱动")):
            continue
        if not any(model in sentence for model in candidate_models):
            violations.append("主要拖累/拉动未对应代表车型")
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
        r"(?:TOP\s*15\s*)?摘要\s*仅列前三\s*[，,；;]?\s*(?:TOP\s*)?4\s*[-—–至到]\s*15\s*"
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
        "正文可按需引用代表车型，完整 TOP15 已注入并可回溯至原始表。",
        report,
    )
    normalized_report, phrase_count = compact_phrase.subn(
        "完整 TOP15 已注入并可回溯至原始表",
        normalized_report,
    )
    if not full_count and not phrase_count:
        return report, []

    return normalized_report, ["已将 TOP15 摘要范围误披露修正为完整明细已注入的表述。"]


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
