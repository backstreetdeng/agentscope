"""BCI-004 · D1 source-map 契约测试。

覆盖：
- 真实 source-map 与 43 维模板逐维对齐（集合、顺序、分组）；
- 8 个无来源维全部带 no_source_reason 且未声明任何来源；
- 题号/标签存在性校验可注入真实集合；
- 缺维、重复维、非法题号、分组错位、none 兜底等非法结构被拒绝；
- 模板注册表能加载 archive 模板与其 source-map。

运行：项目根执行 `..\\Scripts\\python.exe -B -m unittest discover -s competitor_insight/tests -t .`
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from competitor_insight.server.source_map import (
    SourceMapError,
    load_source_map,
    load_template_definition,
    validate_against_question_ids,
    validate_against_tag_names,
    validate_against_template,
)
from competitor_insight.server.template_registry import (
    ARCHIVE_TEMPLATE_ID,
    TemplateRegistry,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = PROJECT_ROOT / "competitor_insight" / "templates"
TEMPLATE_PATH = TEMPLATE_DIR / "user_insight_archive_template.json"
SOURCE_MAP_PATH = TEMPLATE_DIR / "user_insight_archive.source-map.json"

NO_SOURCE_IDS = {
    "kol_influence",
    "first_choice_ranking",
    "reception_expectation",
}


def _minimal_template() -> dict:
    return {
        "template_id": "t",
        "version": "v1",
        "groups": [{"id": "g1"}, {"id": "g2"}],
        "dimensions": [
            {"id": "a", "group": "g1"},
            {"id": "b", "group": "g2"},
        ],
    }


def _dimension(dim_id: str, group: str = "g1", **overrides) -> dict:
    base = {
        "dimension_id": dim_id,
        "group_id": group,
        "fill_mode": "tag",
        "scope": "questions",
        "question_ids": [1],
        "tag_names": ["年龄"],
    }
    base.update(overrides)
    return base


def _write_map(directory: Path, dimensions: list[dict]) -> Path:
    path = directory / "x.source-map.json"
    path.write_text(
        json.dumps(
            {
                "source_map_version": 1,
                "template_id": "t",
                "template_version": "v1",
                "dimensions": dimensions,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


class RealSourceMapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.template = load_template_definition(TEMPLATE_PATH)
        cls.source_map = load_source_map(SOURCE_MAP_PATH)

    def test_dimensions_match_template(self) -> None:
        validate_against_template(self.source_map, self.template)
        self.assertEqual(len(self.source_map.dimensions), 43)
        self.assertEqual(
            [d.dimension_id for d in self.source_map.dimensions],
            [d["id"] for d in self.template["dimensions"]],
        )

    def test_fill_mode_distribution(self) -> None:
        counts = self.source_map.fill_mode_counts()
        self.assertEqual(
            counts,
            {"tag": 22, "metadata": 2, "derived": 1, "llm": 15, "none": 3},
        )

    def test_no_source_dimensions_are_documented(self) -> None:
        none_dims = self.source_map.no_source_dimensions()
        self.assertEqual({d.dimension_id for d in none_dims}, NO_SOURCE_IDS)
        for dim in none_dims:
            self.assertTrue(dim.no_source_reason and len(dim.no_source_reason) >= 10, dim.dimension_id)
            self.assertFalse(dim.question_ids, dim.dimension_id)
            self.assertFalse(dim.tag_names, dim.dimension_id)

    def test_question_ids_and_tags_exist(self) -> None:
        # 2026-11-07 实测：user_insight.question 为 1..85 共 85 行
        validate_against_question_ids(self.source_map, range(1, 86))

    def test_question_ids_reject_unknown(self) -> None:
        with self.assertRaises(SourceMapError):
            validate_against_question_ids(self.source_map, range(1, 60))

    def test_tags_reject_unknown(self) -> None:
        with self.assertRaises(SourceMapError):
            validate_against_tag_names(self.source_map, {"年龄"})

    def test_satisfaction_score_is_q59_llm(self) -> None:
        dim = self.source_map.by_id()["satisfaction_score"]
        self.assertEqual(dim.fill_mode, "llm")
        self.assertEqual(dim.question_ids, (59,))


class InvalidSourceMapTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_missing_dimension_rejected(self) -> None:
        path = _write_map(self.dir, [_dimension("a")])
        with self.assertRaisesRegex(SourceMapError, "维度集合不一致"):
            validate_against_template(load_source_map(path), _minimal_template())

    def test_extra_dimension_rejected(self) -> None:
        path = _write_map(self.dir, [_dimension("a"), _dimension("b", "g2"), _dimension("c", "g2")])
        with self.assertRaisesRegex(SourceMapError, "维度集合不一致"):
            validate_against_template(load_source_map(path), _minimal_template())

    def test_duplicate_dimension_rejected(self) -> None:
        path = _write_map(self.dir, [_dimension("a"), _dimension("a")])
        with self.assertRaisesRegex(SourceMapError, "维度重复"):
            load_source_map(path)

    def test_order_must_match_template(self) -> None:
        path = _write_map(self.dir, [_dimension("b", "g2"), _dimension("a")])
        with self.assertRaisesRegex(SourceMapError, "维度顺序"):
            validate_against_template(load_source_map(path), _minimal_template())

    def test_group_mismatch_rejected(self) -> None:
        path = _write_map(self.dir, [_dimension("a", "g2"), _dimension("b", "g2")])
        with self.assertRaisesRegex(SourceMapError, "分组不一致"):
            validate_against_template(load_source_map(path), _minimal_template())

    def test_illegal_question_id_rejected(self) -> None:
        for bad in (0, -3):
            path = _write_map(self.dir, [_dimension("a", question_ids=[bad])])
            with self.assertRaises(SourceMapError):
                load_source_map(path)

    def test_non_integer_question_id_rejected(self) -> None:
        path = _write_map(self.dir, [_dimension("a", question_ids=["20"])])
        with self.assertRaises(SourceMapError):
            load_source_map(path)

    def test_duplicate_question_ids_rejected(self) -> None:
        path = _write_map(self.dir, [_dimension("a", question_ids=[1, 1])])
        with self.assertRaisesRegex(SourceMapError, "重复题号"):
            load_source_map(path)

    def test_none_without_reason_rejected(self) -> None:
        path = _write_map(
            self.dir,
            [_dimension("a", fill_mode="none", question_ids=[], tag_names=[]), _dimension("b", "g2")],
        )
        with self.assertRaisesRegex(SourceMapError, "no_source_reason"):
            load_source_map(path)

    def test_none_with_source_rejected(self) -> None:
        path = _write_map(
            self.dir,
            [
                _dimension("a", fill_mode="none", no_source_reason="题项未询问该维度"),
                _dimension("b", "g2"),
            ],
        )
        with self.assertRaisesRegex(SourceMapError, "不得再声明来源"):
            load_source_map(path)

    def test_tag_without_tag_names_rejected(self) -> None:
        path = _write_map(self.dir, [_dimension("a", tag_names=[]), _dimension("b", "g2")])
        with self.assertRaisesRegex(SourceMapError, "tag_names"):
            load_source_map(path)

    def test_metadata_field_must_be_allowed(self) -> None:
        path = _write_map(
            self.dir,
            [
                _dimension(
                    "a",
                    fill_mode="metadata",
                    question_ids=[],
                    tag_names=[],
                    metadata_fields=["transcript_uri"],
                ),
                _dimension("b", "g2"),
            ],
        )
        with self.assertRaisesRegex(SourceMapError, "metadata_fields"):
            load_source_map(path)

    def test_derived_requires_derivation(self) -> None:
        path = _write_map(
            self.dir,
            [
                _dimension("a", fill_mode="derived", question_ids=[26], tag_names=[]),
                _dimension("b", "g2"),
            ],
        )
        with self.assertRaisesRegex(SourceMapError, "derivation"):
            load_source_map(path)

    def test_interview_scope_rejects_question_ids(self) -> None:
        path = _write_map(
            self.dir,
            [_dimension("a", fill_mode="llm", scope="interview"), _dimension("b", "g2")],
        )
        with self.assertRaisesRegex(SourceMapError, "scope=interview"):
            load_source_map(path)


class TemplateRegistryTest(unittest.TestCase):
    def test_loads_archive_template_with_source_map(self) -> None:
        bundle = TemplateRegistry(PROJECT_ROOT).load_ready(ARCHIVE_TEMPLATE_ID)
        self.assertEqual(bundle.status, "ready")
        self.assertEqual(bundle.dimension_count, 43)
        source_map = bundle.require_source_map()
        self.assertEqual(len(source_map.dimensions), 43)

    def test_validate_all_reports_no_problem_for_ready_templates(self) -> None:
        report = TemplateRegistry(PROJECT_ROOT).validate_all()
        self.assertEqual(report.get(ARCHIVE_TEMPLATE_ID), [])


if __name__ == "__main__":
    unittest.main()
