# -*- coding: utf-8 -*-
"""
gen_visual_html.py  ——  周报可视化 HTML 生成器

用途：读取 report_data.json，生成与 docx 正报配套的「图文并茂单文件 HTML 速览」。
      作为 gen_report.py 之后的**第五步**自动执行，产出阅读版；docx 仍是归档版。

用法：
    python scripts/gen_visual_html.py \
        --data report_data.json \
        --date-new 09.30-1006 \
        --output "中国汽车产业周度资讯快报2026.0930-1006.html" \
        [--title-prefix "中国汽车产业"]

设计要点：
  - 单文件、零外链依赖、浅色主题（用户既定偏好）
  - 九大板块各自配色，贯穿板块头 / 卡片左边框 / 日期标签
  - 结构自动生成：Hero + KPI + sticky 导航 + 摘要卡 + 九大板块正文 + 来源表
  - 可选增强内容由 report_data.json 的顶层 "visual" 字段驱动（KPI / 图表 / 时间轴 / 观察），
    缺省即自动跳过，不影响出图。
"""

import argparse
import html
import json
import os
import re
import sys

# ---------------------------------------------------------------- 板块配色
SECTION_COLORS = {
    "政策法规": ("--c-policy", "#2563eb"),
    "宏观动态": ("--c-macro", "#0ea5e9"),
    "行业动态": ("--c-industry", "#8b5cf6"),
    "企业要闻": ("--c-company", "#f59e0b"),
    "高层动态": ("--c-exec", "#ec4899"),
    "零部件": ("--c-parts", "#14b8a6"),
    "战略规划": ("--c-strategy", "#6366f1"),
    "新技术/新趋势": ("--c-tech", "#16a34a"),
    "新车上市": ("--c-newcar", "#ef4444"),
}
DEFAULT_COLOR = ("--c-policy", "#2563eb")

CN_NUM = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]


def esc(s):
    """转义为 HTML 安全文本；保留中文弯引号。"""
    return html.escape(str(s or ""), quote=False)


def safe_url(u):
    """仅放行 http/https，避免 javascript: 之类注入。"""
    u = str(u or "").strip()
    if re.match(r"^https?://", u, re.I):
        return html.escape(u, quote=True)
    return ""


def host_of(u):
    m = re.match(r"^https?://([^/]+)", str(u or ""), re.I)
    if not m:
        return "来源"
    return m.group(1).replace("www.", "")


# ---------------------------------------------------------------- 分组
def group_sections(body_sections):
    """把扁平的 (section, subsection) 列表按 section 归组，保持出现顺序。"""
    order, buckets = [], {}
    for blk in body_sections:
        sec = (blk.get("section") or "").strip()
        if not sec:
            continue
        if sec not in buckets:
            buckets[sec] = []
            order.append(sec)
        buckets[sec].append(blk)
    return [(s, buckets[s]) for s in order]


# ---------------------------------------------------------------- 组件渲染
def render_kpis(kpis):
    if not kpis:
        return ""
    acc = ["--c-policy", "--c-macro", "--c-industry", "--c-company", "--c-newcar"]
    out = ['<div class="kpi-grid">']
    for i, k in enumerate(kpis[:5]):
        out.append(
            '<div class="kpi" style="border-top-color:var(%s)">'
            '<div class="num">%s<small>%s</small></div>'
            '<div class="lbl">%s</div></div>'
            % (acc[i % len(acc)], esc(k.get("num", "")), esc(k.get("unit", "")),
               esc(k.get("label", "")).replace("\n", "<br>"))
        )
    out.append("</div>")
    return "".join(out)


