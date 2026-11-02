"""S3 单测：benchmark_research_dag 适配清单硬门槛 + 机制链路。"""
import json
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from utils.benchmark_research_dag import (
    BenchmarkResearchDAG, benchmark_questions, domain, eligible,
    public_args, validate_research_ledger, RECEIPT_DIR, VERSION,
)


def _tool(name, text='{"items": []}', fail=False):
    async def call(**args):
        if fail:
            raise ConnectionError('temporary')
        return text
    return SimpleNamespace(name=name, description='read', input_schema={
        'type': 'object', 'properties': {'query': {'type': 'string'}, 'url': {'type': 'string'},
                                          'model': {'type': 'string'}, 'keyword': {'type': 'string'},
                                          'limit': {'type': 'integer'}},
        'additionalProperties': False}, call=call)


class DomainTests(unittest.TestCase):
    def test_domain_mapping_and_whitelist(self):
        # 内部结构化域：miit_* / reputation_*；web_* 落入 internet
        self.assertEqual(domain('miit_search_models'), 'miit')
        self.assertEqual(domain('miit_get_model_detail'), 'miit')
        self.assertEqual(domain('reputation_search_source_reviews'), 'reputation')
        self.assertEqual(domain('web_search_local'), 'internet')
        self.assertEqual(domain('web_reader_firecrawl'), 'internet')
        # 白名单
        for n in ('miit_search_models', 'miit_get_model_detail', 'reputation_search_source_reviews',
                  'web_search_local', 'web_reader_local'):
            self.assertTrue(eligible(_tool(n)), n)
        # 排除写操作类
        self.assertFalse(eligible(_tool('miit_export_xls')))
        self.assertFalse(eligible(_tool('miit_get_status')))

    def test_no_monthly_module_import(self):
        src = Path(__file__).resolve().parents[1] / 'utils' / 'benchmark_research_dag.py'
        text = src.read_text(encoding='utf-8')
        self.assertNotRegex(text, r'^\s*(from\s+utils\.monthly_research_dag|import\s+monthly_research_dag)',
                            'benchmark 引擎不得 import 月报模块')
        self.assertEqual(VERSION, 'benchmark-research-dag-v1')

    def test_questions_have_no_month_semantics(self):
        qs = benchmark_questions('比亚迪宋PLUS EV')
        self.assertTrue(qs)
        self.assertIn('entities', qs[0])
        self.assertNotIn('month', json.dumps(qs))


class DAGTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'benchmark-dag.json'

    def dag(self, tools, planner, **kwargs):
        return BenchmarkResearchDAG(path=self.path, run_id='test', target='比亚迪宋PLUS EV',
                                    questions=benchmark_questions('比亚迪宋PLUS EV'),
                                    tools=tools, planner=planner, **kwargs)

    async def test_receipt_dir_isolated_from_monthly(self):
        t = _tool('miit_search_models', json.dumps({'items': [
            {'car_id': 'C1', 'create_time': '2026-09-01', 'pz_name': '纯电续航', 'pz_value': '605km 官方数据',
             'model': '比亚迪宋PLUS EV'}]}, ensure_ascii=False))
        async def planner(p):
            return {'actions': [{'tool': t.name, 'args': {'query': 'x'}}]}
        await self.dag([t], planner).run()
        node = json.loads(self.path.read_text(encoding='utf-8'))['nodes'][0]
        self.assertEqual(node['status'], 'completed')
        self.assertIn(RECEIPT_DIR, node['receipt'])
        self.assertNotIn('research-receipts', node['receipt'])
        self.assertEqual(RECEIPT_DIR, 'benchmark-receipts')

    async def test_failure_pattern_not_recorded_as_completed(self):
        t = _tool('web_search_local', 'web_search_local 未找到结果')
        async def planner(p):
            return {'actions': [{'tool': t.name, 'args': {'query': 'x'}}]}
        r = await self.dag([t], planner, max_waves=2).run()
        nodes = json.loads(self.path.read_text(encoding='utf-8'))['nodes']
        self.assertEqual(nodes[0]['status'], 'failed')
        self.assertEqual(r['research']['domains']['internet']['succeeded'], 0)

    async def test_full_run_accepts_miit_p0_and_passes_ledger(self):
        t = _tool('miit_search_models', json.dumps({'items': [
            {'car_id': 'C1', 'create_time': '2026-09-01', 'pz_name': '纯电续航',
             'pz_value': '605km 官方数据', 'model': '比亚迪宋PLUS EV'}]}, ensure_ascii=False))
        stage = 0
        async def planner(p):
            nonlocal stage
            stage += 1
            if stage == 1:
                return {'actions': [{'tool': t.name, 'args': {'query': 'x'}}]}
            return {'evidence': [{'receipt_ids': ['R001'], 'quote': '605km 官方数据',
                'url_or_record_id': 'C1', 'published_at': '2026-09-01',
                'entities': ['比亚迪宋PLUS EV'], 'summary': 'P0 续航锚定', 'verdict': 'supported'}]}
        r = await self.dag([t], planner).run()
        self.assertEqual(len(r['evidence']), 1)
        self.assertEqual(r['evidence'][0]['source_name'], 'miit_search_models')
        self.assertEqual(validate_research_ledger(self.path), [])

    async def test_recovery_reruns_damaged_receipt(self):
        t = _tool('miit_search_models', '{"items": []}')
        async def planner(p):
            return {}
        d = self.dag([t], planner)
        d.add({'tool': t.name, 'args': {}})
        await d.execute(d.state['nodes'][0])
        self.assertEqual(validate_research_ledger(self.path), [])
        Path(d.state['nodes'][0]['receipt']).write_text('tampered', encoding='utf-8')
        self.assertTrue(validate_research_ledger(self.path))
        d.state['status'] = 'completed'
        d.persist()
        recovered = self.dag([t], planner)
        self.assertEqual(recovered.state['nodes'][0]['status'], 'pending')
        self.assertEqual(recovered.state['status'], 'running')

    def test_public_args_blocks_internal_metrics(self):
        with self.assertRaises(Exception):
            public_args({'query': '比亚迪宋PLUS EV 成交价 12万'}, {'type': 'object', 'properties': {'query': {'type': 'string'}}})


if __name__ == '__main__':
    unittest.main()