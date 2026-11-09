"""BCI-004 · D2 存储层测试。

覆盖：
- 同模板同版本重跑 → revision 递增、旧档案 stale、不覆盖；
- 无来源维必须带 no_data_reason，非法字段整份拒绝且不留文件；
- 查询三态：0 行 / 1 行 / 多行不混淆；
- 文件后端与数据库后端语义一致（DB 不可用时跳过，不冒充通过）。
"""

from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path

from competitor_insight.server import db as db_module
from competitor_insight.server.archive_store import (
    ArchiveDraft,
    ArchiveFieldRecord,
    ArchiveStoreError,
    FileArchiveStore,
    PostgresArchiveStore,
    RunRecord,
    build_query_result,
)
from competitor_insight.server.source_map import load_source_map

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_MAP_PATH = PROJECT_ROOT / "competitor_insight" / "templates" / "user_insight_archive.source-map.json"
TEMPLATE_ID = "user_insight_archive"
TEMPLATE_VERSION = "v1"


def build_fields() -> tuple[ArchiveFieldRecord, ...]:
    source_map = load_source_map(SOURCE_MAP_PATH)
    fields = []
    for dim in source_map.dimensions:
        if dim.fill_mode == "none":
            fields.append(
                ArchiveFieldRecord(
                    dimension_id=dim.dimension_id,
                    group_id=dim.group_id,
                    fill_mode="none",
                    no_data_reason=dim.no_source_reason or "",
                )
            )
        else:
            fields.append(
                ArchiveFieldRecord(
                    dimension_id=dim.dimension_id,
                    group_id=dim.group_id,
                    fill_mode=dim.fill_mode,
                    value_text="测试值",
                    evidence_refs=[{"kind": "evidence", "id": f"{dim.dimension_id}-E1", "quote": "测试原话"}]
                    if dim.fill_mode == "llm"
                    else [],
                )
            )
    return tuple(fields)


def build_draft(interview_id: str, status: str = "ready") -> ArchiveDraft:
    return ArchiveDraft(
        interview_id=interview_id,
        template_id=TEMPLATE_ID,
        template_version=TEMPLATE_VERSION,
        template_snapshot={"template_id": TEMPLATE_ID, "dimensions": 43},
        status=status,
        coverage_required=79.07,
        fields=build_fields(),
        model="deepseek-v4-flash",
        prompt_version="d2-test",
    )


class QueryResultTest(unittest.TestCase):
    def test_three_states(self) -> None:
        self.assertEqual(build_query_result([], expected=3).status, "failed")
        self.assertEqual(build_query_result([1], expected=3).status, "partial")
        self.assertEqual(build_query_result([1, 2, 3], expected=3).status, "success")
        self.assertEqual(build_query_result([], expected=None).status, "success")

    def test_partial_is_not_rendered_as_zero(self) -> None:
        result = build_query_result([1], expected=2)
        self.assertEqual(result.hit, 1)
        self.assertEqual(result.expected, 2)
        self.assertEqual(result.to_dict()["status"], "partial")


class FileStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = FileArchiveStore(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_rerun_overwrites_in_place(self) -> None:
        """覆盖语义（用户 2026-11-09 拍板）：重跑原地覆盖，revision 不变，不留修订。"""
        first = self.store.save_archive(build_draft("R900"))
        second = self.store.save_archive(build_draft("R900", status="partial"))
        self.assertEqual((first.revision, second.revision), (1, 1))

        latest = self.store.get_archive("R900", TEMPLATE_ID)
        self.assertEqual(latest.items[0].revision, 1)
        self.assertEqual(latest.items[0].status, "partial")

        list_all = self.store.list_archives(TEMPLATE_ID)
        self.assertEqual([item.revision for item in list_all.items], [1])
        self.assertEqual(len(list_all.items), 1)

    def test_missing_archive_is_failed_not_zero(self) -> None:
        result = self.store.get_archive("R-none", TEMPLATE_ID)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.hit, 0)
        self.assertTrue(result.reasons)

    def test_invalid_field_writes_nothing(self) -> None:
        draft = build_draft("R901")
        broken = ArchiveFieldRecord(dimension_id="x", group_id="g", fill_mode="none")
        bad = ArchiveDraft(
            interview_id=draft.interview_id,
            template_id=draft.template_id,
            template_version=draft.template_version,
            template_snapshot=draft.template_snapshot,
            status=draft.status,
            coverage_required=draft.coverage_required,
            fields=(*draft.fields, broken),
        )
        with self.assertRaises(ArchiveStoreError):
            self.store.save_archive(bad)
        self.assertFalse(self.store.get_archive("R901", TEMPLATE_ID).items)

    def test_list_filters_status(self) -> None:
        self.store.save_archive(build_draft("R902", status="ready"))
        self.store.save_archive(build_draft("R903", status="partial"))
        partial = self.store.list_archives(TEMPLATE_ID, status="partial")
        self.assertEqual([item.interview_id for item in partial.items], ["R903"])
        self.assertEqual(self.store.list_archives(TEMPLATE_ID, status="partial").hit, 1)
        self.assertEqual(self.store.list_archives(TEMPLATE_ID, expected=1).status, "partial")

    def test_run_lifecycle(self) -> None:
        run_id = str(uuid.uuid4())
        self.store.create_run(
            RunRecord(
                run_id=run_id,
                template_id=TEMPLATE_ID,
                template_version=TEMPLATE_VERSION,
                mode="single",
                request_json={"interviews": ["R900"]},
                status="queued",
                total=1,
            )
        )
        self.store.update_run_item(run_id, "R900", "running")
        self.store.update_run_item(run_id, "R900", "done")
        self.store.update_run(run_id, status="completed", done=1)
        result = self.store.get_run(run_id)
        self.assertEqual(result.status, "success")
        self.assertEqual(result.items[0]["run"]["status"], "completed")
        self.assertEqual(result.items[0]["items"][0]["status"], "done")


class PostgresStoreTest(unittest.TestCase):
    """真实库测试：bci schema 不可用时明确跳过，不算通过。"""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.conn_factory = staticmethod(db_module.connect)
            conn = db_module.connect()
        except Exception as exc:  # noqa: BLE001
            raise unittest.SkipTest(f"数据库不可用：{exc}") from exc
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_namespace WHERE nspname = 'bci'")
                if cur.fetchone() is None:
                    raise unittest.SkipTest("bci schema 尚未创建")
        finally:
            conn.close()

    def setUp(self) -> None:
        self.store = PostgresArchiveStore(self.conn_factory)
        self.interview_id = f"__d2test_{uuid.uuid4().hex[:8]}__"

    def tearDown(self) -> None:
        conn = self.conn_factory()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM bci.archive WHERE interview_id = %s", (self.interview_id,))
                cur.execute("DELETE FROM bci.archive_run WHERE template_id = %s AND request_json->>'probe' = %s", (TEMPLATE_ID, self.interview_id))
            conn.commit()
        finally:
            conn.close()

    def test_save_and_read_back(self) -> None:
        first = self.store.save_archive(build_draft(self.interview_id))
        second = self.store.save_archive(build_draft(self.interview_id, status="partial"))
        self.assertEqual((first.revision, second.revision), (1, 1))

        latest = self.store.get_archive(self.interview_id, TEMPLATE_ID)
        self.assertEqual(latest.status, "success")
        record = latest.items[0]
        self.assertEqual(record.revision, 1)
        self.assertEqual(len(record.fields), 43)
        self.assertEqual(record.status, "partial")

    def test_missing_returns_failed(self) -> None:
        result = self.store.get_archive("__not_exists__", TEMPLATE_ID)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.hit, 0)


if __name__ == "__main__":
    unittest.main()