def render_bars(bars):
    """bars: [{title, note, rows:[{k, label, pct, color, v}]}]"""
    if not bars:
        return ""
    out = []
    for b in bars:
        out.append('<div class="panel" style="margin-bottom:16px">')
        if b.get("title"):
            out.append('<div class="panel-title">%s</div>' % esc(b["title"]))
        if b.get("note"):
            out.append('<div class="panel-note">%s</div>' % esc(b["note"]))
        out.append('<div class="bars">')
        for r in b.get("rows", []):
            pct = max(0.0, min(100.0, float(r.get("pct", 0) or 0)))
            out.append(
                '<div class="bar-row">'
                '<div class="k">%s</div>'
                '<div class="bar-track"><div class="bar-fill" style="--bc:%s;width:%.1f%%">%s</div></div>'
                '<div class="v">%s</div></div>'
                % (esc(r.get("k", "")), esc(r.get("color", "#2563eb")), pct,
                   esc(r.get("label", "")), esc(r.get("v", "")))
            )
        out.append("</div>")
        if b.get("foot"):
            out.append('<div style="margin-top:16px;font-size:13px;color:var(--ink-3);line-height:1.75">%s</div>'
                       % esc(b["foot"]))
        out.append("</div>")
    return "".join(out)


def render_donut(d):
    """d: {title, note, pct, label, color, legend:[{text, value, color}]}"""
    if not d:
        return ""
    pct = max(0.0, min(100.0, float(d.get("pct", 0) or 0)))
    r = 54.0
    circ = 2 * 3.141592653589793 * r
    dash = circ * pct / 100.0
    color = d.get("color", "#0ea5e9")
    legend = "".join(
        '<div><i style="background:%s"></i>%s<b style="color:#1f2329;margin-left:auto">%s</b></div>'
        % (esc(l.get("color", "#e5e6eb")), esc(l.get("text", "")), esc(l.get("value", "")))
        for l in d.get("legend", [])
    )
    leg = ('<div class="legend">%s</div>' % legend) if legend else ""
    return (
        '<div class="panel" style="margin-bottom:16px">'
        '<div class="panel-title">%s</div><div class="panel-note">%s</div>'
        '<div class="donut-wrap"><div class="donut">'
        '<svg width="132" height="132" viewBox="0 0 132 132">'
        '<circle cx="66" cy="66" r="54" fill="none" stroke="#e5e6eb" stroke-width="16"/>'
        '<circle cx="66" cy="66" r="54" fill="none" stroke="%s" stroke-width="16" '
        'stroke-dasharray="%.1f %.1f" stroke-linecap="round" transform="rotate(-90 66 66)"/>'
        "</svg>"
        '<div class="center"><b>%s</b><span>%s</span></div></div>%s</div></div>'
        % (esc(d.get("title", "")), esc(d.get("note", "")), esc(color),
           dash, circ - dash, esc(d.get("label_value", "%g%%" % pct)), esc(d.get("label", "")), leg)
    )


def render_timeline(items, color="#ef4444"):
    if not items:
        return ""
    out = ['<div class="panel"><div class="panel-title">%s</div><div class="panel-note">%s</div><div class="tl">'
           % (esc(items[0].get("_title", "时间轴")), esc(items[0].get("_note", "")))]
    for it in items:
        out.append(
            '<div class="tl-item%s"><div class="tl-date">%s</div><div class="tl-name">%s</div>'
            '<div class="tl-desc">%s</div></div>'
            % (" done" if it.get("done") else "", esc(it.get("date", "")),
               esc(it.get("name", "")), it.get("desc", ""))
        )
    out.append("</div></div>")
    return "".join(out)


def render_insights(insights, color="#2563eb"):
    if not insights:
        return ""
    out = []
    for i, ins in enumerate(insights, 1):
        out.append(
            '<div class="insight" style="border-left-color:%s">'
            '<h4><span class="no">%d</span>%s</h4><p>%s</p></div>'
            % (esc(color), i, esc(ins.get("title", "")), esc(inesc(s.get("body", ""))))
        )
    return "".join(out)


def render_news(sec_name, items, color):
    out = []
    for it in items:
        chips = ""
        if it.get("date"):
            chips += '<span class="date-chip">%s</span>' % esc(it["date"])
        if it.get("tag"):
            chips += ('<span style="font-size:12px;color:#86909c">%s</span>' % esc(it["tag"]))
        src = safe_url(it.get("source"))
        if src:
            chips += ('<a class="src" href="%s" target="_blank" rel="noopener">来源 · %s</a>'
                      % (src, esc(host_of(it["source"]))))
        out.append(
            '<div class="news" style="border-left-color:%s">'
            "<h4>%s</h4>"
            '<div class="meta">%s</div>'
            "<p>%s</p></div>"
            % (esc(color), esc(it.get("title", "")), chips, esc(it.get("body", "")))
        )
    return "".join(out)


