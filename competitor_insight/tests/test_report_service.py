"""BCI-007 · 报告服务单测（不连数据库、不跑模型）。"""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from competitor_insight.server.report_archive_aggregate import ArchiveAggregator
from competitor_insight.server.report_service import (
    BciReportService,
    ReportError,
    SOURCE_REGISTRY,
    load_outline,
    validate_outline,
)

SERVICE_SOURCE = Path(__file__).resolve().parents[1] / "server/report_service.py"
RENDER_SOURCE = Path(__file__).resolve().parents[1] / "server/report_render_html.py"


def _metric(label, count, n=41, ratio=50.0):
    return {"label": label, "count": count, "n": n, "ratio": ratio}


class FakeAnalysis:
    def __init__(self):
        self._keys = ["fake-a", "fake-b"]
        self.source_counts = {key: {"quant": 41, "interview": 4, "reputation": 120, "miit": 6} for key in self._keys}

    def attack_point(self, key, llm=None, search=None, cache_dir=None):
        return {
            "model": {"key": key, "label": "测试车A"},
            "directions": [
                {
                    "direction": "实际续航",
                    "competitor": "测试车B",
                    "count": 8,
                    "denominator": 60,
                    "ref": "reputation:negative:测试车B:实际续航",
                }
            ],
            "attack": "以真实续航对位竞品续航争议",
            "basis": "竞品负向口碑前 3",
            "source": "llm",
            "error": "",
            "verification": {
                "status": "verified",
                "fetched_at": "2026-11-11",
                "items": [
                    {
                        "direction": "实际续航",
                        "verdict": "confirmed",
                        "text": "仍有车主反馈",
                        "domain": "autohome.com.cn",
                        "url": "https://example.invalid/post",
                        "quote": "高速掉电快",
                    }
                ],
                "line": "竞品口碑现状：实际续航仍有车主反馈（autohome.com.cn）",
            },
            "prompt_version": "test",
            "loss_n": 40,
        }

    def config(self):
        return {
            "version": "test-1",
            "updated": "2026-11-11",
            "default_model": "fake-a",
            "models": [
                {"key": "fake-a", "label": "测试车A", "interview_models": ["测试车A", "测试车A DM-i"]},
                {"key": "fake-b", "label": "测试车B", "interview_models": ["测试车B"]},
            ],
        }

    def models(self):
        return {
            "version": "test-1",
            "default_model": "fake-a",
            "models": [
                {"key": key, "label": self.config()["models"][index]["label"], "sources": self.source_counts[key], "missing_sources": []}
                for index, key in enumerate(self._keys)
            ],
        }

    def analyze(self, key):
        n = 41
        return {
            "model": {"key": key, "label": self.config()["models"][self._keys.index(key)]["label"]},
            "sources": self.source_counts[key],
            "tiles": {
                "profile": {
                    "metrics": [
                        {
                            "key": "age_band",
                            "label": "年龄段",
                            "kind": "distribution",
                            "status": "ok",
                            "n": n,
                            "items": [_metric("26-30岁", 12, n, 29.3), _metric("36-40岁", 11, n, 26.8)],
                        },
                        {"key": "city_tier", "label": "城市级别", "kind": "empty", "status": "empty", "n": n, "items": []},
                    ]
                },
                "attention": {
                    "metrics": [
                        {
                            "key": "attention",
                            "n": n,
                            "answered": n,
                            "status": "ok",
                            "top": [_metric("纯电续航里程", 25, n, 61.0), _metric("空间", 20, n, 48.8)],
                        }
                    ]
                },
                "winloss": {
                    "metrics": [
                        {
                            "key": "q3_23",
                            "n": n,
                            "answered": n,
                            "status": "ok",
                            "items": [_metric("续航长", 21, n, 51.2), _metric("空间大", 18, n, 43.9)],
                            "top": [_metric("续航长", 21, n, 51.2)],
                        },
                        {
                            "key": "win_quotes",
                            "status": "ok",
                            "people": 3,
                            "items": [{"respondent_code": "R001", "quote": "续航够用，一周一充"}],
                        },
                        {
                            "key": "loss_split",
                            "n": 40,
                            "status": "ok",
                            "items": [
                                {
                                    "label": "测试车B",
                                    "count": 15,
                                    "ratio": 37.5,
                                    "reasons": [{"label": "品牌信任", "count": 8, "n": 15, "ratio": 53.3}],
                                }
                            ],
                        },
                    ]
                },
                "satisfaction": {
                    "metrics": [
                        {"key": "overall", "n": n, "answered": n, "mean": 8.24, "status": "ok"},
                        {
                            "key": "dimensions",
                            "n": n,
                            "status": "ok",
                            "top": [{"label": "空间", "mean": 8.6, "answered": n, "n": n}],
                        },
                        {
                            "key": "recommendation",
                            "n": n,
                            "answered": n,
                            "mean": 7.9,
                            "status": "ok",
                            "items": [{"label": "9-10 分", "count": 20, "n": n, "ratio": 48.8}],
                        },
                        {
                            "key": "reputation",
                            "status": "ok",
                            "positive": [{"label": "空间大", "count": 30, "ratio": 12.5}],
                            "negative": [{"label": "实际续航", "count": 11, "ratio": 4.7}],
                            "denominators": {"positive": 240, "negative": 234},
                        },
                    ]
                },
            },
        }


