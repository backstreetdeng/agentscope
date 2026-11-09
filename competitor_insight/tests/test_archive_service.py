"""BCI-004 · D4 接口 / 原话 / 导出测试。

不依赖路由与 HTTP：直接调用 `ArchiveService` 与 `QuoteService`。
- 模板、受访者列表、档案详情（含三态与 score_source）；
- 生成运行：单人 / 跳过已 ready / 失败项 / 运行锁 / 轮询；
- 导出：xlsx 结构、无来源行文案、评分缺失、md 单人限制、缺档案拒绝；
- 文件后端只验证契约；真实库单独一组，连不上则明确跳过。
"""

from __future__ import annotations

import tempfile
import threading
import time
import unittest
import uuid
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook

from competitor_insight.server import db as db_module
from competitor_insight.server.archive_api import ApiError, ArchiveService
from competitor_insight.server.archive_generator import GenerationError
from competitor_insight.server.archive_store import (
    ArchiveDraft,
    ArchiveFieldRecord,
    FileArchiveStore,
)
from competitor_insight.server.quote_service import QuoteError, QuoteService, escape_like
from competitor_insight.server.template_registry import (
    ARCHIVE_TEMPLATE_ID,
    TemplateRegistry,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REGISTRY = TemplateRegistry(PROJECT_ROOT)
BUNDLE = REGISTRY.load_ready(ARCHIVE_TEMPLATE_ID)
DEFINITION = BUNDLE.definition
SOURCE_MAP = BUNDLE.require_source_map()
DIMENSIONS = DEFINITION["dimensions"]
DIM_INDEX = {dim["id"]: index for index, dim in enumerate(DIMENSIONS)}
SATISFACTION = "satisfaction_score"
NO_SOURCE_DIM = SOURCE_MAP.no_source_dimensions()[0].dimension_id


def build_fields(*, score: float | None = 8.0) -> tuple[ArchiveFieldRecord, ...]:
    fields: list[ArchiveFieldRecord] = []
    for dim in SOURCE_MAP.dimensions:
        if dim.dimension_id == SATISFACTION:
            if score is None:
                fields.append(
                    ArchiveFieldRecord(
                        dimension_id=dim.dimension_id,
                        group_id=dim.group_id,
                        fill_mode="none",
                        no_data_reason="访谈中未给出明确评分",
                        source_ref={"no_source_scope": "interview"},
                        review_status="missing",
                    )
                )
            else:
                fields.append(
                    ArchiveFieldRecord(
                        dimension_id=dim.dimension_id,
                        group_id=dim.group_id,
                        fill_mode="derived",
                        value_text=f"{score} 分",
                        value_json={"score": score, "raw": f"{score} 分"},
                        source_ref={"question_id": 59},
                        evidence_refs=[
                            {
                                "kind": "evidence",
                                "id": f"{dim.dimension_id}-E1",
                                "question_id": 59,
                                "speaker": "受访者",
                                "quote": "综合 8 分。",
                                "source_missing": False,
                            }
                        ],
                    )
                )
            continue

        if dim.fill_mode == "none":
            fields.append(
                ArchiveFieldRecord(
                    dimension_id=dim.dimension_id,
                    group_id=dim.group_id,
                    fill_mode="none",
                    no_data_reason=dim.no_source_reason or "",
                    source_ref={"no_source_scope": "template"},
                    review_status="missing",
                )
            )
            continue

        fields.append(
            ArchiveFieldRecord(
                dimension_id=dim.dimension_id,
                group_id=dim.group_id,
                fill_mode=dim.fill_mode,
                value_text="测试值",
                evidence_refs=[
                    {
                        "kind": "evidence",
                        "id": f"{dim.dimension_id}-E1",
                        "question_id": 20,
                        "speaker": "受访者",
                        "quote": "测试原话",
                        "source_missing": False,
                    }
                ]
                if dim.fill_mode == "llm"
                else [],
            )
        )
    return tuple(fields)


def build_draft(interview_id: str, *, score: float | None = 8.0) -> ArchiveDraft:
    return ArchiveDraft(
        interview_id=interview_id,
        template_id=BUNDLE.template_id,
        template_version=BUNDLE.version,
        template_snapshot=DEFINITION,
        status="ready",
        coverage_required=100.0,
        fields=build_fields(score=score),
        model="deepseek-v4-flash",
        prompt_version="d4-test",
    )


class StubGenerator:
    def __init__(self, fail: set[str] | None = None) -> None:
        self.calls: list[str] = []
        self.fail = fail or set()

    def generate(self, interview_id: str) -> ArchiveDraft:
        self.calls.append(interview_id)
        if interview_id in self.fail:
            raise GenerationError("llm_output_invalid", "模拟模型输出非法")
        return build_draft(interview_id)


class BlockingGenerator(StubGenerator):
    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def generate(self, interview_id: str) -> ArchiveDraft:
        self.started.set()
        self.release.wait(timeout=5)
        return super().generate(interview_id)


class FakeDirectory:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self.calls: list[tuple] = []

    def _filter(self, keyword):
        if not keyword:
            return self.rows
        return [row for row in self.rows if keyword in str(row)]

    def count(self, keyword: str | None = None) -> int:
        return len(self._filter(keyword))

    def list(self, keyword: str | None = None, limit: int = 50, offset: int = 0):
        rows = self._filter(keyword)
        return rows[offset : offset + limit]

    def ids(self) -> list[str]:
        return [row["interview_id"] for row in self.rows]

    def get_many(self, interview_ids):
        wanted = set(interview_ids)
        return {row["interview_id"]: row for row in self.rows if row["interview_id"] in wanted}


class FakeQuotes:
    def __init__(self) -> None:
        self.refreshed: list[tuple[str, list]] = []

    def refresh_refs(self, interview_id: str, refs):
        self.refreshed.append((interview_id, refs))
        return [dict(ref, quote="刷新后的原话", source_missing=False) for ref in refs]


DIRECTORY = FakeDirectory(
    [
        {
            "interview_id": "R001",
            "respondent_code": "R001",
            "city": "广州",
            "vehicle_model": "唐L",
            "purchase_type": "换购",
        },
        {
            "interview_id": "R002",
            "respondent_code": "R002",
            "city": "重庆",
            "vehicle_model": "理想L7",
            "purchase_type": "增购",
        },
    ]
)


class ServiceTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = FileArchiveStore(self._tmp.name)
        self.service = ArchiveService(
            self.store,
            generator=StubGenerator(),
            registry=REGISTRY,
            directory=DIRECTORY,
            background=False,
            max_workers=1,
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()


class TemplateAndRespondentsTest(ServiceTestBase):
    def test_template_matches_definition(self) -> None:
        data = self.service.template()["data"]
        self.assertEqual(data["dimension_count"], 43)
        self.assertEqual(len(data["groups"]), 12)
        self.assertEqual(
            [dim["id"] for dim in data["dimensions"]],
            [dim["id"] for dim in DIMENSIONS],
        )
        self.assertTrue(data["source_map_ready"])

    def test_pending_template_rejected(self) -> None:
        with self.assertRaises(ApiError) as ctx:
            self.service.template("new_model_user_insight")
        self.assertEqual(ctx.exception.code, "template_not_ready")

    def test_unknown_template_rejected(self) -> None:
        with self.assertRaises(ApiError) as ctx:
            self.service.template("not_exists")
        self.assertEqual(ctx.exception.status, 404)

    def test_respondents_merge_archive_status(self) -> None:
        self.store.save_archive(build_draft("R001"))
        payload = self.service.respondents()["data"]
        self.assertEqual(payload["total"], 2)
        first, second = payload["items"]
        self.assertEqual(first["archive"]["status"], "ready")
        self.assertGreater(first["archive"]["completeness"], 0)
        self.assertIsNone(second["archive"])
        self.assertNotIn("name", first)


class DetailTest(ServiceTestBase):
    def test_detail_orders_fields_and_marks_score(self) -> None:
        self.store.save_archive(build_draft("R001"))
        payload = self.service.detail("R001")["data"]
        self.assertEqual(payload["archive"]["status"], "ready")
        self.assertEqual(len(payload["fields"]), 43)
        self.assertEqual(payload["fields"][0]["dimension_id"], DIMENSIONS[0]["id"])

        satisfaction = next(f for f in payload["fields"] if f["dimension_id"] == SATISFACTION)
        self.assertEqual(satisfaction["score_source"], "explicit")
        self.assertEqual(satisfaction["value_json"]["score"], 8.0)

        no_source = next(f for f in payload["fields"] if f["dimension_id"] == NO_SOURCE_DIM)
        self.assertTrue(no_source["display_value"].startswith("本期无来源："))
        self.assertIsNone(no_source["score_source"])

    def test_missing_score_is_marked_missing(self) -> None:
        self.store.save_archive(build_draft("R002", score=None))
        payload = self.service.detail("R002")["data"]
        satisfaction = next(f for f in payload["fields"] if f["dimension_id"] == SATISFACTION)
        self.assertEqual(satisfaction["score_source"], "missing")
        self.assertEqual(satisfaction["no_data_reason"], "访谈中未给出明确评分")

    def test_missing_archive_returns_empty_state(self) -> None:
        payload = self.service.detail("R404")["data"]
        self.assertIsNone(payload["archive"])
        self.assertEqual(payload["fields"], [])

    def test_revision_and_evidence_refresh(self) -> None:
        self.store.save_archive(build_draft("R001"))
        self.store.save_archive(build_draft("R001"))
        quotes = FakeQuotes()
        service = ArchiveService(
            self.store,
            generator=StubGenerator(),
            registry=REGISTRY,
            directory=DIRECTORY,
            quotes=quotes,
            background=False,
        )
        payload = service.detail("R001")["data"]
        self.assertEqual(payload["archive"]["revision"], 2)
        self.assertTrue(quotes.refreshed)
        llm_field = next(f for f in payload["fields"] if f["fill_mode"] == "llm")
        self.assertEqual(llm_field["evidence_refs"][0]["quote"], "刷新后的原话")


class GenerateRunTest(ServiceTestBase):
    def test_template_without_source_map_rejected(self) -> None:
        """缺题项映射的模板（如 nev_user_insight）必须拒绝生成，防止档案写到错误模板名下。"""
        with self.assertRaises(ApiError) as ctx:
            self.service.generate(
                ["R001"], template_id="nev_user_insight", mode="selected", force=True
            )
        self.assertEqual(ctx.exception.code, "template_not_generatable")
        self.assertEqual(len(self.store.list_archives("user_insight_archive").items), 0)

    def test_selected_run_completes(self) -> None:
        result = self.service.generate(["R001", "R002"], mode="selected", force=True)
        run_id = result["data"]["run_id"]
        status = self.service.run_status(run_id)["data"]
        self.assertEqual(status["status"], "completed")
        self.assertEqual((status["done"], status["failed"]), (2, 0))
        self.assertEqual(status["progress"], 100.0)
        self.assertEqual(
            {item["interview_id"]: item["status"] for item in status["items"]},
            {"R001": "done", "R002": "done"},
        )

    def test_ready_archive_is_skipped_without_force(self) -> None:
        self.store.save_archive(build_draft("R001"))
        generator = StubGenerator()
        service = ArchiveService(
            self.store,
            generator=generator,
            registry=REGISTRY,
            directory=DIRECTORY,
            background=False,
        )
        result = service.generate(["R001", "R002"])["data"]
        self.assertEqual((result["total"], result["skipped"]), (1, 1))
        self.assertEqual(generator.calls, ["R002"])

    def test_failed_item_recorded_without_blocking_others(self) -> None:
        generator = StubGenerator(fail={"R002"})
        service = ArchiveService(
            self.store,
            generator=generator,
            registry=REGISTRY,
            directory=DIRECTORY,
            background=False,
        )
        run_id = service.generate(["R001", "R002"], force=True)["data"]["run_id"]
        status = service.run_status(run_id)["data"]
        self.assertEqual(status["status"], "partial")
        items = {item["interview_id"]: item for item in status["items"]}
        self.assertEqual(items["R001"]["status"], "done")
        self.assertEqual(items["R002"]["status"], "failed")
        self.assertEqual(items["R002"]["error_text"], "llm_output_invalid")
        self.assertFalse(self.store.get_archive("R002", BUNDLE.template_id).items)

    def test_run_lock_and_polling(self) -> None:
        generator = BlockingGenerator()
        service = ArchiveService(
            self.store,
            generator=generator,
            registry=REGISTRY,
            directory=DIRECTORY,
            background=True,
        )
        service.generate(["R001"], mode="single", force=True)
        self.assertTrue(generator.started.wait(timeout=3))
        with self.assertRaises(ApiError) as ctx:
            service.generate(["R002"], mode="single", force=True)
        self.assertEqual(ctx.exception.code, "run_in_progress")
        self.assertEqual(ctx.exception.status, 409)

        generator.release.set()
        deadline = time.time() + 5
        while service._active_run is not None and time.time() < deadline:
            time.sleep(0.02)
        self.assertIsNone(service._active_run)

    def test_missing_and_all_modes(self) -> None:
        self.store.save_archive(build_draft("R001"))
        missing = self.service.generate([], mode="missing")["data"]
        self.assertEqual(missing["total"], 1)
        all_run = self.service.generate([], mode="all", force=True)["data"]
        self.assertEqual(all_run["total"], 2)

    def test_unknown_run(self) -> None:
        with self.assertRaises(ApiError) as ctx:
            self.service.run_status(str(uuid.uuid4()))
        self.assertEqual(ctx.exception.code, "run_not_found")

    def test_invalid_mode(self) -> None:
        with self.assertRaises(ApiError):
            self.service.generate(["R001"], mode="whatever")


class ExportTest(ServiceTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.store.save_archive(build_draft("R001"))
        self.store.save_archive(build_draft("R002", score=None))

    def test_xlsx_structure_and_no_source_rows(self) -> None:
        payload = self.service.export(["R001", "R002"])["data"]
        self.assertEqual(payload["format"], "xlsx")
        self.assertTrue(payload["filename"].endswith(".xlsx"))
        self.assertIn("用户洞察档案_", payload["filename"])

        workbook = load_workbook(BytesIO(payload["data"]))
        self.assertEqual(
            workbook.sheetnames, ["洞察档案", "口径与证据", "证据"]
        )
        sheet = workbook["洞察档案"]
        self.assertEqual(sheet.max_row, 2 + len(DIMENSIONS))
        self.assertEqual(sheet.cell(row=2, column=3).value, "R001")
        self.assertEqual(sheet.cell(row=2, column=4).value, "R002")

        no_source_row = 3 + DIM_INDEX[NO_SOURCE_DIM]
        self.assertTrue(
            str(sheet.cell(row=no_source_row, column=3).value).startswith("本期无来源：")
        )

        satisfaction_row = 3 + DIM_INDEX[SATISFACTION]
        self.assertEqual(sheet.cell(row=satisfaction_row, column=3).value, "8.0 分")
        self.assertEqual(
            sheet.cell(row=satisfaction_row, column=4).value,
            "访谈中未给出明确评分",
        )

        evidence = workbook["证据"]
        self.assertGreater(evidence.max_row, 1)
        self.assertEqual(evidence.cell(row=1, column=1).value, "受访者")

    def test_md_single_person(self) -> None:
        payload = self.service.export(["R001"], format="md")["data"]
        text = payload["data"].decode("utf-8")
        self.assertIn("# 用户洞察档案 · R001", text)
        self.assertIn("（广州 · 唐L）", text)
        self.assertIn("## 证据索引", text)
        self.assertIn("本期无来源：", text)
        self.assertTrue(payload["filename"].endswith(".md"))

    def test_md_rejects_multiple(self) -> None:
        with self.assertRaises(ApiError) as ctx:
            self.service.export(["R001", "R002"], format="md")
        self.assertEqual(ctx.exception.code, "md_single_only")

    def test_missing_archive_blocks_export(self) -> None:
        with self.assertRaises(ApiError) as ctx:
            self.service.export(["R001", "R404"])
        self.assertEqual(ctx.exception.code, "archive_missing")
        self.assertEqual(ctx.exception.extra["interview_ids"], ["R404"])

    def test_unsupported_format(self) -> None:
        with self.assertRaises(ApiError) as ctx:
            self.service.export(["R001"], format="xls")
        self.assertEqual(ctx.exception.code, "unsupported_format")


class QuoteServiceUnitTest(unittest.TestCase):
    def test_escape_like(self) -> None:
        self.assertEqual(escape_like("50%_a\\b"), "50\\%\\_a\\\\b")

    def test_invalid_keyword_rejected_before_connecting(self) -> None:
        def boom():
            raise AssertionError("不应连接数据库")

        service = QuoteService(boom)
        for bad in ("", "   ", "x" * 31):
            with self.assertRaises(QuoteError) as ctx:
                service.search("R001", bad)
            self.assertEqual(ctx.exception.code, "invalid_keyword")

    def test_invalid_limit(self) -> None:
        service = QuoteService(lambda: (_ for _ in ()).throw(AssertionError("不应连接数据库")))
        with self.assertRaises(QuoteError):
            service.search("R001", "空间", limit=0)

    def test_empty_refs_skip_database(self) -> None:
        service = QuoteService(lambda: (_ for _ in ()).throw(AssertionError("不应连接数据库")))
        self.assertEqual(service.refresh_refs("R001", []), [])


class RealDatabaseQuoteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            conn = db_module.connect()
        except Exception as exc:  # noqa: BLE001
            raise unittest.SkipTest(f"数据库不可用：{exc}") from exc
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT interview_id FROM user_insight.interview ORDER BY interview_id LIMIT 1")
                row = cur.fetchone()
        finally:
            conn.close()
        if row is None:
            raise unittest.SkipTest("user_insight.interview 无数据")
        cls.interview_id = row[0]

    def test_search_returns_grouped_counts(self) -> None:
        data = QuoteService(db_module.connect).search(self.interview_id, "空间", limit=5)
        self.assertLessEqual(data["total"], 5)
        self.assertEqual(
            set(data["counts"]), {"answer", "evidence", "tag_evidence", "archive"}
        )
        self.assertEqual(data["keyword"], "空间")
        for item in data["items"]:
            self.assertIn("interview_id", item)

    def test_search_without_person_covers_all(self) -> None:
        """未指定受访者时检索全部人：结果不带单人过滤，且 answer/evidence 附带 interview_id。"""
        data = QuoteService(db_module.connect).search(None, "空间", limit=8)
        self.assertLessEqual(data["total"], 8)
        self.assertIsNone(data["interview_ids"])
        persons = {
            item["interview_id"] for item in data["items"] if item["kind"] in ("answer", "evidence")
        }
        for item in data["items"]:
            if item["kind"] in ("answer", "evidence"):
                self.assertTrue(item["interview_id"])
        self.assertGreaterEqual(len(persons), 1)

    def test_search_with_person_list_is_scoped(self) -> None:
        """传多人列表时只返回这些人：answer/evidence 的 interview_id 都在列表内。"""
        ids = [self.interview_id, "R004"]
        data = QuoteService(db_module.connect).search(ids, "空间", limit=8)
        self.assertEqual(data["interview_ids"], ids)
        for item in data["items"]:
            if item["kind"] in ("answer", "evidence"):
                self.assertIn(item["interview_id"], ids)


if __name__ == "__main__":
    unittest.main()
