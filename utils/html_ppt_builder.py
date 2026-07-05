"""
汽车业务咨询风 HTML PPT 生成器。

这个模块不是固定页数模板，而是一个轻量的“报告到 deck”规划器：
1. 先解析本次智能体输出的章节、表格、机会市场、风险市场和行动建议。
2. 再按内容选择咨询风页型：cover、toc、table、comparison、detail、quote、cards 等。
3. 最后生成自包含 CSS/JS 的 HTML deck，内置键盘翻页、进度条、自定义光标和动效。
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class Section:
    """报告中的一级章节。"""

    title: str
    body: str


@dataclass
class Slide:
    """PPT 规划后的单页。"""

    kind: str
    title: str
    kicker: str = ""
    subtitle: str = ""
    bullets: list[str] = field(default_factory=list)
    cards: list[dict[str, str]] = field(default_factory=list)
    table: list[list[str]] = field(default_factory=list)
    note: str = ""
    accent: str = "blue"


def build_consulting_html_ppt(markdown: str, title: str, output_path: Path, project_dir: Path) -> dict[str, Any]:
    """根据每次业务报告动态生成 HTML PPT。"""

    report = parse_report(markdown, title)
    slides = plan_slides(report)
    html_text = render_deck(report, slides)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_text, encoding="utf-8")
    return {
        "success": True,
        "slides_count": len(slides),
        "file_size": output_path.stat().st_size,
        "engine": "consulting-html-ppt-generator",
    }


def parse_report(markdown: str, fallback_title: str) -> dict[str, Any]:
    text = normalize_text(markdown)
    title = extract_title(text) or fallback_title or "乘用车市场智能决策报告"
    sections = split_sections(text)
    return {
        "title": title,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "sections": sections,
        "raw": text,
    }


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_title(text: str) -> str:
    for line in text.splitlines():
        cleaned = clean(line)
        if not cleaned or cleaned in {"---", "----"}:
            continue
        if re.match(r"^[一二三四五六七八九十]+、", cleaned):
            continue
        return cleaned
    return ""


def split_sections(text: str) -> list[Section]:
    pattern = re.compile(r"(?m)^([一二三四五六七八九十]+、[^\n]+)\s*$")
    matches = list(pattern.finditer(text))
    sections: list[Section] = []
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections.append(Section(title=clean(match.group(1)), body=text[start:end].strip(" \n-")))
    if not sections:
        sections.append(Section("一、业务报告", text))
    return sections


def plan_slides(report: dict[str, Any]) -> list[Slide]:
    """按章节内容动态规划页数和页型。"""

    sections: list[Section] = report["sections"]
    slides: list[Slide] = [
        Slide(
            kind="cover",
            title=report["title"],
            kicker="AUTO STRATEGY REPORT",
            subtitle="乘用车市场与产品配置智能决策",
            bullets=["市场机会", "风险预警", "产能调配", "进入决策"],
            note="封面页用于明确本次报告主题和业务输出边界。",
        ),
        Slide(
            kind="toc",
            title=f"本次报告覆盖 {min(len(sections), 6)} 个业务章节",
            kicker="AGENDA",
            cards=[{"title": strip_index(s.title), "body": infer_section_role(s.title)} for s in sections[:6]],
            note="目录页根据本次报告真实章节自动生成。",
        ),
    ]

    for section in sections:
        name = strip_index(section.title)
        if "分析时点" in section.title or "任务边界" in section.title:
            slides.append(scope_slide(section))
        elif "分级" in section.title:
            slides.append(table_slide(section, "MARKET GRADING", "市场机会分级"))
        elif "高潜力" in section.title or "增量机会" in section.title:
            slides.extend(market_group_slides(section, "机会市场", "OPPORTUNITY", "green"))
        elif "高风险" in section.title or "衰退预警" in section.title:
            slides.extend(market_group_slides(section, "风险市场", "RISK WARNING", "red"))
        elif "产能" in section.title:
            slides.append(table_slide(section, "CAPACITY ALLOCATION", "区域产能调配"))
            principle = find_sentence(section.body, "原则")
            if principle:
                slides.append(
                    Slide(
                        kind="quote",
                        title="产能调配原则",
                        kicker="OPERATING PRINCIPLE",
                        subtitle=principle,
                        note="原则页把表格后的执行逻辑单独拎出，避免重要结论淹没在表格里。",
                    ),
                )
        elif "进入" in section.title or "暂缓" in section.title or "决策" in section.title:
            slides.append(table_slide(section, "GO / NO-GO", "进入与暂缓决策"))
            strategy_items = extract_after_label(section.body, "进入策略要点")
            if strategy_items:
                slides.append(
                    Slide(
                        kind="cards",
                        title="进入策略要点",
                        kicker="EXECUTION PLAYBOOK",
                        cards=cards_from_items(strategy_items[:3]),
                        note="策略页承接决策表，聚焦产品、渠道、定价等可执行动作。",
                    ),
                )
        elif "证据" in section.title or "假设" in section.title or "待补充" in section.title:
            slides.extend(evidence_slides(section))
        else:
            slides.append(generic_section_slide(section, name))

    return slides


def scope_slide(section: Section) -> Slide:
    cards = []
    for label in ["分析时点", "任务边界", "数据说明", "产品边界"]:
        value = extract_label_value(section.body, label)
        if value:
            cards.append({"title": label, "body": value})
    if not cards:
        cards = cards_from_items(extract_points(section.body, 4))
    return Slide("cards", "先定义战场，再判断机会", "SCOPE", cards=cards, note="边界页来自报告原文的分析时点、任务范围和数据说明。")


def market_group_slides(section: Section, label: str, kicker: str, accent: str) -> list[Slide]:
    blocks = split_named_blocks(section.body)
    slides: list[Slide] = []
    if blocks:
        overview_cards = []
        for title, body in blocks:
            overview_cards.append(
                {
                    "title": title,
                    "body": first_nonempty([extract_label_value(body, "进入建议"), extract_label_value(body, "建议动作"), first_sentence(body)]),
                },
            )
        slides.append(Slide("cards", f"{label}总览", kicker, cards=overview_cards, accent=accent, note="总览页由报告中的市场一/市场二或风险市场一/二自动生成。"))
        for title, body in blocks:
            basis = extract_after_label(body, "机会依据") or extract_after_label(body, "衰退信号") or extract_points(body, 3)
            decision = first_nonempty(
                [
                    extract_label_value(body, "进入建议"),
                    extract_label_value(body, "建议动作"),
                    extract_label_value(body, "触发条件"),
                    extract_label_value(body, "目标用户画像"),
                ],
            )
            slides.append(
                Slide(
                    kind="detail",
                    title=title,
                    kicker=kicker,
                    subtitle=decision,
                    bullets=basis[:3],
                    accent=accent,
                    note=f"{title}详情页，保留报告中的前三条核心依据。",
                ),
            )
    else:
        slides.append(generic_section_slide(section, strip_index(section.title), accent=accent))
    return slides


def evidence_slides(section: Section) -> list[Slide]:
    slides: list[Slide] = []
    table = first_table(section.body)
    if table:
        slides.append(Slide("table", "证据来源与引用内容", "EVIDENCE", table=table, note="证据页保留报告中的来源表格。"))
    assumptions = extract_after_label(section.body, "关键假设")
    if assumptions:
        slides.append(Slide("cards", "关键假设", "ASSUMPTIONS", cards=cards_from_items(assumptions[:3]), note="假设页用于标明结论成立的前提。"))
    data_need = extract_after_label(section.body, "待补充数据")
    if data_need:
        slides.append(Slide("cards", "待补充数据", "DATA GAP", cards=cards_from_items(data_need[:5]), note="数据缺口页用于指导后续数据建设。"))
    if not slides:
        slides.append(generic_section_slide(section, strip_index(section.title)))
    return slides


def table_slide(section: Section, kicker: str, fallback_title: str) -> Slide:
    table = first_table(section.body)
    if table:
        return Slide("table", fallback_title, kicker, table=table, note=f"{fallback_title}来自报告原始表格。")
    return generic_section_slide(section, fallback_title)


def generic_section_slide(section: Section, title: str, accent: str = "blue") -> Slide:
    table = first_table(section.body)
    if table:
        return Slide("table", title, "DATA TABLE", table=table, accent=accent, note="本页由章节中的结构化表格生成。")
    points = extract_points(section.body, 4)
    return Slide("cards", title, "SECTION", cards=cards_from_items(points), accent=accent, note="本页由章节要点自动提炼生成。")


def render_deck(report: dict[str, Any], slides: list[Slide]) -> str:
    rendered = "\n".join(render_slide(slide, i + 1, len(slides)) for i, slide in enumerate(slides))
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(report["title"])}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800;900&family=Noto+Sans+SC:wght@300;400;500;700;900&family=JetBrains+Mono:wght@400;500;700&display=swap');
  :root {{
    --bg-deep:#f1f5f9; --bg-paper:#f8fafc; --bg-surface:#ffffff; --bg-elevated:#e2e8f0;
    --text-primary:#0f172a; --text-secondary:#334155; --text-tertiary:#64748b; --hairline:#e2e8f0;
    --accent:#1d4ed8; --accent-soft:rgba(29,78,216,.08); --accent-glow:rgba(29,78,216,.04);
    --red:#c0392b; --amber:#d97706; --green:#15803d;
    --slide-transition:.6s cubic-bezier(.22,1,.36,1);
  }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  html,body {{ width:100%; height:100%; overflow:hidden; background:var(--bg-paper); color:var(--text-primary);
    font-family:"Outfit","Noto Sans SC","PingFang SC","Microsoft YaHei",sans-serif; -webkit-font-smoothing:antialiased; cursor:none; }}
  body::before {{ content:''; position:fixed; inset:0; pointer-events:none; z-index:1;
    background:radial-gradient(ellipse at 20% 0%,rgba(29,78,216,.03),transparent 50%),
               radial-gradient(ellipse at 80% 100%,rgba(217,119,6,.03),transparent 50%); }}
  body::after {{ content:''; position:fixed; inset:0; pointer-events:none; z-index:1;
    background-image:repeating-linear-gradient(0deg,transparent 0,transparent 4px,rgba(15,23,42,.008) 4px,rgba(15,23,42,.008) 5px); }}
  .cursor {{ position:fixed; width:32px; height:32px; border:2px solid var(--accent); border-radius:50%; pointer-events:none;
    z-index:9999; transform:translate(-50%,-50%); transition:width .2s,height .2s,opacity .2s,background-color .2s; opacity:.7; }}
  .cursor.hovering {{ width:52px; height:52px; opacity:.9; background:var(--accent-glow); }}
  .deck {{ position:relative; width:100vw; height:100vh; z-index:2; }}
  .badge {{ position:fixed; top:28px; left:clamp(28px,5vw,90px); display:flex; align-items:center; gap:12px; z-index:100; }}
  .badge-mark {{ width:24px; height:24px; border-radius:6px; background:var(--accent); color:#fff; font-weight:900; display:flex; align-items:center; justify-content:center; }}
  .badge-label {{ font-size:13px; letter-spacing:.15em; color:var(--text-secondary); font-weight:800; }}
  .episode-tag {{ position:fixed; top:28px; right:clamp(28px,5vw,90px); display:flex; align-items:center; gap:8px; z-index:100;
    font-size:13px; letter-spacing:.15em; text-transform:uppercase; color:var(--text-tertiary); font-weight:700; font-family:"JetBrains Mono",monospace; }}
  .episode-tag::before {{ content:''; width:8px; height:8px; border-radius:50%; background:var(--accent); }}
  .nav-arrows {{ position:fixed; bottom:22px; left:clamp(28px,5vw,90px); display:flex; gap:10px; z-index:100; }}
  .nav-arrows button {{ width:40px; height:40px; background:var(--bg-surface); border:1.5px solid var(--hairline); border-radius:8px;
    color:var(--text-secondary); font-size:16px; cursor:pointer; transition:.2s; }}
  .nav-arrows button:hover {{ border-color:var(--accent); color:var(--accent); background:var(--accent-soft); transform:translateY(-2px); }}
  .nav-counter {{ position:fixed; bottom:28px; right:clamp(28px,5vw,90px); z-index:100; font:700 15px "JetBrains Mono",monospace;
    letter-spacing:.1em; color:var(--text-tertiary); }}
  .nav-counter .current {{ color:var(--accent); font-weight:900; }}
  .progress-track {{ position:fixed; left:0; bottom:0; width:100%; height:4px; background:var(--bg-elevated); z-index:100; }}
  .progress-bar {{ height:100%; background:var(--accent); transition:width .6s cubic-bezier(.22,1,.36,1); }}
  .slide {{ position:absolute; inset:0; display:flex; flex-direction:column; justify-content:center; padding:clamp(40px,6vw,112px);
    opacity:0; transform:translateY(20px); pointer-events:none; transition:opacity var(--slide-transition),transform var(--slide-transition); overflow:hidden; }}
  .slide.active {{ opacity:1; transform:translateY(0); pointer-events:auto; }}
  .slide.exit-up {{ opacity:0; transform:translateY(-30px); }}
  .slide-tag {{ font-size:clamp(13px,1.25vw,16px); letter-spacing:.25em; text-transform:uppercase; color:var(--accent);
    font-weight:800; margin-bottom:16px; display:flex; align-items:center; gap:10px; }}
  .slide-tag::before {{ content:''; width:16px; height:3px; background:var(--accent); }}
  .slide-title {{ font-size:clamp(30px,4.2vw,58px); font-weight:900; line-height:1.25; letter-spacing:-.01em; margin-bottom:22px; max-width:1180px; }}
  .slide-title .accent {{ color:var(--accent); }} .slide-title .red {{ color:var(--red); }} .slide-title .green {{ color:var(--green); }}
  .slide-subtitle {{ font-size:clamp(16px,1.5vw,22px); color:var(--text-secondary); line-height:1.6; max-width:980px; font-weight:500; margin-bottom:16px; }}
  .cover-slide {{ justify-content:flex-end; padding-bottom:clamp(80px,10vh,150px); }}
  .cover-num {{ position:absolute; top:clamp(90px,12vh,150px); right:clamp(60px,8vw,140px); font-family:"JetBrains Mono",monospace;
    font-size:clamp(130px,22vw,340px); font-weight:900; color:rgba(29,78,216,.05); line-height:.8; letter-spacing:-.05em; user-select:none; }}
  .cover-num .small {{ display:block; margin-bottom:10px; font-size:.25em; color:rgba(29,78,216,.12); letter-spacing:.3em; font-weight:500; }}
  .cover-divider {{ width:80px; height:4px; background:var(--accent); margin:32px 0 8px; }}
  .cover-meta {{ display:flex; gap:clamp(24px,4vw,64px); margin-top:48px; border-top:2px solid var(--hairline); padding-top:32px; flex-wrap:wrap; }}
  .cover-meta-item {{ display:flex; flex-direction:column; gap:6px; }}
  .cover-meta-label {{ font:500 12px "JetBrains Mono",monospace; letter-spacing:.15em; text-transform:uppercase; color:var(--text-tertiary); }}
  .cover-meta-value {{ font-size:16px; color:var(--text-primary); font-weight:800; }}
  .cards-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:22px; margin-top:24px; max-width:1400px; }}
  .scene-card {{ background:var(--bg-surface); border:1.5px solid var(--hairline); border-radius:16px; padding:clamp(22px,2vw,34px);
    box-shadow:0 6px 18px rgba(15,23,42,.02); transition:.3s; }}
  .scene-card:hover {{ border-color:var(--accent); transform:translateY(-4px); box-shadow:0 16px 36px rgba(15,23,42,.06); }}
  .scene-header {{ display:flex; justify-content:space-between; gap:12px; align-items:center; border-bottom:2px dashed var(--hairline); padding-bottom:14px; margin-bottom:14px; }}
  .scene-title-text {{ font-size:19px; font-weight:900; color:var(--text-primary); }}
  .scene-tag {{ font:700 12px "JetBrains Mono",monospace; color:var(--accent); background:var(--accent-soft); padding:4px 10px; border-radius:6px; white-space:nowrap; }}
  .scene-core {{ font-size:15px; color:var(--text-secondary); line-height:1.5; margin-bottom:16px; background:var(--bg-deep); padding:8px 14px; border-radius:8px; font-weight:700; }}
  .table-container {{ margin-top:24px; background:var(--bg-surface); border:1.5px solid var(--hairline); border-radius:14px; overflow:hidden; box-shadow:0 6px 24px rgba(15,23,42,.03); max-width:1400px; }}
  .sop-table {{ width:100%; border-collapse:collapse; text-align:left; font-size:clamp(13px,1.12vw,16px); }}
  .sop-table th,.sop-table td {{ padding:13px 16px; border-bottom:1px solid var(--hairline); line-height:1.55; vertical-align:top; }}
  .sop-table th {{ background:var(--bg-deep); color:var(--text-primary); font-weight:900; letter-spacing:.04em; }}
  .sop-table tr:last-child td {{ border-bottom:0; }}
  .gold-rule-box {{ margin-top:22px; padding:17px 24px; background:var(--accent-soft); border-left:5px solid var(--accent); border-radius:6px;
    font-size:clamp(15px,1.35vw,19px); line-height:1.65; max-width:1400px; }}
  .gold-rule-box strong {{ color:var(--accent); }}
  .quote-balloon {{ background:rgba(192,57,43,.03); border:1.5px solid rgba(192,57,43,.15); border-left:6px solid var(--red);
    border-radius:12px; padding:24px; position:relative; box-shadow:0 4px 12px rgba(192,57,43,.02); }}
  .quote-balloon::after {{ content:'"'; position:absolute; right:24px; bottom:8px; font-size:72px; line-height:1; color:rgba(192,57,43,.08); font-family:Georgia,serif; font-weight:900; }}
  .compare-layout {{ display:grid; grid-template-columns:1fr 1fr; gap:32px; margin-top:22px; max-width:1400px; }}
  .compare-column {{ background:var(--bg-surface); border:1.5px solid var(--hairline); border-radius:16px; padding:28px; box-shadow:0 6px 18px rgba(0,0,0,.01); }}
  .compare-column.bad {{ border-top:5px solid var(--red); }} .compare-column.good {{ border-top:5px solid var(--green); }}
  .compare-header {{ font-size:19px; font-weight:900; margin-bottom:18px; padding-bottom:10px; border-bottom:1.5px solid var(--hairline); }}
  .compare-column.bad .compare-header {{ color:var(--red); }} .compare-column.good .compare-header {{ color:var(--green); }}
  .compare-list {{ list-style:none; display:flex; flex-direction:column; gap:15px; }}
  .compare-list li {{ font-size:15px; line-height:1.6; color:var(--text-secondary); }}
  .timeline-layout {{ display:flex; gap:20px; margin-top:26px; max-width:1400px; }}
  .timeline-step {{ flex:1; background:var(--bg-surface); border:1.5px solid var(--hairline); border-radius:16px; padding:24px; box-shadow:0 6px 18px rgba(15,23,42,.02); }}
  .step-num {{ width:40px; height:40px; background:var(--accent); color:#fff; border-radius:50%; display:flex; align-items:center; justify-content:center; font:700 16px "JetBrains Mono",monospace; margin-bottom:12px; }}
  .step-name {{ font-size:18px; font-weight:900; color:var(--text-primary); margin-bottom:8px; }}
  .step-desc {{ font-size:15px; color:var(--text-secondary); line-height:1.6; }}
  .big-num {{ font:900 64px/1 "JetBrains Mono",monospace; color:var(--accent); opacity:.95; }}
  .accent-red .slide-tag,.accent-red .big-num {{ color:var(--red); }} .accent-red .slide-tag::before {{ background:var(--red); }}
  .accent-green .slide-tag,.accent-green .big-num {{ color:var(--green); }} .accent-green .slide-tag::before {{ background:var(--green); }}
  .notes {{ display:none; }}
  .slide p,.slide li {{ line-height:1.62; }}
  .slide.active .stagger {{ animation:fadeUp .6s cubic-bezier(.22,1,.36,1) both; }}
  .slide.active .stagger:nth-child(1) {{ animation-delay:.08s; }} .slide.active .stagger:nth-child(2) {{ animation-delay:.16s; }}
  .slide.active .stagger:nth-child(3) {{ animation-delay:.24s; }} .slide.active .stagger:nth-child(4) {{ animation-delay:.32s; }}
  @keyframes fadeUp {{ from {{ opacity:0; transform:translateY(20px); }} to {{ opacity:1; transform:translateY(0); }} }}
  @media (max-width:900px) {{ .cards-grid,.compare-layout {{ grid-template-columns:1fr!important; }} .timeline-layout {{ flex-direction:column; }} }}
</style>
</head>
<body>
<div class="cursor" id="cursor"></div>
<div class="deck" id="deck">
  <div class="badge"><div class="badge-mark">S</div><div class="badge-label">汽车市场智能决策 HTML PPT</div></div>
  <div class="episode-tag">Consulting / Case Study Edition</div>
  <div class="nav-arrows"><button onclick="prev()" aria-label="上一页">←</button><button onclick="next()" aria-label="下一页">→</button></div>
  <div class="nav-counter"><span class="current" id="navCurrent">01</span> / <span id="navTotal">{len(slides):02d}</span></div>
  <div class="progress-track"><div class="progress-bar" id="progressBar"></div></div>
{rendered}
</div>
<script>
  const cursor = document.getElementById('cursor');
  document.addEventListener('mousemove', e => {{ cursor.style.left = e.clientX + 'px'; cursor.style.top = e.clientY + 'px'; }});
  document.addEventListener('mouseleave', () => {{ cursor.style.opacity = '0'; }});
  document.addEventListener('mouseenter', () => {{ cursor.style.opacity = '0.7'; }});
  document.querySelectorAll('button, table, .scene-card, .timeline-step, .quote-balloon, .compare-column').forEach(el => {{
    el.addEventListener('mouseenter', () => cursor.classList.add('hovering'));
    el.addEventListener('mouseleave', () => cursor.classList.remove('hovering'));
  }});
  const slides = Array.from(document.querySelectorAll('.slide'));
  let current = 0;
  function goTo(idx) {{
    if (idx < 0 || idx >= slides.length || idx === current) return;
    slides[current].classList.remove('active');
    slides[current].classList.add('exit-up');
    current = idx;
    slides[current].classList.remove('exit-up');
    slides[current].classList.add('active');
    updateUI();
  }}
  function next() {{ goTo(current + 1); }}
  function prev() {{ goTo(current - 1); }}
  function updateUI() {{
    document.getElementById('navCurrent').textContent = String(current + 1).padStart(2, '0');
    document.getElementById('navTotal').textContent = String(slides.length).padStart(2, '0');
    document.getElementById('progressBar').style.width = ((current + 1) / slides.length * 100) + '%';
    location.hash = '#/' + (current + 1);
  }}
  document.addEventListener('keydown', e => {{
    if (['ArrowRight', 'PageDown', ' '].includes(e.key)) next();
    if (['ArrowLeft', 'PageUp'].includes(e.key)) prev();
    if (e.key === 'Home') goTo(0);
    if (e.key === 'End') goTo(slides.length - 1);
  }});
  const m = location.hash.match(/#\\/(\\d+)/);
  if (m) {{
    const idx = Math.max(0, Math.min(slides.length - 1, Number(m[1]) - 1));
    slides.forEach(s => s.classList.remove('active'));
    current = idx;
    slides[current].classList.add('active');
  }}
  updateUI();
</script>
</body>
</html>"""