class FakeArchive:
    template_id = "user_insight_archive"
    _version = "v1"

    def template_version(self):
        return self._version

    def __init__(self):
        self._names = {"测试车A": 2, "测试车A DM-i": 2, "测试车B": 3}

    def template(self):
        return {"template_id": self.template_id, "version": self.template_version()}

    def interviews(self, names):
        count = max((self._names.get(name, 0) for name in names), default=0)
        return [
            {
                "archive_id": index + 1,
                "interview_id": f"R00{index + 1}",
                "revision": 1,
                "template_version": self.template_version(),
                "updated_at": "2026-11-11T10:00:00+08:00",
                "respondent_code": f"R00{index + 1}",
                "city": "杭州",
                "vehicle_model": list(names)[0],
            }
            for index in range(count)
        ]

    def interview_total(self, names):
        return 4

    def aggregate(self, names):
        interviews = self.interviews(names)
        total = len(interviews)
        values = {
            "personality_interest_social": [
                {"interview_id": item["interview_id"], "respondent_code": item["respondent_code"], "text": "关注科技与体育", "items": [], "suspect": False}
                for item in interviews
            ],
            "purchase_motivation": [
                {"interview_id": interviews[0]["interview_id"], "respondent_code": interviews[0]["respondent_code"], "text": "换掉高油耗旧车", "items": [], "suspect": False}
            ]
            if interviews
            else [],
            "info_channels": [
                {
                    "interview_id": item["interview_id"],
                    "respondent_code": item["respondent_code"],
                    "text": "",
                    "items": ["抖音", "汽车之家"] if index == 0 else ["抖音"],
                    "suspect": False,
                }
                for index, item in enumerate(interviews)
            ],
            "content_format_preference": [
                {"interview_id": item["interview_id"], "respondent_code": item["respondent_code"], "text": "", "items": ["参数对比"], "suspect": False}
                for item in interviews
            ],
            "conversion_opportunity_risk": [
                {"interview_id": item["interview_id"], "respondent_code": item["respondent_code"], "text": "", "items": ["若支持快充则更倾向"], "suspect": False}
                for item in interviews
            ],
            "satisfaction_points": [],
            "dissatisfaction_points": [],
            "brand_product_service_rank": [],
        }
        dimensions = {name: {"total": total, "filled": len(items), "suspects": 0} for name, items in values.items()}
        return {
            "template_id": self.template_id,
            "template_version": self.template_version(),
            "interviews": interviews,
            "dimensions": dimensions,
            "values": values,
            "coverage": {"archived": total, "interview_total": 4},
        }


