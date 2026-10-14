"""Cross-run evidence reuse mechanics; synthetic fixtures are not live acceptance."""
import asyncio
from copy import deepcopy
from datetime import date
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

PATH = Path(__file__).resolve().parents[1] / "skills/macro-monthly-report/scripts/macro_sources.py"
SPEC = importlib.util.spec_from_file_location("macro_reuse_test", PATH)
source = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(source)


def request(identifier="pmi", alias="PMI"):
    return {"id": identifier, "series_name": alias, "definition": "中国制造业" + alias,
            "definition_aliases": [alias], "unit": "指数", "frequency": "monthly",
            "source_domains": ["stats.gov.cn"], "original_publisher_domains": ["stats.gov.cn"],
            "query": "制造业PMI 原始统计数据", "template_latest_period": "2026-07", "history_count": 3}


def body(month=9, alias="PMI", suffix="good", value=49.4):
    raw = (f'<meta name="PublishDate" content="2026-{month:02d}-30">'
           '<p>中国制造业PMI统计发布</p><table><tr><th>时期</th><th>' + alias + '</th></tr>'
           f'<tr><td>2026年{month}月</td><td>{value}</td></tr></table>')
    page = source.parse_page(raw, f"https://www.stats.gov.cn/{suffix}.html")
    return {**page, "receipt_id": "source-" + source._hash(page["url"])[:16],
            "text_sha256": source.hashlib.sha256(page["text"].encode()).hexdigest(),
            "fetch_provider": "direct-public-publisher"}


def metadata(run, requests, month="2026-09", cutoff="2026-10-04", status="needs_repair", delivery="public_draft"):
    source._save(run / "run-state.json", {"run_id": run.name, "skill_id": "macro-monthly-report",
                 "status": status, "package_hash": "previous-package-version", "delivery_mode": delivery})
    source._save(run / "inputs/request.json", {"report_month": month, "cutoff_date": cutoff, "delivery_mode": delivery})
    source._save(run / "working/template-contract.json", {"source_requests": requests})


def donor(archive, reqs, *, pages=None, successful=None, name="macro-20261004-100000-00000001",
          month="2026-09", cutoff="2026-10-04", package=True, delivery="public_draft"):
    run = archive / name
    metadata(run, reqs, month, cutoff, delivery=delivery)
    pages = pages or [body()]
    successful = {req["id"] for req in reqs} if successful is None else set(successful)
    observations = []
    for page in pages:
        source._save(run / "working/macro-sources/pages" / (source._hash(page["url"]) + ".json"), page)
        for req in reqs:
            if req["id"] not in successful:
                continue
            for item in source._table_candidates(page, [req]):
                try:
                    observations.append(source.validate_observation(source._canonical_table_candidate(item, page), req, page,
                                                                    date.fromisoformat(cutoff), month))
                except ValueError:
                    pass
    saved = {"report_month": month, "cutoff_date": cutoff, "evidence_observations": observations,
             "request_status": {req["id"]: {"status": "verified" if req["id"] in successful else "missing"} for req in reqs},
             "coverage": {"required": len(reqs), "verified": len(successful)}}
    if package:
        source._save(run / "working/data-package.json", saved)
    else:
        source._save(run / "working/macro-sources/extractions/batch.json", {"observations": observations})
    return run


