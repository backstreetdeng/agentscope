"""S6 适配清单 #11：双引擎同进程共存冒烟测试。

验证 benchmark_research_dag 与 monthly_research_dag 在同一进程可同时实例化：
- 回执目录隔离（benchmark-receipts/ vs research-receipts/），互不覆盖；
- 各自 VERSION、domain 白名单、eligible 过滤互不干扰；
- 共享域 reputation 在两个引擎均正确归类。
"""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from utils.benchmark_research_dag import (
    BenchmarkResearchDAG, benchmark_questions, RECEIPT_DIR, VERSION as BENCH_VERSION,
)
from utils.monthly_research_dag import (
    ResearchDAG, public_questions, VERSION as MONTHLY_VERSION,
)


def _tool(name, text='{"items": []}'):
    async def call(**args):
        return text
    return SimpleNamespace(name=name, description='read', input_schema={
        'type': 'object', 'properties': {'query': {'type': 'string'}, 'model': {'type': 'string'}},
        'additionalProperties': False}, call=call)


class DualEngineCoexistenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    async def test_both_engines_import_and_run_side_by_side(self):
        self.assertNotEqual(MONTHLY_VERSION, BENCH_VERSION)

        monthly_path = Path(self.tmp.name) / 'monthly' / 'research-dag.json'
        benchmark_path = Path(self.tmp.name) / 'benchmark' / 'benchmark-dag.json'
        pages = [{'slide': 17, 'required_prefix': '新能源', 'business_facts': [
            {'entity': '比亚迪汽车', 'period': '2026-09', 'scope': 'single_month',
             'metric': 'yoy_pct', 'value': -17.777}]}]

        monthly_tool = _tool('mcp__policy_search_policies', json.dumps({'items': [
            {'id': 'P1', '政策名称': '新能源汽车下乡补贴活动', 'published_at': '2026-09-01'}]}, ensure_ascii=False))
        benchmark_tool = _tool('miit_search_models', json.dumps({'items': [
            {'car_id': 'C1', 'model_name': '宋PLUS EV', 'create_time': '2026-09-01'}]}, ensure_ascii=False))

        async def planner(prompt):
            return {}

        monthly = ResearchDAG(path=monthly_path, run_id='m1', month='2026-09', pages=pages,
                              tools=[monthly_tool], planner=planner)
        benchmark = BenchmarkResearchDAG(path=benchmark_path, run_id='b1', target='宋PLUS EV',
                                         questions=benchmark_questions('宋PLUS EV'),
                                         tools=[benchmark_tool], planner=planner)

        monthly.add({'tool': monthly_tool.name, 'args': {'query': 'x'}})
        benchmark.add({'tool': benchmark_tool.name, 'args': {'model': '宋PLUS'}})
        await monthly.execute_pending()
        await benchmark.execute_pending()

        # 回执目录隔离：monthly 写 research-receipts/，benchmark 写 benchmark-receipts/
        m_receipt = monthly.state['nodes'][0]['receipt']
        b_receipt = benchmark.state['nodes'][0]['receipt']
        self.assertIn('research-receipts', m_receipt)
        self.assertNotIn(RECEIPT_DIR, m_receipt)
        self.assertIn(RECEIPT_DIR, b_receipt)
        self.assertNotIn('research-receipts', b_receipt)
        self.assertEqual(RECEIPT_DIR, 'benchmark-receipts')
        # 两个账本文件互不覆盖
        self.assertTrue(Path(m_receipt).is_file())
        self.assertTrue(Path(b_receipt).is_file())

    def test_shared_reputation_domain_and_isolated_domains(self):
        from utils.monthly_research_dag import domain as monthly_domain, DOMAINS as monthly_domains
        from utils.benchmark_research_dag import domain as benchmark_domain, DOMAINS as benchmark_domains
        # 共享域 reputation 两引擎均正确归类
        self.assertEqual(monthly_domain('reputation_search_source_reviews'), 'reputation')
        self.assertEqual(benchmark_domain('reputation_search_source_reviews'), 'reputation')
        # 各自专属域互不串扰
        self.assertEqual(monthly_domain('mcp__policy_search_policies'), 'policy')
        self.assertEqual(benchmark_domain('miit_search_models'), 'miit')
        self.assertIn('policy', monthly_domains)
        self.assertNotIn('policy', benchmark_domains)
        self.assertIn('miit', benchmark_domains)
        self.assertNotIn('miit', monthly_domains)


if __name__ == '__main__':
    unittest.main()