class FakeStore:
    def __init__(self):
        self.versions = []
        self.reports = {}
        self.saved = 0
        self.stale = []

    def ensure_report(self, title, model_key, scope, created_by):
        if model_key not in self.reports:
            self.reports[model_key] = f"report-{len(self.reports) + 1}"
        return self.reports[model_key]

    def find_by_fingerprint(self, fingerprint, model_key, outline_version="", renderer=""):
        for row in self.versions:
            if (
                row["data_fingerprint"] == fingerprint
                and row["model_keys"] == [model_key]
                and row["status"] == "valid"
                and row["revision_kind"] == "generate"
                and (row.get("content") or {}).get("outline_version") == outline_version
                and (row.get("content") or {}).get("renderer") == renderer
            ):
                return {
                    "report_version_id": row["report_version_id"],
                    "report_id": row["report_id"],
                    "version_no": row["version_no"],
                    "version_label": row["version_label"],
                    "generated_at": "2026-11-11T12:00:00+08:00",
                    "title": row["title"],
                }
        return None

    def save_version(
        self,
        report_id,
        content,
        html,
        fingerprint,
        snapshot,
        *,
        revision_kind="generate",
        parent_version_id=None,
        patch=None,
        version_label=None,
    ):
        self.saved += 1
        label = version_label or ("v1.0" if self.saved == 1 else f"v2.{self.saved - 2}")
        version = {
            "report_version_id": f"version-{self.saved}",
            "report_id": report_id,
            "version_no": self.saved,
            "version_label": label,
            "parent_version_id": parent_version_id,
            "revision_kind": revision_kind,
            "patch": patch or {},
            "content": content,
            "html": html,
            "data_fingerprint": fingerprint,
            "source_snapshot": snapshot,
            "generated_at": "2026-11-11T12:00:00+08:00",
            "status": "valid",
            "stale_reason": "",
            "model_key": content["models"][0]["key"],
            "model_keys": [model["key"] for model in content["models"]],
            "legacy": False,
            "title": content["title"],
        }
        self.versions.append(version)
        return {
            "report_version_id": version["report_version_id"],
            "report_id": report_id,
            "version_no": version["version_no"],
            "version_label": label,
            "revision_kind": revision_kind,
            "generated_at": version["generated_at"],
        }

    def list_versions(self, model_key=None, limit=50):
        rows = [row for row in self.versions if model_key is None or row["model_key"] == model_key]
        return rows[:limit]

    def version_line(self, report_id):
        return [row for row in self.versions if row["report_id"] == report_id]

    def get_version(self, report_version_id):
        for row in self.versions:
            if row["report_version_id"] == report_version_id:
                return row
        return None

    def mark_stale(self, report_version_id, reason):
        self.stale.append((report_version_id, reason))

    def mark_valid(self, report_version_id):
        for row in self.versions:
            if row["report_version_id"] == report_version_id:
                row["status"] = "valid"
                row["stale_reason"] = ""

    def soft_delete_version(self, report_version_id):
        for row in self.versions:
            if row["report_version_id"] == report_version_id and not row.get("deleted_at"):
                row["deleted_at"] = "2026-11-12T09:00:00+08:00"
                return True
        return False


def make_service(revise_llm=None) -> BciReportService:
    return BciReportService(
        analysis=FakeAnalysis(),
        archive=FakeArchive(),
        store=FakeStore(),
        narrative=False,
        attack_llm=lambda system_prompt, message: "{}",
        revise_llm=revise_llm,
    )


class OutlineContractTest(unittest.TestCase):
    def test_outline_is_valid_and_sources_registered(self):
        outline = load_outline()
        validate_outline(outline)
        blocks = [block for page in outline["pages"] + outline["appendices"] for block in page["blocks"]]
        self.assertGreaterEqual(len(blocks), 12)
        self.assertEqual(len({block["id"] for block in blocks}), len(blocks))
        self.assertTrue(all(block["source"] in SOURCE_REGISTRY for block in blocks))

    def test_outline_rejects_unknown_source(self):
        outline = copy.deepcopy(load_outline())
        outline["pages"][0]["blocks"][0]["source"] = "somewhere.magic"
        with self.assertRaises(ReportError) as ctx:
            validate_outline(outline)
        self.assertEqual(ctx.exception.code, "outline_invalid")

    def test_outline_requires_boolean_required(self):
        outline = copy.deepcopy(load_outline())
        outline["pages"][0]["blocks"][0]["required"] = "yes"
        with self.assertRaises(ReportError):
            validate_outline(outline)


