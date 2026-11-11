"""BCI-007 · 报告 HTML 渲染（单文件、离线可读）。

约束：
- 输出一个自包含 HTML：CSS 内联、无脚本、无外链字体/图片/CDN，断网与内网均可打开；
- 所有动态文本（含深访原话、车型名、备注）统一 `html.escape`，禁止拼接未转义内容；
- 每块都带来源与分母，缺失块显式标注原因，不用 0 或占位数字填充。
"""

from __future__ import annotations

import html
from typing import Any

RENDERER_VERSION = "report-render-html/1.0.4"

_STATUS_LABELS = {
    "ok": "完整",
    "partial": "部分缺失",
    "insufficient": "样本不足",
    "missing": "缺数据",
    "empty": "缺数据",
}

_CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { margin: 0; padding: 32px 40px 64px; background: #f4f5f7; color: #1e2329;
       font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif; line-height: 1.65; }
.page { max-width: 1080px; margin: 0 auto; background: #fff; padding: 40px 48px 56px;
        box-shadow: 0 1px 3px rgba(16, 24, 40, .08); border-radius: 4px; }
h1 { font-size: 26px; margin: 0 0 6px; letter-spacing: .5px; }
h2 { font-size: 19px; margin: 40px 0 4px; padding-left: 10px; border-left: 4px solid #1f5fbf; }
h3 { font-size: 14px; margin: 22px 0 8px; color: #344054; }
h4 { font-size: 13px; margin: 16px 0 6px; color: #475467; }
p { margin: 6px 0; }
.sub { color: #667085; font-size: 13px; margin: 0 0 4px; }
.meta { color: #475467; font-size: 12px; margin-top: 10px; }
.meta span { margin-right: 14px; }
.scope { margin: 14px 0 0; padding: 10px 14px; background: #f8fafc; border: 1px solid #e4e7ec;
         border-radius: 4px; font-size: 12.5px; color: #475467; }
.chips { margin: 10px 0 0; }
.chip { display: inline-block; margin: 0 8px 6px 0; padding: 2px 10px; border-radius: 12px;
        background: #eef4ff; color: #1f5fbf; font-size: 12px; }
.block { border: 1px solid #eaecf0; border-radius: 4px; padding: 14px 16px; margin: 12px 0 18px; }
.block-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px;
              border-bottom: 1px dashed #e4e7ec; padding-bottom: 6px; margin-bottom: 10px; }
.block-title { font-size: 13.5px; font-weight: 600; color: #1e2329; }
.badge { font-size: 11.5px; padding: 1px 8px; border-radius: 10px; background: #ecfdf3; color: #067647;
         white-space: nowrap; }
.badge.partial { background: #fffaeb; color: #b54708; }
.badge.missing, .badge.empty { background: #fef3f2; color: #b42318; }
.badge.insufficient { background: #fef3f2; color: #b42318; }
table { width: 100%; border-collapse: collapse; font-size: 12.5px; margin: 4px 0 8px; }
th, td { border: 1px solid #e4e7ec; padding: 5px 8px; text-align: left; vertical-align: top; }
th { background: #f8fafc; color: #344054; font-weight: 600; white-space: nowrap; }
td.num { text-align: right; }
th.num { text-align: right; white-space: nowrap; }
.note { color: #667085; font-size: 12px; margin: 4px 0 0; }
.bars { margin: 4px 0 2px; }
.bar-row { display: grid; grid-template-columns: 120px 1fr 168px; gap: 8px; align-items: center;
           font-size: 12.5px; margin: 5px 0; }
.bar-label { color: #344054; }
.bar-track { background: #f2f4f7; height: 12px; border-radius: 6px; overflow: hidden; }
.bar-fill { background: #1f5fbf; height: 100%; }
.bar-value { color: #475467; text-align: right; white-space: nowrap; }
.kv { display: flex; flex-wrap: wrap; gap: 10px; }
.kv-item { min-width: 160px; flex: 1 1 180px; border: 1px solid #eaecf0; border-radius: 4px; padding: 8px 10px; }
.kv-label { font-size: 12px; color: #667085; }
.kv-value { font-size: 18px; font-weight: 600; color: #1f5fbf; }
.kv-sub { font-size: 11.5px; color: #98a2b3; }
blockquote { margin: 6px 0; padding: 8px 12px; background: #f9fafb; border-left: 3px solid #d0d5dd;
             font-size: 12.5px; color: #344054; }
blockquote .who { color: #1f5fbf; font-weight: 600; margin-right: 6px; }
blockquote.suspect { border-left-color: #f79009; }
ul.bullets { margin: 6px 0; padding-left: 20px; font-size: 13px; }
ul.bullets li { margin: 6px 0; }
ul.bullets .who { color: #1f5fbf; font-weight: 600; }
.refs { margin: 6px 0 0; font-size: 11.5px; color: #1f5fbf; }
.lead { margin: 2px 0 10px; padding: 8px 12px; border-left: 3px solid #1f5fbf; background: #f2f7ff; color: #24405f; font-size: 13px; }
.src { margin: 14px 0 0; padding-top: 8px; border-top: 1px solid #e3e9ef; font-size: 11.5px; color: #5b6b7d; }
.src-note { margin: 3px 0 0; font-size: 11px; color: #8a97a6; }
.unavailable { margin: 18px 0 6px; padding: 56px 20px; border: 1px dashed #c9d6e5; border-radius: 10px;
  background: #fbfcfe; text-align: center; color: #8a97a6; font-size: 14px; }
body.single { padding: 18px 22px 28px; background: #fff; }
body.single .page { max-width: none; padding: 8px 6px 12px; box-shadow: none; }
.foot { margin-top: 36px; padding-top: 12px; border-top: 1px solid #eaecf0; color: #98a2b3; font-size: 11.5px; }
.toc { columns: 2; font-size: 12.5px; color: #475467; margin: 6px 0 0; padding-left: 18px; }
@media print {
  body { background: #fff; padding: 0; }
  .page { box-shadow: none; max-width: none; padding: 0; }
  h2 { break-after: avoid; }
  .block { break-inside: avoid; }
  @page { margin: 16mm; }
}
"""


def _e(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _badge(status: str) -> str:
    label = _STATUS_LABELS.get(status, status)
    return f'<span class="badge { _e(status) }">{_e(label)}</span>'


def _block_note(block: dict[str, Any]) -> str:
    note = block.get("note") or ""
    return f'<p class="note">{_e(note)}</p>' if note else ""


def _extra_block_note(block: dict[str, Any]) -> str:
    """块级说明若与任一 model 说明重复就不再重复渲染。"""
    note = block.get("note") or ""
    if not note:
        return ""
    if any((model.get("note") or "") == note for model in block.get("models") or []):
        return ""
    return _block_note(block)


def _table(models: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for model in models:
        columns = model.get("columns") or []
        rows = model.get("rows") or []
        parts.append(f"<h4>{_e(model.get('label'))}</h4>")
        if not rows:
            parts.append(f'<p class="note">{_e(model.get("note") or "无数据")}</p>')
            continue
        parts.append("<table><thead><tr>")
        for index, column in enumerate(columns):
            cls = ' class="num"' if index else ""
            parts.append(f"<th{cls}>{_e(column)}</th>")
        parts.append("</tr></thead><tbody>")
        for row in rows:
            parts.append("<tr>")
            for index, cell in enumerate(row):
                cls = ' class="num"' if index else ""
                parts.append(f"<td{cls}>{_e(cell)}</td>")
            parts.append("</tr>")
        parts.append("</tbody></table>")
        if model.get("note"):
            parts.append(f'<p class="note">{_e(model["note"])}</p>')
    return "".join(parts)


def _matrix(block: dict[str, Any]) -> str:
    columns = block.get("columns") or []
    rows = block.get("rows") or []
    if not rows:
        return f'<p class="note">{_e(block.get("note") or "无数据")}</p>'
    parts = ["<table><thead><tr>"]
    for index, column in enumerate(columns):
        cls = ' class="num"' if index else ""
        parts.append(f"<th{cls}>{_e(column)}</th>")
    parts.append("</tr></thead><tbody>")
    for row in rows:
        parts.append("<tr>")
        for index, cell in enumerate(row):
            cls = ' class="num"' if index else ""
            parts.append(f"<td{cls}>{_e(cell)}</td>")
        parts.append("</tr>")
    parts.append("</tbody></table>")
    return "".join(parts)


def _bars(block: dict[str, Any]) -> str:
    parts: list[str] = []
    unit = block.get("unit") or ""
    maximum = float(block.get("max") or 100)
    for model in block.get("models") or []:
        parts.append(f"<h4>{_e(model.get('label'))}（n={_e(model.get('n'))}）</h4>")
        items = model.get("items") or []
        if not items:
            parts.append(f'<p class="note">{_e(model.get("note") or "无数据")}</p>')
            continue
        parts.append('<div class="bars">')
        for item in items:
            value = item.get("value")
            try:
                width = max(0.0, min(100.0, float(value) / maximum * 100))
            except (TypeError, ValueError):
                width = 0.0
            display = "—" if value is None else f"{value}{unit}"
            parts.append(
                '<div class="bar-row">'
                f'<div class="bar-label">{_e(item.get("label"))}</div>'
                f'<div class="bar-track"><div class="bar-fill" style="width:{width:.1f}%"></div></div>'
                f'<div class="bar-value">{_e(display)}（{_e(item.get("text"))}）</div>'
                "</div>"
            )
        parts.append("</div>")
        if model.get("note"):
            parts.append(f'<p class="note">{_e(model["note"])}</p>')
    return "".join(parts)


def _kv(block: dict[str, Any]) -> str:
    parts: list[str] = []
    for model in block.get("models") or []:
        parts.append(f"<h4>{_e(model.get('label'))}</h4>")
        items = model.get("items") or []
        if not items:
            parts.append(f'<p class="note">{_e(model.get("note") or "无数据")}</p>')
            continue
        parts.append('<div class="kv">')
        for item in items:
            parts.append(
                '<div class="kv-item">'
                f'<div class="kv-label">{_e(item.get("label"))}</div>'
                f'<div class="kv-value">{_e(item.get("value"))}</div>'
                f'<div class="kv-sub">{_e(item.get("sub"))}</div>'
                "</div>"
            )
        parts.append("</div>")
        if model.get("note"):
            parts.append(f'<p class="note">{_e(model["note"])}</p>')
    return "".join(parts)


def _quotes(block: dict[str, Any]) -> str:
    parts: list[str] = []
    for model in block.get("models") or []:
        people = model.get("people")
        archived = model.get("archived")
        denominator = f"（{people}/{archived} 份档案有值）" if archived else ""
        parts.append(f"<h4>{_e(model.get('label'))}{_e(denominator)}</h4>")
        items = model.get("items") or []
        if not items:
            parts.append(f'<p class="note">{_e(model.get("note") or "无数据")}</p>')
            continue
        for item in items:
            cls = "quote suspect" if item.get("suspect") else "quote"
            flag = "（待核）" if item.get("suspect") else ""
            parts.append(
                f'<blockquote class="{cls}">'
                f'<span class="who">{_e(item.get("code"))}</span>'
                f'{_e(item.get("text"))}{_e(flag)}</blockquote>'
            )
        if model.get("note"):
            parts.append(f'<p class="note">{_e(model["note"])}</p>')
    return "".join(parts)


def _bullets(block: dict[str, Any]) -> str:
    items = block.get("items") or []
    if not items:
        return f'<p class="note">{_e(block.get("note") or "无数据")}</p>'
    parts = ['<ul class="bullets">']
    for item in items:
        parts.append(f'<li><span class="who">{_e(item.get("model"))}</span> {_e(item.get("text"))}</li>')
    parts.append("</ul>")
    return "".join(parts)


_RENDERERS = {"table": None, "bars": _bars, "kv": _kv, "quotes": _quotes, "bullets": _bullets}


def _render_block(block: dict[str, Any], sources: dict[str, str]) -> str:
    if block.get("data_status") == "unavailable":
        return (
            '<div class="block">'
            '<div class="block-head">'
            f'<span class="block-title">{_e(block.get("title"))}</span>'
            f'{_badge("missing")}'
            "</div>"
            f'<div class="unavailable">{_e(block.get("empty_note") or "暂未提供数据")}</div>'
            f'<p class="note">{_e(block.get("note"))}</p>'
            "</div>"
        )
    if block["type"] == "table":
        body = _matrix(block) if block.get("kind") == "matrix" else _table(block.get("models") or [])
    else:
        body = _RENDERERS[block["type"]](block)
    if block.get("type") != "bullets" or block.get("items"):
        body = f"{body}{_extra_block_note(block)}"
    source = sources.get(block.get("source"), block.get("source"))
    refs = block.get("refs") or []
    refs_html = f'<p class="refs">来源引用：{_e("、".join(str(ref) for ref in refs))}</p>' if refs else ""
    return (
        '<div class="block">'
        '<div class="block-head">'
        f'<span class="block-title">{_e(block.get("title"))}</span>'
        f'{_badge(block.get("availability"))}'
        "</div>"
        f"{body}"
        f'<p class="note">数据来源：{_e(source)}</p>'
        f"{refs_html}"
        "</div>"
    )


def _page_sources(page: dict[str, Any]) -> str:
    # 不可用页同样保留页脚：数据源与口径说明照常出现，只是正文不出表格。
    parts = [
        f'{item.get("name")} n={item.get("n")}' if item.get("n") is not None else str(item.get("name"))
        for item in page.get("sources") or []
        if item.get("name")
    ]
    if not parts:
        return ""
    html = f'<p class="src">数据来源：{_e(" + ".join(parts))}</p>'
    note = page.get("footer_note") or ""
    if note:
        html += f'<p class="src-note">{_e(note)}</p>'
    return html


def _page_body(page: dict[str, Any], sources: dict[str, str]) -> str:
    """渲染单页正文（导语 + 块 / 整页不可用 + 页脚数据来源）。"""
    lead = f'<p class="lead">{_e(page.get("lead"))}</p>' if page.get("lead") else ""
    if page.get("data_status") == "unavailable":
        body = (
            f'<div class="unavailable"><p>{_e(page.get("empty_note") or "暂未提供数据")}</p>'
            + (f'<p class="note">{_e(page.get("missing_reason"))}</p>' if page.get("missing_reason") else "")
            + "</div>"
        )
    else:
        body = "".join(_render_block(block, sources) for block in page.get("blocks") or [])
    return f'<h2>{_e(page.get("page"))} · {_e(page.get("title"))}</h2>' \
           f'<p class="sub">{_e(page.get("subtitle"))}</p>{lead}{body}{_page_sources(page)}'


def render_report_page_html(content: dict[str, Any], page_id: str) -> str:
    """单页视图：只渲染大纲中的一页，样式与整篇报告一致；导出仍是完整 11 页。"""
    pages = list(content.get("pages") or [])
    all_pages = pages + list(content.get("appendices") or [])
    target = next((page for page in all_pages if str(page.get("page")) == str(page_id)), None)
    if target is None:
        raise KeyError(page_id)
    sources = {row["name"]: row["description"] for row in content.get("sources") or []}
    ordinal = next(
        (index + 1 for index, page in enumerate(pages) if str(page.get("page")) == str(page_id)),
        None,
    )
    position = f"第 {ordinal} / {len(pages)} 页" if ordinal else "附录"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(target.get("page"))} · {_e(target.get("title"))}</title>
<style>{_CSS}</style>
</head>
<body class="single">
<div class="page">
  {_page_body(target, sources)}
  <div class="foot">{_e(content.get("title"))} · {_e(position)} · 版本指纹 {_e((content.get("data_fingerprint") or "")[:12])}</div>
</div>
</body>
</html>
"""


def render_report_html(content: dict[str, Any]) -> str:
    sources = {row["name"]: row["description"] for row in content.get("sources") or []}
    models = content.get("models") or []
    chips = "".join(
        f'<span class="chip">{_e(model.get("label"))} · 定量 {_e((model.get("sources") or {}).get("quant", 0))} · '
        f'档案 {_e((model.get("archive") or {}).get("archived", 0))}</span>'
        for model in models
    )
    toc = "".join(
        f'<li>{_e(page.get("page"))} {_e(page.get("title"))}</li>'
        for page in list(content.get("pages") or []) + list(content.get("appendices") or [])
    )

    sections: list[str] = []
    for page in content.get("pages") or []:
        sections.append(f'<section id="{_e(page.get("page"))}">{_page_body(page, sources)}</section>')

    appendix_blocks = "".join(
        _render_block(block, sources) for page in content.get("appendices") or [] for block in page.get("blocks") or []
    )
    excluded = content.get("excluded_pages") or []
    excluded_rows = "".join(
        f'<tr><td>{_e(item.get("page"))}</td><td>{_e(item.get("title"))}</td><td>{_e(item.get("reason"))}</td></tr>'
        for item in excluded
    )
    excluded_html = (
        f"<h3>未纳入的页面</h3><table><thead><tr><th>编号</th><th>页面</th><th>原因</th></tr></thead>"
        f"<tbody>{excluded_rows}</tbody></table>"
        if excluded_rows
        else ""
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(content.get("title"))}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="page">
  <h1>{_e(content.get("title"))}</h1>
  <p class="sub">{_e(content.get("subtitle"))}</p>
  <div class="meta">
    <span>生成时间：{_e(content.get("generated_at"))}</span>
    <span>版本指纹：{_e((content.get("data_fingerprint") or "")[:12])}</span>
    <span>大纲：{_e(content.get("outline_version"))}</span>
  </div>
  <div class="chips">{chips}</div>
  <div class="scope">{_e(content.get("scope_note"))}</div>
  <h3>目录</h3>
  <ol class="toc">{toc}</ol>
  {"".join(sections)}
  <section id="APPENDIX"><h2>附录 · 数据边界</h2>
  <p class="sub">样本、来源、缺失项与未纳入页面</p>
  {appendix_blocks}
  {excluded_html}
  </section>
  <div class="foot">
    本报告由 BCI-007 报告服务生成，静态快照，不随底层数据自动变化；数据变动后旧版本标记为过期。<br>
    渲染器 {_e(RENDERER_VERSION)} · 大纲 {_e(content.get("outline_version"))} ·
    指纹 {_e(content.get("data_fingerprint"))}
  </div>
</div>
</body>
</html>
"""


__all__ = ["RENDERER_VERSION", "render_report_html", "render_report_page_html"]