def render_slide(slide: Slide, page: int, total: int) -> str:
    accent_class = f"accent-{slide.accent}" if slide.accent != "blue" else ""
    if slide.kind == "cover":
        meta = [
            ("Report Type", slide.subtitle or "市场战略分析"),
            ("Generated", datetime.now().strftime("%Y.%m.%d")),
            ("Focus", "机会 / 风险 / 产能 / 决策"),
            ("Format", "HTML Consulting Deck"),
        ]
        body = f"""
    <div class="cover-num"><span class="small">REPORT</span>{page:02d}</div>
    <div class="slide-tag stagger">{esc(slide.kicker)}</div>
    <h1 class="slide-title stagger">{esc(slide.title)}</h1>
    <p class="slide-subtitle stagger">{esc(slide.subtitle)}</p>
    <div class="cover-divider stagger"></div>
    <div class="cover-meta stagger">{''.join(f'<div class="cover-meta-item"><span class="cover-meta-label">{esc(k)}</span><span class="cover-meta-value">{esc(v)}</span></div>' for k, v in meta)}</div>"""
    elif slide.kind == "toc":
        body = f"""
    <div class="slide-tag stagger">{esc(slide.kicker)}</div>
    <h2 class="slide-title stagger">{esc(slide.title)}</h2>
    <p class="slide-subtitle stagger">先看结构，再进入市场机会、风险预警、产能调配与进入决策。</p>
    <div class="cards-grid stagger" style="grid-template-columns:repeat(3,1fr);">{''.join(render_toc_card(i, c) for i, c in enumerate(slide.cards, 1))}</div>"""
    elif slide.kind == "table":
        body = f"""
    <div class="slide-tag stagger">{esc(slide.kicker)}</div>
    <h2 class="slide-title stagger">{esc(conclusion_title(slide.title))}</h2>
    <p class="slide-subtitle stagger">保留原始业务表格，但用咨询风表格容器强化层级与可读性。</p>
    <div class="table-container stagger">{render_table(slide.table)}</div>"""
    elif slide.kind == "detail":
        body = f"""
    <div class="slide-tag stagger">{esc(slide.kicker)}</div>
    <h2 class="slide-title stagger">{esc(slide.title)}</h2>
    <p class="slide-subtitle stagger">{esc(slide.subtitle or '围绕市场信号、触发条件与执行动作进行判断。')}</p>
    <div class="compare-layout stagger">
      <div class="quote-balloon"><div class="scene-title-text">决策提示</div><p style="margin-top:12px;line-height:1.7;color:var(--text-secondary);font-weight:600;">{esc(slide.subtitle or '详见右侧依据')}</p></div>
      <div class="timeline-layout" style="margin-top:0;flex-direction:column;">{''.join(render_bullet(i, b) for i, b in enumerate(slide.bullets[:3], 1))}</div>
    </div>"""
    elif slide.kind == "quote":
        body = f"""
    <div class="slide-tag stagger">{esc(slide.kicker)}</div>
    <h2 class="slide-title stagger">{esc(slide.title)}</h2>
    <div class="gold-rule-box stagger"><strong>关键原则：</strong>{esc(slide.subtitle)}</div>"""
    else:
        body = f"""
    <div class="slide-tag stagger">{esc(slide.kicker)}</div>
    <h2 class="slide-title stagger">{esc(slide.title)}</h2>
    <p class="slide-subtitle stagger">将报告要点压缩为可讨论、可决策、可行动的业务卡片。</p>
    <div class="cards-grid stagger">{''.join(render_story_card(i, c) for i, c in enumerate(slide.cards[:6], 1))}</div>"""

    return f"""
  <div class="slide {'cover-slide' if slide.kind == 'cover' else ''} {accent_class} {'active' if page == 1 else ''}" data-index="{page - 1}" data-title="{esc(slide.title)}">
{body}
    <div class="notes">{esc(slide.note or slide.title)}</div>
  </div>"""