class BuildContentTest(unittest.TestCase):
    def setUp(self):
        self.service = make_service()
        self.content, self.snapshot = self.service.build(["fake-a"])

    def test_every_declared_block_is_rendered(self):
        outline = load_outline()
        declared = {block["id"] for page in outline["pages"] + outline["appendices"] for block in page["blocks"]}
        rendered = {block["id"] for page in self.content["pages"] + self.content["appendices"] for block in page["blocks"]}
        self.assertEqual(declared, rendered)

    def test_table_blocks_carry_denominator(self):
        for page in self.content["pages"]:
            for block in page["blocks"]:
                if block["type"] not in {"table", "bars", "kv"}:
                    continue
                if block.get("data_status") == "unavailable":
                    continue
                if block.get("kind") == "matrix":
                    self.assertTrue(block["rows"])
                    continue
                for model in block["models"]:
                    self.assertIsNotNone(model["n"], f"{block['id']} / {model['label']} 缺分母")

    def test_missing_block_is_recorded_as_gap(self):
        block = next(
            block
            for page in self.content["pages"]
            for block in page["blocks"]
            if block["id"] == "P04.BRAND_ROLE"
        )
        self.assertEqual(block["availability"], "missing")
        self.assertTrue(any(gap["block"] == "P04.BRAND_ROLE" for gap in self.content["gaps"]))

    def test_p07_attack_block_uses_attack_points(self):
        block = next(
            block
            for page in self.content["pages"]
            for block in page["blocks"]
            if block["id"] == "P07.ATTACK"
        )
        model = block["models"][0]
        self.assertEqual(model["status"], "ok")
        self.assertEqual(model["n"], 40)
        self.assertEqual(model["rows"][0][0], "实际续航")
        self.assertIn("autohome.com.cn", model["rows"][0][3])

    def test_labels_come_from_config_not_code(self):
        self.assertIn("测试车A", json.dumps(self.content, ensure_ascii=False))
        for source in (SERVICE_SOURCE, RENDER_SOURCE):
            text = source.read_text(encoding="utf-8")
            for label in ("零跑B10", "铂智3X", "iCAR 超级V23", "海狮05", "钛3"):
                self.assertNotIn(label, text, f"{source.name} 硬编码了车型名 {label}")

    def test_bullets_reference_existing_blocks(self):
        rendered_ids = {block["id"] for page in self.content["pages"] for block in page["blocks"]}
        bullets = next(
            block for page in self.content["pages"] for block in page["blocks"] if block["id"] == "P11.BULLETS"
        )
        for item in bullets["items"]:
            for ref in item["refs"]:
                if ref.startswith("A."):
                    continue
                self.assertIn(ref, rendered_ids)

    def test_fingerprint_is_stable_for_same_data(self):
        content, _ = self.service.build(["fake-a"])
        self.assertEqual(content["data_fingerprint"], self.content["data_fingerprint"])

    def test_fingerprint_changes_when_sample_changes(self):
        baseline = self.content["data_fingerprint"]
        self.service.analysis.source_counts["fake-a"]["quant"] = 42
        content, _ = self.service.build(["fake-a"])
        self.assertNotEqual(content["data_fingerprint"], baseline)


class FingerprintScopeTest(unittest.TestCase):
    def test_outline_and_renderer_upgrade_do_not_change_fingerprint(self):
        service = make_service()
        content, snapshot = service.build(["fake-a"])
        baseline = service.fingerprint(snapshot)
        upgraded = dict(snapshot)
        upgraded["outline"] = {"version": "report-outline/9.9.9"}
        upgraded["renderer"] = "report-render-html/9.9.9"
        self.assertEqual(service.fingerprint(upgraded), baseline)

    def test_upgrade_state_points_outline_and_renderer(self):
        service = make_service()
        state = service.upgrade_state(
            {"outline_version": "report-outline/2.0.0", "renderer": "report-render-html/1.0.0"}
        )
        self.assertTrue(state["available"])
        kinds = [item["kind"] for item in state["items"]]
        self.assertEqual(kinds, ["outline", "renderer"])
        self.assertIn("可重新生成", state["text"])

    def test_fingerprint_rule_declares_exclusions(self):
        rule = BciReportService.fingerprint_rule()
        self.assertEqual(rule["scheme"], "report-fingerprint/2.0")
        self.assertTrue(any("outline" in item for item in rule["excluded"]))
        self.assertTrue(any("renderer" in item for item in rule["excluded"]))


