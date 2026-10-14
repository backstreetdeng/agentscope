"""Deterministic Office exports and independent OOXML acceptance checks."""
from __future__ import annotations
import io
import json
import math
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
import zipfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEPENDENCIES = Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies'
NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main', 'c': 'http://schemas.openxmlformats.org/drawingml/2006/chart'}


def export_forecast(result: dict, history: dict, output_dir: Path) -> list[dict]:
    """Create both artifacts from precisely the same already-computed result."""
    output_dir = Path(output_dir).resolve()
    working = output_dir.parent / 'working' / 'export_runtime'
    working.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    node = Path(os.environ.get('PASSENGER_EXPORT_NODE', DEPENDENCIES / 'node/bin/node.exe'))
    modules = Path(os.environ.get('PASSENGER_EXPORT_NODE_MODULES', DEPENDENCIES / 'node/node_modules')).resolve()
    if not node.is_file() or not modules.is_dir():
        raise RuntimeError('Bundled Node.js / Office export dependencies are unavailable')
    link = working / 'node_modules'
    if not link.exists():
        if os.name == 'nt':
            subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(modules)], check=True, capture_output=True, text=True)
        else:
            link.symlink_to(modules, target_is_directory=True)
    if link.resolve() != modules:
        raise RuntimeError('Unexpected export dependency link target')
    payload = working / 'forecast-export-input.json'
    payload.write_text(json.dumps({'result': result, 'history': history}, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    command = [str(node), '--max-old-space-size=4096', '--no-concurrent-recompilation', str(PROJECT_ROOT / 'scripts/export_passenger_forecast.mjs'), '--input', str(payload), '--output', str(output_dir), '--modules', str(link)]
    completed = subprocess.run(command, check=False, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=240)
    (working / 'export.log').write_text(completed.stdout + '\n' + completed.stderr, encoding='utf-8')
    if completed.returncode:
        raise RuntimeError(f'Office export failed (exit {completed.returncode}): {completed.stderr[-1800:]}')
    try:
        document = json.loads(next(line for line in reversed(completed.stdout.splitlines()) if line.startswith('{"artifacts":')))
    except (StopIteration, ValueError) as exc:
        raise RuntimeError('Office exporter did not return an artifact manifest') from exc
    artifacts = document['artifacts']
    for artifact in artifacts:
        candidate = Path(artifact['path']).resolve()
        if candidate.parent != output_dir or not candidate.is_file():
            raise RuntimeError('Exporter produced an invalid artifact path')
    return artifacts


def _xlsx_cells(data: bytes, sheet_index: int = 1) -> tuple[dict, list[str]]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if archive.testzip():
            raise ValueError('Corrupt workbook ZIP member')
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings = [''.join(t.text or '' for t in item.findall('.//s:t', NS)) for item in ET.fromstring(archive.read('xl/sharedStrings.xml'))]
        root = ET.fromstring(archive.read(f'xl/worksheets/sheet{sheet_index}.xml'))
        cells = {}
        for cell in root.findall('.//s:c', NS):
            raw = cell.find('s:v', NS)
            value = raw.text if raw is not None else None
            kind = cell.get('t')
            if kind == 's' and value is not None:
                value = strings[int(value)]
            elif kind == 'inlineStr':
                value = ''.join(t.text or '' for t in cell.findall('.//s:t', NS))
            elif value is not None and kind not in ('str', 'e'):
                value = float(value)
            formula = cell.find('s:f', NS)
            cells[cell.get('r')] = {'value': value, 'formula': formula.text if formula is not None else None, 'error': kind == 'e'}
        return cells, archive.namelist()


def validate_exports(artifacts: list[dict], result: dict) -> dict:
    """Reopen bytes independently; reject stale values, formula loss or static charts."""
    checks = []
    def check(name, ok, detail=''):
        checks.append({'name': name, 'passed': bool(ok), 'detail': str(detail)})
    def near(a, b, tol=1e-7):
        return isinstance(a, (int, float)) and math.isfinite(a) and abs(a - b) <= tol
    rows = result.get('rows', [])
    check('twelve_month_result', len(rows) == 12 and [r.get('month') for r in rows] == list(range(1, 13)))
    by_kind = {a.get('kind'): a for a in artifacts}
    check('required_artifact_kinds', set(by_kind) == {'spreadsheet', 'presentation'} and len(artifacts) == 2)
    for kind, artifact in by_kind.items():
        try:
            content = Path(artifact['path']).read_bytes()
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = archive.namelist()
                check(f'{kind}_zip_integrity', archive.testzip() is None)
                external = []
                for name in names:
                    if name.endswith('.rels'):
                        external.extend(r.get('Target') for r in ET.fromstring(archive.read(name)) if r.get('TargetMode') == 'External')
                check(f'{kind}_no_external_dependencies', not external, external)
                if kind == 'spreadsheet':
                    cells, _ = _xlsx_cells(content)
                    sheet_names = [n for n in names if n.startswith('xl/worksheets/sheet') and n.endswith('.xml')]
                    all_cells = [_xlsx_cells(content, i + 1)[0] for i in range(len(sheet_names))]
                    check('xlsx_no_formula_errors', all(not c['error'] for sheet in all_cells for c in sheet.values()))
                    for index, row in enumerate(rows, 9):
                        check(f'xlsx_month_{row["month"]}_inputs', near(cells[f'B{index}']['value'], row['total']) and near(cells[f'C{index}']['value'], row['penetration'] / 100))
                        check(f'xlsx_month_{row["month"]}_formulas', cells[f'D{index}']['formula'] == f'B{index}*C{index}' and cells[f'E{index}']['formula'] == f'B{index}-D{index}')
                        check(f'xlsx_month_{row["month"]}_cached_values', near(cells[f'D{index}']['value'], row['nev']) and near(cells[f'E{index}']['value'], row['traditional']))
                    total = sum(r['total'] for r in rows)
                    nev = sum(r['total'] * r['penetration'] / 100 for r in rows)
                    check('xlsx_annual_closure', near(cells['B21']['value'], result['annual_total']) and cells['B21']['formula'] == 'SUM(B9:B20)')
                    check('xlsx_weighted_penetration', near(cells['C21']['value'], nev / total) and cells['C21']['formula'] == 'D21/B21')
                    check('xlsx_energy_identity', near(cells['D21']['value'] + cells['E21']['value'], total))
                    charts = [n for n in names if n.startswith('xl/') and '/charts/chart' in n and n.endswith('.xml')]
                    check('xlsx_native_charts', len(charts) == 2)
                    formulas = []
                    for name in charts:
                        root = ET.fromstring(archive.read(name))
                        formulas += [f.text for f in root.findall('.//c:f', NS)]
                    check('xlsx_live_chart_references', len(formulas) >= 4 and any('$B$9:$B$20' in f for f in formulas) and any('$C$9:$C$20' in f for f in formulas), formulas)
                elif kind == 'presentation':
                    slides = [n for n in names if n.startswith('ppt/slides/slide') and n.endswith('.xml')]
                    charts = sorted(n for n in names if n.startswith('ppt/charts/chart') and n.endswith('.xml'))
                    embeds = [n for n in names if n.startswith('ppt/embeddings/') and n.endswith('.xlsx')]
                    check('pptx_two_slides', len(slides) == 2)
                    check('pptx_native_editable_charts', len(charts) == 2 and len(embeds) == 2)
                    full_text = ''.join(archive.read(n).decode('utf-8') for n in slides)
                    check('pptx_discloses_draft_and_cutoff', '草稿' in full_text and '未量化' in full_text and '截至' in full_text and str(result['year']) in full_text)
                    expected = [([r['total'] for r in rows], 'total'), ([r['penetration'] / 100 for r in rows], 'penetration')]
                    for (name, (values, label)) in zip(charts, expected):
                        root = ET.fromstring(archive.read(name))
                        actual = [float(v.text) for v in root.findall('.//c:ser/c:val//c:pt/c:v', NS)]
                        check(f'pptx_{label}_chart_cache', len(actual) == 12 and all(near(a, b) for a, b in zip(actual, values)))
                    embedded_values = []
                    for name in embeds:
                        embedded, _ = _xlsx_cells(archive.read(name))
                        embedded_values.append([embedded.get(f'B{i}', {}).get('value') for i in range(2, 14)])
                    for values, label in expected:
                        check(f'pptx_{label}_embedded_workbook', any(len(candidate) == 12 and all(near(a, b) for a, b in zip(candidate, values)) for candidate in embedded_values))
        except Exception as exc:
            check(f'{kind}_reopen', False, f'{type(exc).__name__}: {exc}')
    return {'status': 'passed' if checks and all(c['passed'] for c in checks) else 'failed', 'checks': checks}