def footer(page: int, total: int, label: str) -> str:
    return (
        f'<div class="deck-header"><span class="biz-mark">CATARC AI DECISION</span><span>{esc(label)}</span></div>'
        f'<div class="deck-footer"><span>Passenger Vehicle · New Energy SUV</span>'
        f'<span class="slide-number" data-current="{page}" data-total="{total}"></span></div>'
    )


def render_toc_card(index: int, card: dict[str, str]) -> str:
    return f'<div class="scene-card"><div class="scene-header"><span class="scene-title-text">{esc(card.get("title", ""))}</span><span class="scene-tag">{index:02d}</span></div><div class="scene-core">{esc(card.get("body", ""))}</div></div>'


def render_story_card(index: int, card: dict[str, str]) -> str:
    return f'<div class="scene-card"><div class="scene-header"><span class="scene-title-text">{esc(card.get("title", ""))}</span><span class="scene-tag">{index:02d}</span></div><div class="scene-core">{esc(card.get("body", ""))}</div></div>'


def render_bullet(index: int, text: str) -> str:
    return f'<div class="timeline-step"><div class="step-num">{index:02d}</div><div class="step-name">核心依据</div><div class="step-desc">{esc(text)}</div></div>'


def render_table(table: list[list[str]]) -> str:
    if not table:
        return ""
    head, rows = table[0], table[1:]
    return (
        '<table class="sop-table"><thead><tr>'
        + "".join(f"<th>{esc(x)}</th>" for x in head)
        + "</tr></thead><tbody>"
        + "".join("<tr>" + "".join(f"<td>{esc(cell)}</td>" for cell in row) + "</tr>" for row in rows[:8])
        + "</tbody></table>"
    )