class GenerateIdempotencyTest(unittest.TestCase):
    def test_generate_reuses_same_fingerprint(self):
        service = make_service()
        result1 = service.generate(["fake-a"])
        result2 = service.generate(["fake-a"])
        self.assertTrue(result1["created"])
        self.assertFalse(result2["created"])
        self.assertTrue(result2["reused"])
        self.assertEqual(result1["report_version_id"], result2["report_version_id"])
        self.assertEqual(len(service.store.versions), 1)

    def test_unknown_model_is_rejected(self):
        service = make_service()
        with self.assertRaises(ReportError) as ctx:
            service.generate(["no-such-model"])
        self.assertEqual(ctx.exception.status, 404)

    def test_empty_model_keys_falls_back_to_default(self):
        service = make_service()
        result = service.generate([])
        self.assertEqual(result["title"], "测试车A 竞品用户洞察报告")
        self.assertEqual(result["version_label"], "v1.0")

    def test_multi_model_is_rejected(self):
        service = make_service()
        with self.assertRaises(ReportError) as ctx:
            service.generate(["fake-a", "fake-b"])
        self.assertEqual(ctx.exception.code, "multi_model_not_supported")


class DeterministicRevisionTest(unittest.TestCase):
    def setUp(self):
        self.service = make_service()
        self.base = self.service.generate(["fake-a"])
        self.base_row = self.service.store.get_version(self.base["report_version_id"])

    def test_set_title_creates_child_version(self):
        result = self.service.revise(
            self.base["report_version_id"],
            [{"op": "set_title", "target": {"page": "P04"}, "value": "竞品流失去向"}],
        )
        self.assertEqual(result["version_label"], "v1.1")
        self.assertEqual(result["parent_version_id"], self.base["report_version_id"])
        child = self.service.store.get_version(result["report_version_id"])
        page = next(page for page in child["content"]["pages"] if page["page"] == "P04")
        self.assertEqual(page["title"], "竞品流失去向")
        self.assertEqual(child["revision_kind"], "revise")
        self.assertEqual(child["data_fingerprint"], self.base_row["data_fingerprint"])
        # 父版本不被覆盖
        parent = self.service.store.get_version(self.base["report_version_id"])
        self.assertNotEqual(
            next(page["title"] for page in parent["content"]["pages"] if page["page"] == "P04"),
            "竞品流失去向",
        )

    def test_limit_items_truncates_bullets(self):
        result = self.service.revise(
            self.base["report_version_id"],
            [{"op": "limit_items", "target": {"block": "P11.BULLETS"}, "count": 2}],
        )
        child = self.service.store.get_version(result["report_version_id"])
        bullets = next(
            block for page in child["content"]["pages"] for block in page["blocks"] if block["id"] == "P11.BULLETS"
        )
        self.assertEqual(len(bullets["items"]), 2)

    def test_append_refs_adds_block_reference(self):
        result = self.service.revise(
            self.base["report_version_id"],
            [{"op": "append_refs", "target": {"block": "P04.CHART"}, "refs": ["P04.TOP5", "P11.BULLETS"]}],
        )
        child = self.service.store.get_version(result["report_version_id"])
        block = next(
            block for page in child["content"]["pages"] for block in page["blocks"] if block["id"] == "P04.CHART"
        )
        self.assertEqual(block["refs"], ["P04.TOP5", "P11.BULLETS"])
        self.assertIn("来源引用", child["html"])

    def test_unknown_ref_is_rejected(self):
        with self.assertRaises(ReportError) as ctx:
            self.service.revise(
                self.base["report_version_id"],
                [{"op": "append_refs", "target": {"block": "P04.CHART"}, "refs": ["P99.NOPE"]}],
            )
        self.assertEqual(ctx.exception.code, "target_not_found")

    def test_numeric_violation_is_rejected(self):
        with self.assertRaises(ReportError) as ctx:
            self.service.revise(
                self.base["report_version_id"],
                [{"op": "set_title", "target": {"block": "P04.CHART"}, "value": "续航 99%"}],
            )
        self.assertEqual(ctx.exception.code, "numeric_violation")

    def test_free_text_op_is_rejected(self):
        with self.assertRaises(ReportError) as ctx:
            self.service.revise(
                self.base["report_version_id"],
                [{"op": "rewrite_paragraph", "target": {"page": "P04"}, "value": "随便改"}],
            )
        self.assertEqual(ctx.exception.code, "invalid_request")

    def test_branching_same_version_is_rejected(self):
        self.service.revise(
            self.base["report_version_id"],
            [{"op": "set_title", "target": {"page": "P04"}, "value": "第一改"}],
        )
        with self.assertRaises(ReportError) as ctx:
            self.service.revise(
                self.base["report_version_id"],
                [{"op": "set_title", "target": {"page": "P04"}, "value": "第二改"}],
            )
        self.assertEqual(ctx.exception.code, "revision_conflict")

    def test_compare_marks_changed_block(self):
        child = self.service.revise(
            self.base["report_version_id"],
            [{"op": "set_title", "target": {"page": "P04"}, "value": "竞品流失去向"}],
        )
        diff = self.service.compare(self.base["report_version_id"], child["report_version_id"])
        page = next(item for item in diff["pages"] if item["page"] == "P04")
        self.assertTrue(page["changed"])
        self.assertEqual(diff["target"]["version_label"], "v1.1")
        self.assertTrue(any(item["field"] == "title" for item in page["field_changes"]))

    def test_legacy_report_is_read_only(self):
        self.base_row["legacy"] = True
        with self.assertRaises(ReportError) as ctx:
            self.service.revise(
                self.base["report_version_id"],
                [{"op": "set_title", "target": {"page": "P04"}, "value": "不能改"}],
            )
        self.assertEqual(ctx.exception.code, "legacy_readonly")


