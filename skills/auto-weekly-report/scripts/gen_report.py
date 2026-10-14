# -*- coding: utf-8 -*-
"""Generate weekly automotive industry report from template + JSON data.

Usage:
    python gen_report.py --template <template.docx> --output <output.docx> \
        --data <report_data.json> --date-old <MM.DD-MM.DD> --date-new <MM.DD-MM.DD>

Example:
    python gen_report.py \
        --template "E:/ASUS/桌面1/中汽数据实习/0报告们/2026年部分周报/4月/中国汽车产业周度资讯快报2026.0509-0515.docx" \
        --output "中国汽车产业周度资讯快报2026.0725-0731.docx" \
        --data report_data.json \
        --date-old "05.09-05.15" --date-new "07.25-07.31"

The script:
1. Copies the template file (preserving all XML structure, styles, images, text boxes)
2. Updates the cover date in text boxes (handles split w:t elements)
3. Removes old summary/TOC/body content (keeps cover page)
4. Rebuilds summary, TOC, and body sections from JSON data
5. Uses page break (w:br type=page) between TOC and body (NOT section break)
6. Result: 2 sections (cover / summary+TOC+body), matching Word-saved reference
"""
import sys
import os
import shutil
import copy
import json
import argparse
from docx import Document
from lxml import etree

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'


def parse_date(date_str):
    """Parse 'MM.DD-MM.DD' into (start_month, start_day, end_month, end_day).

    Leading zeros in month are stripped (e.g. '05' -> '5') because the template
    splits the month as '0' + digit across separate w:t elements.
    Days keep their original format (e.g. '09', '15').
    """
    start, end = date_str.split('-')
    sm, sd = start.split('.')
    em, ed = end.split('.')
    # Strip leading zero from month: '05' -> '5', '08' -> '8'
    sm = str(int(sm))
    em = str(int(em))
    return sm, sd, em, ed


def update_dates(doc, old_date, new_date, start_date=None, end_date=None):
    """Replace complete dates across split runs without touching cover assets."""
    import re
    start_date = start_date or "2026-" + new_date.split("-")[0].replace(".", "-")
    end_date = end_date or "2026-" + new_date.split("-")[1].replace(".", "-")
    replacement = start_date.replace("-", ".") + "-" + end_date.replace("-", ".")
    roots = [doc.element] + [part._element for part in doc.part.related_parts.values()
                            if hasattr(part, "_element") and part.content_type.endswith(("header+xml", "footer+xml"))]
    updated = 0
    for part in roots:
        for para in part.iter(f"{{{W}}}p"):
            nodes = []
            for node in para.iter(f"{{{W}}}t"):
                parent = node.getparent()
                while parent is not None and parent.tag != f"{{{W}}}p":
                    parent = parent.getparent()
                if parent is para:
                    nodes.append(node)
            text = "".join(node.text or "" for node in nodes)
            if re.fullmatch(r'20\d{2}',text.strip()) and any(parent.tag==f"{{{W}}}txbxContent" for parent in para.iterancestors()):
                if nodes:
                    nodes[0].text=start_date[:4]
                    for node in nodes[1:]:node.text=''
                continue
            matches = list(re.finditer(r"20\d{2}\.\d{1,2}\.\d{1,2}\s*[-—]\s*20\d{2}\.\d{1,2}\.\d{1,2}", text))
            for match in reversed(matches):
                position = 0
                first = True
                for node in nodes:
                    original = node.text or ""
                    low, high = position, position + len(original)
                    position = high
                    if high <= match.start() or low >= match.end():
                        continue
                    prefix = original[:max(0, match.start() - low)]
                    suffix = original[max(0, match.end() - low):]
                    node.text = prefix + (replacement if first else "") + suffix
                    first = False
                updated += 1
    if updated < 2:
        raise ValueError("模板封面两个日期区域未完整更新，停止交付。")
    return updated