def conclusion_title(title: str) -> str:
    """把中性章节名改写成更像咨询页的结论标题。"""

    mapping = {
        "市场机会分级": "市场应按“重点投放、稳健布局、暂缓扩张”三档管理",
        "区域产能调配": "产能应向川渝与华南倾斜，高风险市场转为订单式供给",
        "进入与暂缓决策": "进入、深耕、暂缓与收缩要按区域分层执行",
        "证据来源与引用内容": "关键判断需要由销量、渗透率、区域结构与政策证据共同支撑",
    }
    return mapping.get(title, title)


def first_table(text: str) -> list[list[str]]:
    lines = [line.strip() for line in text.splitlines()]
    tables: list[list[str]] = []
    current: list[list[str]] = []
    for line in lines + [""]:
        if is_table_line(line):
            row = parse_table_line(line)
            if row and not all(re.fullmatch(r":?-{2,}:?", cell) for cell in row):
                current.append(row)
        else:
            if len(current) >= 2:
                tables = current
                break
            current = []
    if not tables:
        return []
    width = max(len(row) for row in tables)
    return [row + [""] * (width - len(row)) for row in tables]


def is_table_line(line: str) -> bool:
    return ("\t" in line and len(line.split("\t")) >= 3) or (line.startswith("|") and line.endswith("|"))


