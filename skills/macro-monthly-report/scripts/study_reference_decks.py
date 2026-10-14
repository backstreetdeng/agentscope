"""Read historical PPTX evidence without forecasting or modifying the originals.

Only the Python standard library is required. Paths are explicit so this helper
works in both desktop and isolated web run workspaces.
"""
import argparse
import hashlib
import json
import posixpath
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
      'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
      'c': 'http://schemas.openxmlformats.org/drawingml/2006/chart',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}


def relations(z, part):
    name = posixpath.join(posixpath.dirname(part), '_rels', posixpath.basename(part) + '.rels')
    if name not in z.namelist():
        return {}
    return {x.attrib['Id']: (x.attrib.get('TargetMode'),
            posixpath.normpath(posixpath.join(posixpath.dirname(part), x.attrib['Target'])))
            for x in ET.fromstring(z.read(name))}


def points(node):
    if node is None:
        return []
    return [{'index': int(p.attrib['idx']), 'value': p.findtext('c:v', namespaces=NS)}
            for p in node.findall('.//c:pt', NS)]


def inspect(path):
    data = path.read_bytes()
    with zipfile.ZipFile(path) as z:
        pres = ET.fromstring(z.read('ppt/presentation.xml'))
        rels = relations(z, 'ppt/presentation.xml')
        slides = []
        for number, entry in enumerate(pres.findall('p:sldIdLst/p:sldId', NS), 1):
            part = rels[entry.attrib['{' + NS['r'] + '}id']][1]
            root = ET.fromstring(z.read(part))
            texts = []
            for shape in root.findall('.//p:sp', NS):
                ident = shape.find('p:nvSpPr/p:cNvPr', NS)
                paras = [''.join(t.text or '' for t in p.findall('.//a:t', NS))
                         for p in shape.findall('p:txBody/a:p', NS)]
                if any(paras):
                    texts.append({'shape_id': ident.attrib['id'] if ident is not None else None,
                                  'text': '\n'.join(paras)})
            charts = []
            for mode, target in relations(z, part).values():
                if mode == 'External' or not target.startswith('ppt/charts/') or not target.endswith('.xml'):
                    continue
                chart = ET.fromstring(z.read(target))
                series = []
                for s in chart.findall('.//c:ser', NS):
                    series.append({'name': s.findtext('c:tx/c:strRef/c:strCache/c:pt/c:v', namespaces=NS)
                                   or s.findtext('c:tx/c:v', default='', namespaces=NS),
                                   'categories': points(s.find('c:cat', NS)),
                                   'values': points(s.find('c:val', NS)),
                                   'formulas': [f.text for f in s.findall('.//c:f', NS)]})
                charts.append({'part': target, 'series': series,
                               'relationships': relations(z, target)})
            tables = []
            for table in root.findall('.//a:tbl', NS):
                tables.append([[''.join(t.text or '' for t in cell.findall('.//a:t', NS))
                                for cell in row.findall('a:tc', NS)] for row in table.findall('a:tr', NS)])
            slides.append({'slide': number, 'texts': texts, 'charts': charts, 'tables': tables})
        size = pres.find('p:sldSz', NS)
        return {'file': path.name, 'sha256': hashlib.sha256(data).hexdigest(),
                'size': size.attrib, 'slide_count': len(slides),
                'chart_count': sum(len(s['charts']) for s in slides),
                'embedded_workbooks': sorted(n for n in z.namelist() if n.startswith('ppt/embeddings/')),
                'slides': slides, 'evidence_role': 'user_provided_history_not_latest_official_actual'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inputs', nargs='+', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    decks = [inspect(p) for p in args.inputs]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / 'reference-study.json').write_text(json.dumps(decks, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = []
    for deck in decks:
        lines += ['# ' + deck['file'], f"{deck['slide_count']} slides; {deck['chart_count']} charts", '']
        for s in deck['slides']:
            lines += [f"## P{s['slide']}"] + [f"[{t['shape_id']}] {t['text']}" for t in s['texts']]
            for c in s['charts']:
                lines.append('Chart: ' + c['part'])
                for series in c['series']:
                    lines.append(json.dumps(series, ensure_ascii=False))
            if s['tables']:
                lines.append(json.dumps(s['tables'], ensure_ascii=False))
            lines.append('')
    (args.output_dir / 'reference-study.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps([{k: d[k] for k in ('file', 'slide_count', 'chart_count', 'sha256')} for d in decks], ensure_ascii=False))


if __name__ == '__main__':
    main()