class MacroReuseTest(unittest.IsolatedAsyncioTestCase):
    async def collect(self, archive, reqs, *, month="2026-09", cutoff="2026-10-05", draft=True, directory=None, fetch=None):
        current = archive / "macro-20261005-100000-ffffffff"
        metadata(current, reqs, month, cutoff, status="running", delivery="public_draft" if draft else "formal")
        if directory is None:
            directory = {"by_request": {req["id"]: {"items": [{"url": body()["url"]}]} for req in reqs}}
        discover = AsyncMock(return_value=directory)
        fetch = fetch or AsyncMock(return_value=body())
        search = AsyncMock(return_value={"items": []})
        progress = AsyncMock()
        with patch.object(source, "_official_discovery", discover), patch.object(source, "_fetch_page", fetch), \
             patch.object(source, "_search_candidates", search), \
             patch.object(source, "_extract_page_observations", AsyncMock(return_value=[])):
            result = await source.collect_sources(month, cutoff, reqs, current, public_draft=draft,
                                                  reuse_root=archive, progress=progress)
        return result, discover, fetch, search, progress, current

    async def test_99_of_134_reused_only_35_pending_and_donor_is_unchanged(self):
        reqs = [request("metric-" + str(index)) for index in range(134)]
        with TemporaryDirectory() as folder:
            archive = Path(folder)
            previous = donor(archive, reqs, successful={item["id"] for item in reqs[:99]})
            original = {path.relative_to(previous).as_posix(): path.read_bytes() for path in previous.rglob("*") if path.is_file()}
            result, discover, fetch, _, progress, current = await self.collect(archive, reqs)
            self.assertEqual(result["source_reuse"]["reused"], 99)
            self.assertEqual(result["source_reuse"]["pending"], 35)
            self.assertEqual({item["id"] for item in discover.await_args.args[0]}, {item["id"] for item in reqs[99:]})
            self.assertEqual(result["coverage"], {"required": 134, "verified": 134})
            self.assertEqual(fetch.await_count, 1)  # remaining series share one release
            self.assertTrue(any("复用 99/134" in call.args[0] and "补跑 35" in call.args[0] for call in progress.await_args_list))
            self.assertEqual(original, {path.relative_to(previous).as_posix(): path.read_bytes() for path in previous.rglob("*") if path.is_file()})
            receipts = [json.loads(path.read_text(encoding="utf-8")) for path in (current / "working/macro-sources/pages").glob("*.json")]
            replay = source.verify_source_corroboration(result, {"source_requests": reqs}, {item["receipt_id"]: item for item in receipts})
            self.assertEqual(len(replay["observations"]), 134)
            self.assertEqual(replay["issues"], [])

    async def test_all_verified_does_not_discover_search_fetch_or_call_model(self):
        with TemporaryDirectory() as folder:
            archive = Path(folder)
            donor(archive, [request()])
            result, discover, fetch, search, _, _ = await self.collect(archive, [request()])
            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["source_reuse"]["reused"], 1)
            discover.assert_not_awaited(); fetch.assert_not_awaited(); search.assert_not_awaited()

    async def test_changed_definition_or_unit_cannot_reuse(self):
        for changed in ({**request(), "unit": "%"}, {**request(), "definition": "其它统计范围"}):
            with self.subTest(changed=changed), TemporaryDirectory() as folder:
                archive = Path(folder)
                donor(archive, [request()])
                result, _, fetch, _, _, _ = await self.collect(archive, [changed])
                self.assertEqual(result["source_reuse"]["reused"], 0)
                self.assertGreater(fetch.await_count, 0)

    async def test_different_month_or_later_information_cutoff_not_imported(self):
        with TemporaryDirectory() as folder:
            archive = Path(folder)
            donor(archive, [request()], cutoff="2026-10-10")
            result, _, fetch, _, _, _ = await self.collect(archive, [request()])
            self.assertEqual(result["source_reuse"]["reused"], 0)
            self.assertEqual(fetch.await_count, 1)
        with TemporaryDirectory() as folder:
            archive = Path(folder)
            donor(archive, [request()])
            result, _, fetch, _, _, _ = await self.collect(archive, [request()], month="2026-10")
            self.assertEqual(result["source_reuse"]["reused"], 0)
            self.assertGreater(fetch.await_count, 0)

    async def test_new_release_calendar_requires_refresh_instead_of_freezing_success(self):
        req = {**request(), "release_lag_days": 20}
        with TemporaryDirectory() as folder:
            archive = Path(folder)
            donor(archive, [req], pages=[body(month=8)])
            result, _, fetch, _, _, _ = await self.collect(archive, [req], cutoff="2026-10-25")
            self.assertEqual(result["source_reuse"]["reused"], 0)
            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["observations"][0]["period"], "2026-09")
            self.assertEqual(fetch.await_count, 1)

    async def test_bad_receipt_or_false_success_label_cannot_skip_collection(self):
        with TemporaryDirectory() as folder:
            archive = Path(folder)
            previous = donor(archive, [request()])
            path = next((previous / "working/macro-sources/pages").glob("*.json"))
            page = json.loads(path.read_text(encoding="utf-8")); page["text"] = "corrupted source"
            source._save(path, page)
            result, _, fetch, _, _, _ = await self.collect(archive, [request()])
            self.assertEqual(result["source_reuse"]["reused"], 0)
            self.assertEqual(fetch.await_count, 1)
            self.assertTrue(result["source_reuse"]["rejected"])

    async def test_partial_cancelled_batch_is_replayed_without_complete_package(self):
        with TemporaryDirectory() as folder:
            archive = Path(folder)
            donor(archive, [request()], package=False)
            result, discover, fetch, _, _, _ = await self.collect(archive, [request()])
            self.assertEqual(result["source_reuse"]["reused"], 1)
            discover.assert_not_awaited(); fetch.assert_not_awaited()

    async def test_empty_initial_seed_cannot_hide_successful_cancelled_batch(self):
        with TemporaryDirectory() as folder:
            archive=Path(folder)
            run=donor(archive,[request()],package=False)
            source._save(run/'working/macro-sources/reuse-seed.json',{
                'report_month':'2026-09','cutoff_date':'2026-10-04','evidence_observations':[]})
            result,discover,fetch,_,_,_=await self.collect(archive,[request()])
            self.assertEqual(result['source_reuse']['reused'],1)
            discover.assert_not_awaited();fetch.assert_not_awaited()

    async def test_formal_run_cannot_inherit_draft_success_with_insufficient_history(self):
        req = {**request(), "release_lag_days": 20}
        with TemporaryDirectory() as folder:
            archive = Path(folder)
            donor(archive, [req], pages=[body(month=8)])
            result, _, fetch, _, _, _ = await self.collect(archive, [req], draft=False, fetch=AsyncMock(return_value=body(month=8)))
            self.assertEqual(result["source_reuse"]["reused"], 0)
            self.assertEqual(result["request_status"][req["id"]]["status"], "insufficient_history")
            self.assertGreater(fetch.await_count, 0)

    async def test_query_change_and_package_upgrade_replay_evidence_not_task_acceptance(self):
        with TemporaryDirectory() as folder:
            archive = Path(folder)
            donor(archive, [request()])
            result, _, fetch, _, _, current = await self.collect(archive, [{**request(), "query": "new search wording"}])
            self.assertEqual(result["source_reuse"]["reused"], 1)
            fetch.assert_not_awaited()
            self.assertEqual(json.loads((current / "run-state.json").read_text(encoding="utf-8"))["status"], "running")

    async def test_newest_verified_project_selected_without_mixing_snapshots(self):
        with TemporaryDirectory() as folder:
            archive = Path(folder)
            donor(archive, [request()], pages=[body(value=48.0)])
            donor(archive, [request()], pages=[body(value=50.0)], name="macro-20261004-200000-00000002")
            result, _, fetch, _, _, _ = await self.collect(archive, [request()])
            self.assertEqual({item["value"] for item in result["observations"]}, {50.0})
            self.assertEqual(result["source_reuse"]["origins"][0]["origin_run_id"], "macro-20261004-200000-00000002")
            fetch.assert_not_awaited()

    async def test_customs_selected_vintage_still_checked_before_skipping(self):
        req = {**request(), "chart_id": "s19-shape13"}
        fresh = body(suffix="new-bulletin", value=50.0)
        directory = {"by_request": {req["id"]: {"items": [{"url": fresh["url"]}],
            "source_restrictions": {"exclusive_reviewed_discovery": True, "allowed_source_urls": [fresh["url"]]}}}}
        with TemporaryDirectory() as folder:
            archive = Path(folder)
            donor(archive, [req])
            result, discover, fetch, _, _, _ = await self.collect(archive, [req], directory=directory, fetch=AsyncMock(return_value=fresh))
            self.assertEqual(discover.await_count, 1)
            self.assertEqual(result["source_reuse"]["reused"], 0)
            self.assertEqual({item["value"] for item in result["observations"]}, {50.0})
            self.assertEqual(fetch.await_count, 1)

    async def test_copied_evidence_survives_original_project_removal(self):
        with TemporaryDirectory() as folder:
            archive = Path(folder)
            previous = donor(archive, [request()])
            first, _, _, _, _, _ = await self.collect(archive, [request()])
            previous.rename(archive / "retired-project-outside-discovery")
            second, _, fetch, _, _, _ = await self.collect(archive, [request()])
            self.assertEqual(second["source_reuse"]["reused"], 1)
            self.assertEqual(first["observations"], second["observations"])
            fetch.assert_not_awaited()

    async def test_customs_directory_failure_cannot_reuse_old_selected_vintage(self):
        req = {**request(), "chart_id": "s19-shape13"}
        with TemporaryDirectory() as folder:
            archive = Path(folder)
            donor(archive, [req])
            result, _, fetch, search, _, _ = await self.collect(archive, [req], directory={"by_request": {}})
            self.assertEqual(result["source_reuse"]["reused"], 0)
            self.assertEqual(result["coverage"]["verified"], 0)
            fetch.assert_not_awaited(); search.assert_not_awaited()

    async def test_malformed_old_snapshot_does_not_abort_new_task(self):
        with TemporaryDirectory() as folder:
            archive = Path(folder)
            previous = donor(archive, [request()])
            source._save(previous / "working/data-package.json", ["bad schema"])
            result, _, fetch, _, _, _ = await self.collect(archive, [request()])
            self.assertEqual(result["source_reuse"]["reused"], 0)
            self.assertEqual(result["status"], "ready")
            self.assertEqual(fetch.await_count, 1)


if __name__ == "__main__":
    unittest.main()