def parse_table_line(line: str) -> list[str]:
    if "\t" in line:
        return [clean(cell) for cell in line.split("\t") if clean(cell)]
    return [clean(cell) for cell in line.strip("|").split("|")]


def split_named_blocks(text: str) -> list[tuple[str, str]]:
    pattern = re.compile(r"(?m)^((?:市场|风险市场)[一二三四五六\d]+[:：][^\n]+)\s*$")
    matches = list(pattern.finditer(text))
    blocks = []
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        blocks.append((clean(match.group(1)), text[start:end].strip()))
    return blocks


def extract_label_value(text: str, label: str) -> str:
    match = re.search(rf"{re.escape(label)}[:：]\s*([^\n]+)", text)
    return clean(match.group(1)) if match else ""


def extract_after_label(text: str, label: str) -> list[str]:
    idx = text.find(label)
    if idx < 0:
        return []
    block = text[idx + len(label) : idx + len(label) + 1400]
    return extract_points(block, 5)


def extract_points(text: str, limit: int = 5) -> list[str]:
    points: list[str] = []
    for line in text.splitlines():
        raw = clean(line)
        if not raw or raw in {"---"} or is_table_line(raw):
            continue
        if raw.endswith(("：", ":")) and len(raw) <= 18:
            continue
        match = re.match(r"^(?:[•\-]|[0-9]+[.、])\s*(.+)$", raw)
        if match:
            points.append(clean(match.group(1)))
        elif "：" in raw and len(raw) <= 130:
            points.append(raw)
    if not points:
        for sentence in re.split(r"(?<=[。；])", clean(text)):
            sentence = clean(sentence)
            if 12 <= len(sentence) <= 160:
                points.append(sentence)
    return unique(points)[:limit]