def render_sources(rows):
    if not rows:
        return ""
    out = ['<details class="src-box" open><summary>点击核验每条资讯的原始出处</summary>'
           '<table class="src"><thead><tr><th>板块</th><th>条目标题</th><th>日期</th><th>来源</th></tr></thead><tbody>']
    for r in rows:
        u = safe_url(r.get("source"))
        link = ('<a href="%s" target="_blank" rel="noopener">%s</a>' % (u, esc(host_of(r["source"]))))
        out.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
                   % (esc(r.get("section", "")), esc(r.get("title", "")),
                      esc(r.get("date", "")), link))
    out.append("</tbody></table></details>")
    return "".join(out)


# ---------------------------------------------------------------- CSS
CSS = r"""
:root{
  --bg:#f4f5f7;--card:#ffffff;--ink:#1f2329;--ink-2:#4e5969;--ink-3:#86909c;
  --line:#e5e6eb;--line-2:#f0f1f3;--radius:14px;
  --shadow:0 1px 2px rgba(16,24,40,.04),0 6px 20px rgba(16,24,40,.06);
  --c-policy:#2563eb;--c-macro:#0ea5e9;--c-industry:#8b5cf6;--c-company:#f59e0b;
  --c-exec:#ec4899;--c-parts:#14b8a6;--c-strategy:#6366f1;--c-tech:#16a34a;--c-newcar:#ef4444;
}
*{box-sizing:border-box;margin:0;padding:0;}
html{scroll-behavior:smooth;}
body{background:var(--bg);color:var(--ink);font-size:15px;line-height:1.75;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  -webkit-font-smoothing:antialiased;}
.wrap{max-width:1080px;margin:0 auto;padding:0 22px 80px;}
.hero{background:linear-gradient(135deg,#0f172a 0%,#1e293b 45%,#334155 100%);
  color:#fff;padding:52px 22px 40px;position:relative;overflow:hidden;}
.hero::after{content:"";position:absolute;right:-120px;top:-120px;width:420px;height:420px;
  background:radial-gradient(circle,rgba(59,130,246,.35),transparent 65%);border-radius:50%;}
.hero-inner{max-width:1080px;margin:0 auto;position:relative;z-index:1;}
.eyebrow{display:inline-flex;align-items:center;gap:8px;font-size:12.5px;letter-spacing:.06em;
  background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.2);
  padding:6px 14px;border-radius:999px;color:#dbeafe;margin-bottom:20px;}
.hero h1{font-size:34px;line-height:1.3;font-weight:700;letter-spacing:-.01em;margin-bottom:14px;}
.hero h1 span{color:#7dd3fc;}
.hero p.sub{color:#cbd5e1;font-size:14.5px;max-width:760px;}
.hero-meta{margin-top:22px;display:flex;flex-wrap:wrap;gap:10px;}
.hero-meta span{font-size:12.5px;color:#e2e8f0;background:rgba(255,255,255,.09);
  border:1px solid rgba(255,255,255,.14);padding:5px 13px;border-radius:8px;}
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px;
  margin-top:-30px;position:relative;z-index:2;}
.kpi{background:var(--card);border-radius:var(--radius);padding:20px 20px 18px;
  box-shadow:var(--shadow);border-top:3px solid var(--c-policy);}
.kpi .num{font-size:28px;font-weight:700;letter-spacing:-.02em;line-height:1.15;}
.kpi .num small{font-size:14px;font-weight:600;margin-left:3px;color:var(--ink-2);}
.kpi .lbl{font-size:12.5px;color:var(--ink-3);margin-top:6px;line-height:1.5;}
nav.toc{position:sticky;top:0;z-index:50;background:rgba(244,245,247,.92);
  backdrop-filter:blur(10px);border-bottom:1px solid var(--line);
  margin:34px -22px 0;padding:12px 22px;display:flex;gap:8px;overflow-x:auto;scrollbar-width:none;}
nav.toc::-webkit-scrollbar{display:none;}
nav.toc a{flex:0 0 auto;font-size:13px;color:var(--ink-2);text-decoration:none;
  padding:6px 13px;border-radius:999px;border:1px solid var(--line);background:#fff;white-space:nowrap;}
nav.toc a:hover{border-color:#c9cdd4;color:var(--ink);}
section{margin-top:44px;scroll-margin-top:70px;}
.sec-head{display:flex;align-items:center;gap:13px;margin-bottom:6px;}
.sec-num{width:36px;height:36px;border-radius:10px;flex:0 0 auto;display:flex;
  align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:15px;background:var(--c);}
.sec-title{font-size:21px;font-weight:700;letter-spacing:-.01em;}
.sec-count{font-size:12.5px;color:var(--ink-3);font-weight:400;margin-left:2px;}
.sec-sub{font-size:13.5px;color:var(--ink-3);margin:0 0 18px 49px;}
.sum-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px;}
.sum-item{background:var(--card);border-radius:var(--radius);padding:18px 20px;
  box-shadow:var(--shadow);display:flex;gap:14px;align-items:flex-start;
  transition:.18s;border:1px solid transparent;}
.sum-item:hover{transform:translateY(-2px);border-color:#dbe4f5;}
.sum-item .idx{flex:0 0 auto;width:26px;height:26px;border-radius:8px;background:#eef2ff;
  color:#4338ca;font-size:13px;font-weight:700;display:flex;align-items:center;
  justify-content:center;margin-top:2px;}
.sum-item p{font-size:14.5px;line-height:1.72;color:var(--ink-2);}
.sum-item p b{color:var(--ink);font-weight:600;}
.sum-item h5{font-size:14.5px;font-weight:650;color:var(--ink);margin-bottom:3px;}
.news{background:var(--card);border-radius:var(--radius);box-shadow:var(--shadow);
  border-left:3px solid var(--c);padding:20px 22px;margin-bottom:13px;}
.news h4{font-size:16.5px;font-weight:650;line-height:1.5;margin-bottom:9px;}
.news .meta{display:flex;flex-wrap:wrap;align-items:center;gap:9px;margin-bottom:11px;}
.date-chip{font-size:12px;font-weight:600;color:var(--c);background:#f2f4f8;
  background:color-mix(in srgb,var(--c) 10%,#fff);padding:3px 9px;border-radius:6px;}
.news p{font-size:14.5px;color:var(--ink-2);line-height:1.78;}
.news p b{color:var(--ink);font-weight:600;}
.news a.src{font-size:12.5px;color:var(--ink-3);text-decoration:none;
  border-bottom:1px dashed var(--line);}
.news a.src:hover{color:var(--c);}
.subhead{display:flex;align-items:center;gap:9px;margin:26px 0 13px;}
.subhead .dot{width:7px;height:7px;border-radius:50%;background:var(--c);}
.subhead h3{font-size:15.5px;font-weight:650;}
.subhead .n{font-size:12px;color:var(--ink-3);}
.panel{background:var(--card);border-radius:var(--radius);box-shadow:var(--shadow);padding:22px 24px;}
.panel-title{font-size:14px;font-weight:650;margin-bottom:4px;}
.panel-note{font-size:12.5px;color:var(--ink-3);margin-bottom:18px;}
.bars{display:flex;flex-direction:column;gap:14px;}
.bar-row{display:grid;grid-template-columns:130px 1fr 100px;align-items:center;gap:12px;font-size:13px;}
.bar-row .k{color:var(--ink-2);text-align:right;}
.bar-track{height:22px;background:var(--line-2);border-radius:6px;overflow:hidden;}
.bar-fill{height:100%;border-radius:6px;background:var(--bc,#2563eb);display:flex;
  align-items:center;justify-content:flex-end;padding-right:8px;color:#fff;
  font-size:12px;font-weight:600;min-width:36px;}
.bar-row .v{font-size:13px;font-weight:650;color:var(--ink);}
.donut-wrap{display:flex;align-items:center;gap:26px;flex-wrap:wrap;}
.donut{position:relative;flex:0 0 auto;}
.donut .center{position:absolute;inset:0;display:flex;flex-direction:column;
  align-items:center;justify-content:center;}
.donut .center b{font-size:24px;font-weight:700;letter-spacing:-.02em;}
.donut .center span{font-size:11.5px;color:var(--ink-3);}
.legend{display:flex;flex-direction:column;gap:9px;font-size:13px;min-width:230px;flex:1;}
.legend div{display:flex;align-items:center;gap:8px;color:var(--ink-2);}
.legend i{width:10px;height:10px;border-radius:3px;display:inline-block;}
.tl{position:relative;padding-left:26px;margin-top:6px;}
.tl::before{content:"";position:absolute;left:7px;top:8px;bottom:8px;width:2px;background:var(--line);}
.tl-item{position:relative;padding-bottom:18px;}
.tl-item:last-child{padding-bottom:0;}
.tl-item::before{content:"";position:absolute;left:-24px;top:7px;width:12px;height:12px;
  border-radius:50%;background:#fff;border:3px solid var(--c-newcar);}
.tl-item.done::before{background:var(--c-newcar);}
.tl-date{font-size:12.5px;font-weight:700;color:var(--c-newcar);letter-spacing:.02em;margin-bottom:3px;}
.tl-name{font-size:15px;font-weight:650;margin-bottom:3px;}
.tl-desc{font-size:13.5px;color:var(--ink-2);line-height:1.7;}
.insight{background:linear-gradient(135deg,#f8fafc,#eef2f7);border:1px solid #e2e8f0;
  border-radius:var(--radius);padding:22px 24px;margin-bottom:14px;border-left:4px solid var(--c-policy);}
.insight h4{font-size:16px;font-weight:700;margin-bottom:9px;display:flex;align-items:center;gap:9px;}
.insight h4 .no{width:22px;height:22px;border-radius:7px;background:#1e293b;color:#fff;
  font-size:12px;display:flex;align-items:center;justify-content:center;flex:0 0 auto;}
.insight p{font-size:14.5px;color:#334155;line-height:1.8;}
details.src-box{background:var(--card);border-radius:var(--radius);box-shadow:var(--shadow);
  padding:18px 22px;margin-top:14px;}
details.src-box summary{cursor:pointer;font-size:14.5px;font-weight:650;list-style:none;
  display:flex;align-items:center;justify-content:space-between;}
details.src-box summary::-webkit-details-marker{display:none;}
details.src-box summary::after{content:"展开";font-size:12.5px;color:var(--ink-3);font-weight:400;}
details.src-box[open] summary::after{content:"收起";}
table.src{width:100%;border-collapse:collapse;margin-top:16px;font-size:12.5px;}
table.src th{text-align:left;color:var(--ink-3);font-weight:600;padding:8px 10px;
  border-bottom:1px solid var(--line);white-space:nowrap;}
table.src td{padding:8px 10px;border-bottom:1px solid var(--line-2);color:var(--ink-2);vertical-align:top;}
table.src tr:hover td{background:#fafbfc;}
table.src td a{color:var(--c-policy);text-decoration:none;word-break:break-all;}
footer{margin-top:52px;padding-top:22px;border-top:1px solid var(--line);
  font-size:12.5px;color:var(--ink-3);line-height:1.9;}
@media (max-width:640px){
  .hero h1{font-size:25px;}
  .bar-row{grid-template-columns:84px 1fr 72px;font-size:12px;}
  .wrap{padding:0 16px 60px;}
  nav.toc{margin-left:-16px;margin-right:-16px;padding-left:16px;padding-right:16px;}
  .sec-sub{margin-left:0;}
}
"""

