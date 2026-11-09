"""深度调研报告独立验收规则（deep-research Skill / MKT-002）。

输入为 Markdown 报告全文，输出失败项列表（空列表 = 通过）。
校验规则与 skills/deep-research/assets/report-contract.json 对齐：
1. 必需章节存在（结论摘要、参考来源）
2. 参考来源清单非空且每条含 URL
3. 正文 [cite:N] 全部可解析到来源清单（无虚构引用）
4. 无空引用占位（[cite:]、[cite:abc] 等）
纯确定性校验，不依赖模型；供 scripts/validate_report.py 与单测共用。
"""
from __future__ import annotations

import re

REQUIRED_SECTIONS = ("结论摘要", "参考来源")
MIN_REPORT_CHARS = 300

_CITE_PATTERN = re.compile(r"\[cite:([0-9]+)\]")
_CITE_BAD_PATTERN = re.compile(r"\[cite:\s*[^0-9\]]*\]")
_SOURCE_ENTRY_PATTERN = re.compile(r"^\s*(\d{1,3})[.、]\s*(.+)$", re.MULTILINE)
_URL_PATTERN = re.compile(r"https?://[^\s）)】]+")
_SECTION_PATTERN = re.compile(r"^#{1,6}\s*(.+?)\s*$", re.MULTILINE)


def _find_section_body(text: str, title: str) -> str:
    """取指定标题章节的正文（到下一个同级或更高级标题为止）。"""
    pattern = re.compile(
        r"^#{1,6}\s*.*?" + re.escape(title) + r".*?$", re.MULTILINE
    )
    match = pattern.search(text)
    if not match:
        return ""
    rest = text[match.end():]
    next_heading = re.search(r"^#{1,6}\s+", rest, re.MULTILINE)
    return rest[: next_heading.start()] if next_heading else rest


def validate_research_report(text: str) -> list[str]:
    text = text or ""
    failures: list[str] = []

    if len(text.strip()) < MIN_REPORT_CHARS:
        failures.append(f"报告正文过短（{len(text.strip())} 字符，最少 {MIN_REPORT_CHARS}），疑似空交付物。")
        return failures

    # 1. 必需章节
    headings = [item.strip() for item in _SECTION_PATTERN.findall(text)]
    for section in REQUIRED_SECTIONS:
        if not any(section in heading for heading in headings):
            failures.append(f"缺少必需章节：{section}")

    # 2. 参考来源清单
    source_body = _find_section_body(text, "参考来源")
    source_numbers: set[int] = set()
    if not source_body.strip():
        failures.append("「参考来源」章节为空。")
    else:
        for match in _SOURCE_ENTRY_PATTERN.finditer(source_body):
            number = int(match.group(1))
            entry = match.group(2)
            source_numbers.add(number)
            if not _URL_PATTERN.search(entry):
                failures.append(f"参考来源 {number} 缺少 URL：{entry[:60]}")
        if not source_numbers:
            failures.append("「参考来源」未解析到任何编号条目（格式：N. 标题 — URL）。")
        elif sorted(source_numbers) != list(range(1, len(source_numbers) + 1)):
            failures.append("参考来源编号不连续，应从 1 开始连续编号。")

    # 3. 引用可解析
    cited = {int(item) for item in _CITE_PATTERN.findall(text)}
    invalid_cites = sorted(cited - source_numbers)
    if invalid_cites:
        failures.append(f"正文引用 [cite:...] 指向不存在的来源编号：{invalid_cites}（虚构引用）。")

    # 4. 空引用占位
    bad_cites = _CITE_BAD_PATTERN.findall(text)
    if bad_cites:
        failures.append(f"存在空引用占位：{bad_cites[:5]}")

    if source_numbers and not cited:
        failures.append("参考来源存在但正文没有任何 [cite:N] 引用，来源与结论未挂钩。")

    return failures