def cards_from_items(items: list[str]) -> list[dict[str, str]]:
    cards = []
    for item in items:
        title, body = split_title_body(item)
        cards.append({"title": title, "body": body})
    return cards


def split_title_body(text: str) -> tuple[str, str]:
    text = clean(text)
    for sep in ["：", ":"]:
        if sep in text:
            left, right = text.split(sep, 1)
            if 2 <= len(left) <= 24:
                return clean(left), clean(right)
    if "，" in text:
        left, right = text.split("，", 1)
        return clean(left[:24]), clean(right)
    return text[:24], text


def find_sentence(text: str, keyword: str) -> str:
    for sentence in re.split(r"(?<=[。；])", clean(text)):
        if keyword in sentence:
            return sentence
    return ""


def first_sentence(text: str) -> str:
    for sentence in re.split(r"(?<=[。；])", clean(text)):
        if len(sentence) > 8:
            return sentence
    return clean(text)[:120]


def first_nonempty(values: list[str]) -> str:
    for value in values:
        if value:
            return value
    return ""


def infer_section_role(title: str) -> str:
    if "机会" in title:
        return "识别增量区域和产品投放窗口"
    if "风险" in title or "预警" in title:
        return "识别政策、饱和与竞争衰退信号"
    if "产能" in title:
        return "把市场判断转译为区域供给策略"
    if "进入" in title or "决策" in title:
        return "形成进入、深耕、暂缓或收缩动作"
    if "证据" in title:
        return "明确结论依据、假设和数据缺口"
    return "界定分析范围与业务判断依据"


def strip_index(title: str) -> str:
    return re.sub(r"^[一二三四五六七八九十]+、", "", clean(title))


def clean(text: str) -> str:
    text = re.sub(r"[*_`#>]+", "", str(text or ""))
    text = text.replace("•", "").strip()
    return re.sub(r"\s+", " ", text)


def unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for item in items:
        key = item[:80]
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def esc(text: str) -> str:
    return html.escape(str(text or ""), quote=True)