JS = r"""
(function(){
  var links=[].slice.call(document.querySelectorAll('nav.toc a'));
  var targets=links.map(function(a){return document.querySelector(a.getAttribute('href'));}).filter(Boolean);
  function onScroll(){
    var y=window.scrollY+110,cur=0;
    targets.forEach(function(t,i){if(t.offsetTop<=y)cur=i;});
    links.forEach(function(a,i){
      var on=(i===cur);
      a.style.background=on?'#1f2329':'#fff';
      a.style.color=on?'#fff':'';
      a.style.borderColor=on?'#1f2329':'';
    });
  }
  window.addEventListener('scroll',onScroll,{passive:true});
  onScroll();
})();
"""


def build(data, date_new, title_prefix):
    year = str(data.get("period_start", "2026"))[:4]
    summary = data.get("summary") or []
    body_sections = data.get("body_sections") or []
    vis = data.get("visual") or {}
    groups = group_sections(body_sections)

    total_items = sum(len(b.get("items") or []) for b in body_sections)

    # ---- 导航
    nav = ['<nav class="toc"><a href="#sum">要点速览</a>']
    for i, (sec, _) in enumerate(groups):
        nav.append('<a href="#s%d">%s %s</a>' % (i + 1, CN_NUM[i] if i < len(CN_NUM) else str(i + 1), esc(sec)))
    if vis.get("insights"):
        nav.append('<a href="#obs">本期观察</a>')
    nav.append('<a href="#src">来源清单</a></nav>')
    nav = "".join(nav)

    # ---- Hero
    hook = vis.get("hook_title") or "%s %s 资讯速览" % (title_prefix, date_new)
    sub = vis.get("hook_sub") or "本期共收录 %d 条资讯，按九大板块编排，每条均标注事件日期与来源。" % total_items
    meta = vis.get("meta") or ["统计窗口 %s.%s" % (year, date_new),
                               "9 大板块 · %d 条资讯" % total_items,
                               "编制 %s" % ("__DATE__")]
    meta_html = "".join("<span>%s</span>" % esc(m) for m in meta)

    # ---- 摘要
    sum_html = []
    for i, s in enumerate(summary, 1):
        t = s.get("title")
        title_line = "<h5>%s</h5>" % esc(t) if t else ""
        sum_html.append('<div class="sum-item"><div class="idx">%d</div><div>%s<p>%s</p></div></div>'
                        % (i, title_line, esc(s.get("body", ""))))
    sum_block = ('<section id="sum" style="--c:#334155"><div class="sec-head">'
                 '<div class="sec-num" style="--c:#334155">&#10022;</div>'
                 '<h2 class="sec-title">要点速览 <span class="sec-count">%d 条</span></h2></div>'
                 '<p class="sec-sub">%s</p><div class="sum-list">%s</div></section>'
                 % (len(summary), esc(vis.get("summary_note", "按重要性排序，每条对应正文中的一条完整资讯。")),
                    "".join(sum_html))) if summary else ""

    # ---- 九大板块
    sec_html, src_rows = [], []
    for i, (sec, blocks) in enumerate(groups):
        _, color = SECTION_COLORS.get(sec, DEFAULT_COLOR)
        cnt = sum(len(b.get("items") or []) for b in blocks)
        part = ['<section id="s%d" style="--c:%s">' % (i + 1, color)]
        part.append('<div class="sec-head"><div class="sec-num">%s</div>'
                    '<h2 class="sec-title">%s <span class="sec-count">%d 条</span></h2></div>'
                    % (CN_NUM[i] if i < len(CN_NUM) else str(i + 1), esc(sec), cnt))
        lead = (vis.get("section_leads") or {}).get(sec)
        part.append('<p class="sec-sub">%s</p>' % esc(lead or ""))

        for blk in blocks:
            items = blk.get("items") or []
            # 注意：变量名不能叫 sub——会覆盖 Hero 的 sub（导语），导致导语渲染为空
            sub_name = (blk.get("subsection") or "").strip()
            if sub_name:
                part.append('<div class="subhead"><span class="dot"></span><h3>%s</h3>'
                            '<span class="n">%d 条</span></div>' % (esc(sub_name), len(items)))
            part.append(render_news(sec, items, color))
            for it in items:
                if it.get("source"):
                    src_rows.append({"section": sec if not sub_name else "%s-%s" % (sec, sub_name),
                                     "title": it.get("title", ""),
                                     "date": it.get("date", ""),
                                     "source": it.get("source")})
        part.append("</section>")
        sec_html.append("".join(part))

    # ---- 增强块
    charts = render_bars(vis.get("bars")) + render_donut(vis.get("donut"))
    tl = render_timeline(vis.get("timeline") or [])
    if tl:
        sec_html.append('<section style="--c:var(--c-newcar)">'
                        '<div class="sec-head"><div class="sec-num">&#9635;</div>'
                        '<h2 class="sec-title">时间轴</h2></div>%s</section>' % tl)

    obs = ""
    if vis.get("insights"):
        obs = ('<section id="obs" style="--c:var(--c-policy)"><div class="sec-head">'
               '<div class="sec-num" style="--c:#1e293b">&#10022;</div>'
               '<h2 class="sec-title">本期观察 <span class="sec-count">%d 点</span></h2></div>'
               '<p class="sec-sub">%s</p>%s</section>'
               % (len(vis["insights"]),
                  esc(vis.get("insights_note", "看完本期资讯后，最值得带走的几个判断。")),
                  render_insights(vis["insights"])))

    src = ""
    if src_rows:
        src = ('<section id="src"><div class="sec-head" style="--c:#334155">'
               '<div class="sec-num" style="--c:#334155">&#8801;</div>'
               '<h2 class="sec-title">来源清单 <span class="sec-count">%d 条</span></h2></div>%s</section>'
               % (len(src_rows), render_sources(src_rows)))

    foot = vis.get("footer_note") or (
        "<b>口径说明</b><br>"
        "1. 统计窗口为 %s.%s；上一期已报道的条目不再重复计入。<br>"
        "2. 企业销量、月度交付、季度/半年财报、当月乘用车产销/渗透率/份额等周期性数据一律不收录，摘要亦不采用。<br>"
        "3. 纯海外视角资讯（海外建厂、出口基地、海外专属车型）不进入「企业要闻」；涉及出海规划的归入「战略规划」。<br>"
        "4. 「新车上市」板块只收全新车系；改款、年款、衍生版本不收录。<br><br>"
        "本页为 docx 正报的可视化阅读版，两者内容一致。" % (year, date_new)
    )

    doc = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>{css}</style>
