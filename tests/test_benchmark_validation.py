"""S5 单测：交叉校验规则库（schema / cells / P0 锚定 / 价格阶梯）。"""
import copy
import unittest

from utils.benchmark_validation import (
    validate_matrix, validate_schema, validate_cells, validate_p0_anchor, validate_price_tiers,
)


def _valid_matrix() -> dict:
    return {
        "run_id": "r1",
        "target_model": "宋PLUS EV",
        "generated_at": "2026-11-02T00:00:00",
        "dimensions": [
            {"name": "纯电续航", "category": "hard_spec", "anchor": "P0"},
            {"name": "整备质量", "category": "hard_spec", "anchor": "P0"},
            {"name": "指导价", "category": "market", "anchor": "P1"},
            {"name": "限时价", "category": "market", "anchor": "P1"},
        ],
        "models": [
            {"name": "宋PLUS EV", "is_target": True, "pool_evidence": ["R001"]},
            {"name": "元PLUS", "is_target": False, "pool_evidence": ["R001"]},
        ],
        "cells": [
            {"model": "宋PLUS EV", "dimension": "纯电续航", "value": "605", "unit": "km",
             "status": "confirmed", "receipt_id": "R001", "as_of": "2026-09-01", "source_tier": "P0", "note": ""},
            {"model": "宋PLUS EV", "dimension": "整备质量", "value": "1885", "unit": "kg",
             "status": "single_source", "receipt_id": "R001", "as_of": "2026-09-01", "source_tier": "P0", "note": ""},
            {"model": "宋PLUS EV", "dimension": "指导价", "value": "16.98", "unit": "万元",
             "status": "confirmed", "receipt_id": "R002", "as_of": "2026-09-01", "source_tier": "P1", "note": ""},
            {"model": "宋PLUS EV", "dimension": "限时价", "value": "15.98", "unit": "万元",
             "status": "single_source", "receipt_id": "R002", "as_of": "2026-09-01", "source_tier": "P1", "note": ""},
        ],
    }


class SchemaTests(unittest.TestCase):
    def test_valid_matrix_passes(self):
        self.assertEqual(validate_schema(_valid_matrix()), [])

    def test_missing_required_field_fails(self):
        m = _valid_matrix()
        del m["generated_at"]
        self.assertTrue(any("generated_at" in e for e in validate_schema(m)))


class CellTests(unittest.TestCase):
    def test_non_na_cell_missing_receipt_fails(self):
        m = _valid_matrix()
        del m["cells"][3]["receipt_id"]
        self.assertTrue(validate_cells(m))

    def test_disputed_cell_needs_conflict_type(self):
        m = _valid_matrix()
        m["cells"][3]["status"] = "disputed"
        m["cells"][3]["note"] = ""
        self.assertTrue(any("disputed" in e for e in validate_cells(m)))

    def test_na_cell_needs_no_receipt(self):
        m = _valid_matrix()
        m["cells"][3]["status"] = "na"
        m["cells"][3]["value"] = None
        del m["cells"][3]["receipt_id"]
        self.assertFalse(any("限时价" in e for e in validate_cells(m)))


class P0AnchorTests(unittest.TestCase):
    def test_hard_param_must_be_p0(self):
        m = _valid_matrix()
        m["cells"][0]["source_tier"] = "P1"
        self.assertTrue(any("纯电续航" in e and "P0" in e for e in validate_p0_anchor(m)))

    def test_insufficient_needs_note(self):
        m = _valid_matrix()
        m["cells"][1]["status"] = "insufficient"
        m["cells"][1]["note"] = ""
        self.assertTrue(any("无申报" in e for e in validate_p0_anchor(m)))

    def test_valid_hard_params_pass(self):
        self.assertEqual(validate_p0_anchor(_valid_matrix()), [])


class PriceTierTests(unittest.TestCase):
    def test_single_price_dimension_fails(self):
        m = _valid_matrix()
        m["dimensions"].append({"name": "价格", "category": "market", "anchor": "P1"})
        self.assertTrue(validate_price_tiers(m))

    def test_tiered_price_passes(self):
        self.assertEqual(validate_price_tiers(_valid_matrix()), [])


class AggregateTests(unittest.TestCase):
    def test_valid_matrix_fully_passes(self):
        self.assertEqual(validate_matrix(_valid_matrix()), [])

    def test_bad_matrix_accumulates_failures(self):
        m = _valid_matrix()
        del m["cells"][0]["receipt_id"]
        m["cells"][0]["source_tier"] = "P1"
        failures = validate_matrix(m)
        self.assertTrue(failures)


if __name__ == "__main__":
    unittest.main()