class FreeformRewriteTest(unittest.TestCase):
    """自由指令改稿：模型改单页文案，溯源失败重试一次，二次失败拒绝。"""

    @staticmethod
    def _payload(prompt: str) -> dict:
        return json.loads(prompt.split("\n上一次输出被拒")[0])

    def test_rewrites_page_copy_and_records_before_after(self):
        def fake(prompt):
            data = self._payload(prompt)
            number = data["allowed_numbers"][0]
            return json.dumps(
                {
                    "lead": f"本页改为收敛写法，沿用 {number} 这一口径。",
                    "blocks": [{"id": "P04.CHART", "note": "表格说明已按指令收敛。"}],
                    "refs": ["P04.TOP5"],
                },
                ensure_ascii=False,
            )

        service = make_service(revise_llm=fake)
        base = service.generate(["fake-a"])
        instruction = "把导语改得更精炼，表格说明收敛一句"
        result = service.revise(
            base["report_version_id"],
            [{"op": "rewrite_page", "target": {"page": "P04"}, "instruction": instruction}],
        )
        self.assertEqual(result["version_label"], "v1.1")
        child = service.store.get_version(result["report_version_id"])
        page = next(item for item in child["content"]["pages"] if item["page"] == "P04")
        self.assertTrue(page["lead"].startswith("本页改为收敛写法"))
        block = next(item for item in page["blocks"] if item["id"] == "P04.CHART")
        self.assertEqual(block["note"], "表格说明已按指令收敛。")
        record = child["patch"]["rewrites"][0]
        self.assertEqual(record["instruction"], instruction)
        self.assertEqual(record["refs"], ["P04.TOP5"])
        self.assertTrue(any(item["field"] == "lead" for item in record["changes"]))
        self.assertTrue(any(item["block"] == "P04.CHART" and item["field"] == "note" for item in record["changes"]))
        parent = service.store.get_version(base["report_version_id"])
        parent_page = next(item for item in parent["content"]["pages"] if item["page"] == "P04")
        self.assertNotEqual(parent_page["lead"], page["lead"])

    def test_retries_once_when_number_is_not_traceable(self):
        calls = {"n": 0}

        def flaky(prompt):
            calls["n"] += 1
            if calls["n"] == 1:
                return json.dumps({"lead": "新增 98765% 的结论"}, ensure_ascii=False)
            return json.dumps({"lead": "收敛后的结论"}, ensure_ascii=False)

        service = make_service(revise_llm=flaky)
        base = service.generate(["fake-a"])
        result = service.revise(
            base["report_version_id"],
            [{"op": "rewrite_page", "target": {"page": "P04"}, "instruction": "改导语"}],
        )
        self.assertEqual(calls["n"], 2)
        child = service.store.get_version(result["report_version_id"])
        page = next(item for item in child["content"]["pages"] if item["page"] == "P04")
        self.assertEqual(page["lead"], "收敛后的结论")

    def test_rejects_version_when_second_attempt_still_untraceable(self):
        service = make_service(revise_llm=lambda prompt: json.dumps({"lead": "新增 98765% 的结论"}, ensure_ascii=False))
        base = service.generate(["fake-a"])
        with self.assertRaises(ReportError) as ctx:
            service.revise(
                base["report_version_id"],
                [{"op": "rewrite_page", "target": {"page": "P04"}, "instruction": "改导语"}],
            )
        self.assertEqual(ctx.exception.code, "revision_rejected")
        self.assertEqual(len(service.store.versions), 1)

    def test_unavailable_page_only_allows_title(self):
        service = make_service(revise_llm=lambda prompt: json.dumps({"lead": "补写正文"}, ensure_ascii=False))
        base = service.generate(["fake-a"])
        content = service.store.get_version(base["report_version_id"])["content"]
        page = next(item for item in content["pages"] if item.get("data_status") == "unavailable")
        with self.assertRaises(ReportError) as ctx:
            service.revise(
                base["report_version_id"],
                [{"op": "rewrite_page", "target": {"page": page["page"]}, "instruction": "补写正文"}],
            )
        self.assertEqual(ctx.exception.code, "revision_rejected")