</head>
<body>
<header class="hero"><div class="hero-inner">
  <div class="eyebrow">{eyebrow}</div>
  <h1>{hook}</h1>
  <p class="sub">{sub}</p>
  <div class="hero-meta">{meta}</div>
</div></header>
<div class="wrap">
{kpi}
{nav}
{summary}
{charts_anchor}
{sections}
{obs}
{src}
<footer>{foot}</footer>
</div>
<script>{js}</script>
</body>
</html>
""".format(
        title=esc(hook),
        css=CSS,
        eyebrow=esc(vis.get("eyebrow", "%s · 周度资讯快报 · 可视化阅读版" % title_prefix)),
        hook=hook,
        sub=esc(sub),
        meta=meta_html,
        kpi=render_kpis(vis.get("kpis")),
        nav=nav,
        summary=sum_block,
        charts_anchor=('<section style="--c:var(--c-macro)"><div class="sec-head">'
                       '<div class="sec-num">&#9636;</div>'
                       '<h2 class="sec-title">关键数据</h2></div>%s</section>' % charts) if charts else "",
        sections="".join(sec_html),
        obs=obs,
        src=src,
        foot=foot,
        js=JS,
    )
    return doc


def main():
    ap = argparse.ArgumentParser(description="周报 report_data.json -> 可视化 HTML")
    ap.add_argument("--data", required=True, help="report_data.json 路径")
    ap.add_argument("--output", required=True, help="输出 HTML 路径")
    ap.add_argument("--date-new", required=True, help='本期日期，如 "09.30-10.06"')
    ap.add_argument("--title-prefix", default="中国汽车产业", help="标题前缀")
    ap.add_argument("--report-date", default="", help="编制日期，如 2026.10.08；缺省用系统当天")
    args = ap.parse_args()

    with open(args.data, "r", encoding="utf-8") as f:
        data = json.load(f)

    report_date = args.report_date
    if not report_date:
        import datetime
        report_date = datetime.date.today().strftime("%Y.%m.%d")

    html_doc = build(data, args.date_new, args.title_prefix)
    html_doc = html_doc.replace("__DATE__", report_date)

    out_dir = os.path.dirname(os.path.abspath(args.output))
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html_doc)

    # 自检
    bad = html_doc.count("\ufffd")
    n_sec = html_doc.count("<section")
    n_news = html_doc.count('class="news"')
    print("[OK] 已生成：%s" % args.output)
    print("     板块数 %d ｜ 资讯卡 %d ｜ 字符数 %d ｜ 乱码字符 %d" % (n_sec, n_news, len(html_doc), bad))
    if bad:
        print("[WARN] 检出 %d 个替换字符，请检查 report_data.json 编码" % bad)
        sys.exit(2)


if __name__ == "__main__":
    main()