def generate_report(template_path, output_path, data_path, old_date, new_date, start_date=None, end_date=None):
    # 1. Copy template
    shutil.copy2(template_path, output_path)
    doc = Document(output_path)
    body = doc.element.body
    paras = list(doc.paragraphs)

    # 2. Update dates in text boxes
    update_dates(doc, old_date, new_date, start_date, end_date)

    # 3. Find section breaks and summary start
    sect_breaks = []
    summary_start = None
    for i, p in enumerate(paras):
        pPr = p._element.find(f'{{{W}}}pPr')
        if pPr is not None:
            sect = pPr.find(f'{{{W}}}sectPr')
            if sect is not None:
                sect_breaks.append(copy.deepcopy(sect))
        if p.text.strip() == '重要周度资讯盘点' and summary_start is None:
            summary_start = i

    # Save final sectPr
    final_sect = body.find(f'{{{W}}}sectPr')
    final_sect_copy = copy.deepcopy(final_sect) if final_sect is not None else None

    # 4. Save paragraph templates by scanning template content
    tmpl = {}
    toc_start_idx = None
    body_start_idx = None
    section_titles = {'政策法规', '宏观动态', '行业动态', '企业要闻', '高层动态',
                      '零部件', '战略规划', '新技术/新趋势', '新车上市'}
    subsection_titles = {'豪华品牌车企', '合资品牌车企', '自主品牌车企',
                         '造车新势力及其他车企', '新能源技术', '智能网联技术', '其他关键技术'}

    for i, p in enumerate(paras):
        txt = p.text.strip()
        st = p.style.name
        pf = p.paragraph_format

        if txt == '重要周度资讯盘点' and 'summary_title' not in tmpl:
            tmpl['summary_title'] = copy.deepcopy(p._element)
        elif st == 'Heading 3' and summary_start and i > summary_start \
                and txt != '重要周度资讯盘点' and 'summary_item' not in tmpl:
            if toc_start_idx is None or i < toc_start_idx:
                tmpl['summary_item'] = copy.deepcopy(p._element)

        if txt == '目录' and toc_start_idx is None and summary_start and i > summary_start:
            toc_start_idx = i
            if 'toc_title' not in tmpl:
                tmpl['toc_title'] = copy.deepcopy(p._element)
        elif st == 'toc 1' and 'toc_entry' not in tmpl:
            tmpl['toc_entry'] = copy.deepcopy(p._element)

        if toc_start_idx and body_start_idx is None and st == 'Heading 3':
            if txt in section_titles:
                body_start_idx = i
                if 'section_title' not in tmpl:
                    tmpl['section_title'] = copy.deepcopy(p._element)

        if body_start_idx and i > body_start_idx and st == 'Heading 3':
            if txt in subsection_titles:
                if 'subsection_title' not in tmpl:
                    tmpl['subsection_title'] = copy.deepcopy(p._element)
            elif txt not in section_titles:
                if 'item_heading' not in tmpl:
                    tmpl['item_heading'] = copy.deepcopy(p._element)

        if body_start_idx and i > body_start_idx and st == 'Normal' \
                and txt and pf.first_line_indent and 'body_text' not in tmpl:
            tmpl['body_text'] = copy.deepcopy(p._element)

    required = {'summary_title', 'summary_item', 'toc_title', 'toc_entry', 'section_title', 'subsection_title', 'item_heading', 'body_text'}
    if summary_start is None or required - set(tmpl):
        raise ValueError('模板结构不完整：' + str(required - set(tmpl)))
    print(f"Templates found: {list(tmpl.keys())}")
    print(f"Section breaks found: {len(sect_breaks)}")

    # 5. Helper functions
    def mk(key, text):
        elem = copy.deepcopy(tmpl[key])
        pPr = elem.find(f'{{{W}}}pPr')
        if pPr is not None:
            sect = pPr.find(f'{{{W}}}sectPr')
            if sect is not None:
                pPr.remove(sect)
        for child in list(elem):
            if child.tag != f'{{{W}}}pPr':
                elem.remove(child)
        if key in {'summary_title', 'summary_item'}:
            if pPr is None:
                pPr = etree.SubElement(elem, f'{{{W}}}pPr'); elem.insert(0, pPr)
            outline = pPr.find(f'{{{W}}}outlineLvl')
            if outline is None: outline = etree.SubElement(pPr, f'{{{W}}}outlineLvl')
            outline.set(f'{{{W}}}val', '9')
        if key in {'section_title', 'subsection_title', 'item_heading'}:
            if pPr is None:
                pPr = etree.SubElement(elem, f'{{{W}}}pPr'); elem.insert(0, pPr)
            outline = pPr.find(f'{{{W}}}outlineLvl')
            if outline is None: outline = etree.SubElement(pPr, f'{{{W}}}outlineLvl')
            outline.set(f'{{{W}}}val', {'section_title': '0', 'subsection_title': '1', 'item_heading': '2'}[key])
        if pPr is None:
            pPr = etree.SubElement(elem, f'{{{W}}}pPr'); elem.insert(0,pPr)
        for property_name in ('keepLines','widowControl'):
            node=pPr.find(f'{{{W}}}'+property_name)
            if node is None:node=etree.SubElement(pPr,f'{{{W}}}'+property_name)
            node.set(f'{{{W}}}val','1')
        if key in {'summary_title','summary_item','toc_title','section_title','subsection_title','item_heading'}:
            node=pPr.find(f'{{{W}}}keepNext')
            if node is None:node=etree.SubElement(pPr,f'{{{W}}}keepNext')
            node.set(f'{{{W}}}val','1')
        if key=='toc_title':
            node=pPr.find(f'{{{W}}}pageBreakBefore')
            if node is None:node=etree.SubElement(pPr,f'{{{W}}}pageBreakBefore')
            node.set(f'{{{W}}}val','1')
        r = etree.SubElement(elem, f'{{{W}}}r')
        orig_runs = tmpl[key].findall(f'{{{W}}}r')
        if orig_runs:
            rPr = orig_runs[0].find(f'{{{W}}}rPr')
            if rPr is not None:
                r.insert(0, copy.deepcopy(rPr))
        t = etree.SubElement(r, f'{{{W}}}t')
        t.text = text
        t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
        return elem

    def add_sect(para_elem, sect_tpl):
        pPr = para_elem.find(f'{{{W}}}pPr')
        if pPr is None:
            pPr = etree.SubElement(para_elem, f'{{{W}}}pPr')
            para_elem.insert(0, pPr)
        pPr.append(copy.deepcopy(sect_tpl))

    def ins(elem):
        fs = body.find(f'{{{W}}}sectPr')
        if fs is not None:
            body.insert(list(body).index(fs), elem)
        else:
            body.append(elem)

    # 6. Remove old content (keep cover paras only)
    cover_ids = set(id(p._element) for p in paras[:summary_start])
    for child in list(body):
        if child.tag == f'{{{W}}}p' and id(child) not in cover_ids:
            body.remove(child)
    old_sect = body.find(f'{{{W}}}sectPr')
    if old_sect is not None:
        body.remove(old_sect)

    # 7. Add section break after last cover para
    if sect_breaks:
        last_cover_pPr = paras[summary_start - 1]._element.find(f'{{{W}}}pPr')
        has_sect = last_cover_pPr is not None and last_cover_pPr.find(f'{{{W}}}sectPr') is not None
        if not has_sect:
            add_sect(paras[summary_start - 1]._element, sect_breaks[0])

    # 8. Load data and build document
    with open(data_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Summary
    ins(mk('summary_title', '重要周度资讯盘点'))
    for item in data['summary']:
        ins(mk('summary_item', item['title']))
        if item['body']:
            ins(mk('body_text', item['body']))

    # TOC
    ins(mk('body_text', ''))
    ins(mk('toc_title', '目录'))
    field = mk('body_text', '')
    r = field.find(f'{{{W}}}r')
    begin = etree.SubElement(r, f'{{{W}}}fldChar'); begin.set(f'{{{W}}}fldCharType', 'begin')
    instruction = etree.SubElement(r, f'{{{W}}}instrText'); instruction.text = ' TOC \\o "1-3" \\h \\z \\u '
    separator = etree.SubElement(r, f'{{{W}}}fldChar'); separator.set(f'{{{W}}}fldCharType', 'separate')
    ins(field)
    for entry in data['toc']:
        ins(mk('toc_entry', entry))
    ending = mk('body_text', '')
    end = etree.SubElement(ending.find(f'{{{W}}}r'), f'{{{W}}}fldChar'); end.set(f'{{{W}}}fldCharType', 'end')
    ins(ending)

    # Page break before body (NOT section break - 2 sections only)
    sep = mk('body_text', '')
    r = sep.find(f'{{{W}}}r')
    if r is not None:
        br = etree.SubElement(r, f'{{{W}}}br')
        br.set(f'{{{W}}}type', 'page')
    ins(sep)
    ins(mk('body_text', ''))  # empty spacer paragraph

    # Body sections
    cur_section = None
    for sec in data['body_sections']:
        if sec['section'] != cur_section:
            ins(mk('section_title', sec['section']))
            cur_section = sec['section']
        if sec['subsection']:
            ins(mk('subsection_title', sec['subsection']))
        for item in sec['items']:
            ins(mk('item_heading', item['title']))
            if item['body']:
                ins(mk('body_text', item['body']))

    # Re-add final sectPr
    if final_sect_copy is not None:
        body.append(final_sect_copy)

    # Update the real TOC when opened in Word; never invent page numbers.
    settings = doc.settings.element
    update = settings.find(f'{{{W}}}updateFields')
    if update is None: update = etree.SubElement(settings, f'{{{W}}}updateFields')
    update.set(f'{{{W}}}val', 'true')
    doc.save(output_path)
    print(f"\nDocument saved: {output_path}")
    print(f"Total paragraphs: {len(doc.paragraphs)}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate weekly automotive report')
    parser.add_argument('--template', required=True, help='Template .docx path')
    parser.add_argument('--output', required=True, help='Output .docx path')
    parser.add_argument('--data', required=True, help='report_data.json path')
    parser.add_argument('--date-old', required=True, help='Old date MM.DD-MM.DD (e.g. 05.09-05.15)')
    parser.add_argument('--date-new', required=True, help='New date MM.DD-MM.DD (e.g. 07.25-07.31)')
    parser.add_argument('--start-date', default=None)
    parser.add_argument('--end-date', default=None)
    args = parser.parse_args()

    generate_report(args.template, args.output, args.data, args.date_old, args.date_new, args.start_date, args.end_date)
