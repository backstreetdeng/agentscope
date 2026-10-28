"""Tests for missing/duplicate data and cutoff handling using an isolated workbook."""
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook
from integrations.chronos2_data import ALL_PROVINCES, read_workbook


class WorkbookValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'data.xlsx'
        self.book = Workbook()
        self.sheet = self.book.active
        self.sheet.append(['标题', None, None, '年', '月', '使用省份', '新能源类型', '数量'])

    def tearDown(self):
        self.book.close()
        self.tmp.cleanup()

    def add(self, year, month, province, value):
        self.sheet.append([None, None, None, year, month, province, '纯电动', value])

    def load(self):
        self.book.save(self.path)
        return read_workbook(self.path)

    def test_duplicate_is_rejected(self):
        self.add(2025, 1, '甲', 3); self.add(2025, 1, '甲', 4)
        with self.assertRaisesRegex(ValueError, '重复'): self.load()

    def test_missing_month_breaks_contiguous_history(self):
        for month in (1, 2, 4, 5): self.add(2025, month, '甲', month)
        series = self.load().series('甲', '纯电动')
        self.assertEqual([month for month, _ in series], ['2025-04', '2025-05'])

    def test_missing_combination_is_zero_in_present_month(self):
        self.add(2025, 1, '甲', 1); self.add(2025, 2, '乙', 2)
        self.assertEqual(self.load().series('甲', '纯电动'), [('2025-01', 1), ('2025-02', 0)])

    def test_national_zero_fills_missing_combinations(self):
        for i in range(31): self.add(2025, 1, str(i), i)
        for i in range(30): self.add(2025, 2, str(i), i)
        data = self.load()
        self.assertEqual(data.series(ALL_PROVINCES, '纯电动', '2025-01'), [('2025-01', 465.0)])
        self.assertEqual(data.series(ALL_PROVINCES, '纯电动')[-1], ('2025-02', 435.0))

    def test_invalid_numbers_rejected(self):
        self.add(2025, 1, '甲', -1)
        with self.assertRaisesRegex(ValueError, '非负有限'): self.load()


if __name__ == '__main__': unittest.main()
