# -*- coding: utf-8 -*-
"""从 report_data.json 生成《周报_来源.docx》—— 条目标题 → 来源 URL 清单。

与正报一并交付，供人工逐条核验出处（对应 search_prompts.md 迭代重点第 5 条）。

用法：
    python gen_sources.py --data report_data.json \
        --date-new 08.29-09.04 \
        --output "中国汽车产业周度资讯快报2026.0829-0904_来源.docx"
"""
import argparse
import json
import os

from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH


def build(data, date_new, output_path):
    year = str(data.get("period_start", "2026"))[:4]
    period_label = (data["period_start"].replace("-", ".") + "-" + data["period_end"].replace("-", ".")) if data.get("period_start") and data.get("period_end") else year + "." + date_new
    doc = Document()

    # 标题
    h = doc.add_heading(level=0)
    run = h.add_run(f"中国汽车产业周度资讯快报{period_label} — 新闻来源清单")
    run.font.size = Pt(16)

    note = doc.add_paragraph()
    nr = note.add_run("本清单逐条对应正报条目的新闻来源，便于人工核验出处。"
                      "每条来源均已保存抓取记录及事件日期证据，可与正报逐项核验。")
    nr.font.size = Pt(9)
    nr.italic = True

    def emit_section(label, items):
        if not items:
            return
        doc.add_heading(label, level=1)
        for it in items:
            title = it.get('title', '')
            source = it.get('source', '') or '（未提供来源，需复核）'
            p = doc.add_paragraph(style='List Bullet')
            p.add_run(f"事件日：{it.get('event_date', '')}　")
            r1 = p.add_run(f"{title}　")
            r1.bold = True
            r2 = p.add_run(f"— {source}")
            r2.font.size = Pt(9)

    # 摘要来源
    emit_section("摘要", data.get('summary', []))

    # 正文九大章节
    for sec in data.get('body_sections', []):
        label = sec.get('section', '')
        sub = sec.get('subsection', '')
        full = f"{label}（{sub}）" if sub else label
        emit_section(full, sec.get('items', []))

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    doc.save(output_path)
    print(f"来源文档已生成：{output_path}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate weekly report sources docx')
    parser.add_argument('--data', required=True, help='report_data.json 路径')
    parser.add_argument('--date-new', required=True, help='本周日期 MM.DD-MM.DD')
    parser.add_argument('--output', required=True, help='输出 docx 路径')
    args = parser.parse_args()

    with open(args.data, 'r', encoding='utf-8') as f:
        data = json.load(f)
    build(data, args.date_new, args.output)
