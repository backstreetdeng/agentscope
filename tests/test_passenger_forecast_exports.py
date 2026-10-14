"""Acceptance tests deliberately inspect saved bytes, independently of the builder."""
import io
import json
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from tempfile import TemporaryDirectory
from utils.passenger_forecast_exports import validate_exports, _xlsx_cells


class ForecastExportValidationTests(unittest.TestCase):
    @unittest.skipUnless((Path(__file__).resolve().parents[1] / 'outputs/forecast-integration-selftest-20261010/outputs/2027年乘用车月度预测.xlsx').is_file(), 'Requires the real-business-file integration export')
    def test_saved_workbook_tampering_is_rejected(self):
        root = Path(__file__).resolve().parents[1] / 'outputs/forecast-integration-selftest-20261010'
        payload = json.loads((root / 'working/export_runtime/forecast-export-input.json').read_text(encoding='utf8'))
        source = root / 'outputs/2027年乘用车月度预测.xlsx'
        presentation = root / 'outputs/2027年乘用车月度预测.pptx'
        original = [{'kind': 'spreadsheet', 'path': str(source)}, {'kind': 'presentation', 'path': str(presentation)}]
        self.assertEqual(validate_exports(original, payload['result'])['status'], 'passed')
        with TemporaryDirectory() as directory:
            corrupt = Path(directory) / 'tampered.xlsx'
            with zipfile.ZipFile(source) as reader, zipfile.ZipFile(corrupt, 'w') as writer:
                for item in reader.infolist():
                    content = reader.read(item.filename)
                    if item.filename == 'xl/worksheets/sheet1.xml':
                        document = ET.fromstring(content)
                        ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                        value = document.find('.//s:c[@r="D9"]/s:v', ns)
                        value.text = str(float(value.text) + 1)
                        content = ET.tostring(document, encoding='utf-8', xml_declaration=True)
                    writer.writestr(item, content)
            corrupted = [{'kind': 'spreadsheet', 'path': str(corrupt)}, original[1]]
            report = validate_exports(corrupted, payload['result'])
            self.assertEqual(report['status'], 'failed')
            self.assertFalse(next(c for c in report['checks'] if c['name'] == 'xlsx_month_1_cached_values')['passed'])

    def test_missing_exports_fail(self):
        report = validate_exports([], {'rows': []})
        self.assertEqual(report['status'], 'failed')
        self.assertFalse(next(c for c in report['checks'] if c['name'] == 'required_artifact_kinds')['passed'])

    def test_corrupt_artifact_fails(self):
        with TemporaryDirectory() as directory:
            file = Path(directory) / 'bad.xlsx'
            file.write_bytes(b'not a workbook')
            report = validate_exports([{'kind': 'spreadsheet', 'path': str(file)}], {'rows': []})
            self.assertEqual(report['status'], 'failed')
            self.assertTrue(any(c['name'] == 'spreadsheet_reopen' and not c['passed'] for c in report['checks']))

    def test_cached_formula_and_shared_strings_are_independently_read(self):
        buffer = io.BytesIO()
        ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('xl/sharedStrings.xml', f'<sst xmlns="{ns}"><si><t>业务提供</t></si></sst>')
            archive.writestr('xl/worksheets/sheet1.xml', f'<worksheet xmlns="{ns}"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1"><f>SUM(B2:B3)</f><v>42</v></c><c r="C1" t="e"><v>#REF!</v></c></row></sheetData></worksheet>')
        cells, _ = _xlsx_cells(buffer.getvalue())
        self.assertEqual(cells['A1']['value'], '业务提供')
        self.assertEqual(cells['B1'], {'value': 42.0, 'formula': 'SUM(B2:B3)', 'error': False})
        self.assertTrue(cells['C1']['error'])


if __name__ == '__main__':
    unittest.main()