class AggregatorUnitTest(unittest.TestCase):
    def test_value_items_flattens_structures(self):
        from competitor_insight.server.report_archive_aggregate import value_items

        self.assertEqual(value_items(["抖音", {"label": "汽车之家"}]), ["抖音", "汽车之家"])
        self.assertEqual(value_items({"items": ["小红书"]}), ["小红书"])
        self.assertEqual(value_items(None, "抖音；朋友推荐"), ["抖音", "朋友推荐"])
        self.assertEqual(value_items(None, "未提及"), [])

    def test_channel_counts_dedupes_alias_and_person(self):
        entries = [
            {"items": ["抖音", "短视频"]},
            {"items": ["抖音"]},
            {"items": ["懂车帝"]},
        ]
        counts = ArchiveAggregator.channel_counts(entries)
        self.assertEqual(counts["抖音"], 2)
        self.assertEqual(counts["懂车帝"], 1)

    def test_interviews_query_is_model_scoped(self):
        captured = {}

        def fake_fetch(sql, params):
            captured["sql"] = sql
            captured["params"] = params
            return []

        aggregator = ArchiveAggregator(fetch=fake_fetch, template_path=Path(__file__).resolve().parents[1] / "templates/user_insight_archive_template.json")
        aggregator.interviews(["测试车A", "测试车A DM-i"])
        self.assertIn("i.vehicle_model = any(%s)", captured["sql"])
        self.assertIn("template_version", captured["sql"])
        self.assertEqual(captured["params"][2], ["测试车A", "测试车A DM-i"])

    def test_aggregate_uses_archive_count_as_denominator(self):
        aggregator = ArchiveAggregator(fetch=lambda sql, params: [], template_path=Path(__file__).resolve().parents[1] / "templates/user_insight_archive_template.json")
        aggregator.interviews = lambda names: [{"archive_id": 1, "interview_id": "R001", "revision": 1, "template_version": "v1", "updated_at": "", "respondent_code": "R001", "city": "", "vehicle_model": "测试车A"}]
        aggregator.interview_total = lambda names: 4
        aggregator._query = lambda sql, params: [(1, "info_channels", "", ["抖音"], "", "valid")]
        result = aggregator.aggregate(["测试车A"])
        self.assertEqual(result["coverage"], {"archived": 1, "interview_total": 4})
        self.assertEqual(result["dimensions"]["info_channels"]["total"], 1)
        self.assertEqual(result["dimensions"]["info_channels"]["filled"], 1)


if __name__ == "__main__":
    unittest.main()
