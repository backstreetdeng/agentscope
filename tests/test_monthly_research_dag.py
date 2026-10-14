import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from utils.monthly_research_dag import ResearchDAG, public_questions, public_args, validate_research_ledger


class DAGTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'research-dag.json'
        self.calls = []
        self.pages = [{'slide': 17, 'required_prefix': '新能源', 'business_facts': [
            {'entity': '比亚迪汽车', 'period': '2026-09', 'scope': 'single_month',
             'metric': 'yoy_pct', 'value': -17.777, 'fact_id': 'private-fact'}]}]

    def tool(self, name, text='{"items": []}', fail=False):
        async def call(**args):
            self.calls.append((name, args))
            if fail:
                raise ConnectionError('temporary')
            return text
        return SimpleNamespace(name=name, description='read', input_schema={
            'type': 'object', 'properties': {'query': {'type': 'string'}, 'url': {'type': 'string'}},
            'additionalProperties': False}, call=call)

    def dag(self, tools, planner, **kwargs):
        return ResearchDAG(path=self.path, run_id='test', month='2026-09', pages=self.pages,
                           tools=tools, planner=planner, **kwargs)

    async def test_empty_results_expand_to_web_and_resume_without_requery(self):
        tools = [self.tool('mcp__policy_search_policies'), self.tool('any_search'),
                 self.tool('web_fetch', '比亚迪汽车公告 2026-09-15 新车活动正式发布 https://official.example/a')]
        stage = 0
        async def planner(prompt):
            nonlocal stage
            stage += 1
            if stage == 1:
                return {'actions': [{'tool': tools[0].name, 'args': {'query': '2026-09 比亚迪汽车'}}], 'gaps': ['目录无命中']}
            if stage == 2:
                return {'actions': [{'tool': 'any_search', 'args': {'query': '2026-09 比亚迪汽车 公告'}, 'depends_on': ['R001']}]}
            if stage == 3:
                return {'actions': [{'tool': 'web_fetch', 'args': {'url': 'https://official.example/a'}, 'depends_on': ['R002']}]}
            return {'actions': [], 'evidence': [{'receipt_ids': ['R003'], 'quote': '新车活动正式发布',
                'url_or_record_id': 'https://official.example/a', 'published_at': '2026-09-15',
                'applicable_month': '2026-09', 'entities': ['比亚迪汽车'], 'summary': '当月公告活动', 'verdict': 'supported'}]}
        result = await self.dag(tools, planner).run()
        self.assertEqual(len(result['evidence']), 1)
        self.assertEqual(result['research']['nodes'], 3)
        self.assertEqual(result['evidence'][0]['grade'], 'C')
        await self.dag(tools, planner).run()
        self.assertEqual(len(self.calls), 3)
        nodes = json.loads(self.path.read_text(encoding='utf-8'))['nodes']
        self.assertEqual(nodes[2]['depends_on'], ['R002'])

    async def test_cannot_invent_receipt_quote_or_skip_web_original(self):
        t = self.tool('any_search', '2026-09-15 比亚迪汽车 新车活动正式发布 https://official.example/a')
        async def planner(p):
            return {}
        d = self.dag([t], planner)
        d.add({'tool': t.name, 'args': {'query': '比亚迪汽车'}})
        await d.execute(d.state['nodes'][0])
        e = {'receipt_ids': ['R001'], 'quote': '新车活动正式发布', 'url_or_record_id': 'https://official.example/a',
             'published_at': '2026-09-15', 'applicable_month': '2026-09', 'entities': ['比亚迪汽车'], 'verdict': 'supported'}
        with self.assertRaisesRegex(ValueError, '打开原文'):
            d.accept_evidence(e)
        e['receipt_ids'] = ['invented']
        with self.assertRaisesRegex(ValueError, '回执'):
            d.accept_evidence(e)

    async def test_failed_call_retries_and_remains_explicit_gap(self):
        t = self.tool('mcp__rights_search_offers', fail=True)
        async def planner(p):
            return {'actions': [{'tool': t.name, 'args': {'query': '比亚迪汽车'}}], 'gaps': ['权益仍不可核实']}
        r = await self.dag([t], planner, max_waves=4).run()
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(r['research']['domains']['rights']['succeeded'], 0)
        self.assertTrue(r['evidence_gaps'])

    async def test_invalid_schema_and_cycles_are_rejected(self):
        t = self.tool('mcp__new_car_search_models')
        async def planner(p):
            return {}
        d = self.dag([t], planner)
        with self.assertRaises(Exception):
            d.add({'tool': t.name, 'args': {'private': 'x'}})
        with self.assertRaisesRegex(ValueError, '依赖'):
            d.add({'tool': t.name, 'args': {}, 'depends_on': ['R001']})

    def test_public_direction_has_no_private_measurement(self):
        q = public_questions(self.pages, '2026-09')
        self.assertEqual(q[0]['signals'][0]['direction'], '下降')
        self.assertNotIn('17.777', json.dumps(q))
        self.assertNotIn('private-fact', json.dumps(q))
        with self.assertRaises(ValueError):
            public_args({'query': '比亚迪销量同比下降17.777%'}, {'type': 'object'})

    async def test_verified_receipt_survives_narrative_independently(self):
        t = self.tool('mcp__new_car_get_model_detail', '记录 NC123 比亚迪汽车 2026-09-15 新车活动正式发布')
        async def planner(p):
            return {}
        d = self.dag([t], planner)
        d.add({'tool': t.name, 'args': {}})
        await d.execute(d.state['nodes'][0])
        e = {'receipt_ids': ['R001'], 'quote': '新车活动正式发布', 'url_or_record_id': 'NC123',
             'published_at': '2026-09-15', 'applicable_month': '2026-09', 'entities': ['比亚迪汽车'], 'verdict': 'supported'}
        d.accept_evidence(e)
        self.assertEqual(len(d.output()['evidence']), 1)
        d.persist()
        self.assertEqual(validate_research_ledger(self.path), [])
        e['quote'] = '不存在的政策带动销量暴涨'
        with self.assertRaisesRegex(ValueError, '逐字匹配'):
            d.accept_evidence(e)
        e['quote'] = '新车活动正式发布'
        e['published_at'] = '2026-10-15'
        with self.assertRaises(ValueError):
            d.accept_evidence(e)

    async def test_dependency_order_and_corrupt_receipt_recovery(self):
        t = self.tool('mcp__policy_search_policies')
        async def planner(p):
            return {}
        d = self.dag([t], planner)
        d.add({'tool': t.name, 'args': {'query': 'first'}})
        d.add({'tool': t.name, 'args': {'query': 'second'}, 'depends_on': ['R001']})
        await d.execute_pending()
        self.assertEqual([args['query'] for _, args in self.calls], ['first', 'second'])
        self.assertEqual(validate_research_ledger(self.path), [])
        Path(d.state['nodes'][0]['receipt']).write_text('tampered', encoding='utf-8')
        self.assertTrue(validate_research_ledger(self.path))
        d.state['status'] = 'completed'
        d.persist()
        recovered = self.dag([t], planner)
        self.assertEqual(recovered.state['nodes'][0]['status'], 'pending')
        self.assertEqual(recovered.state['status'], 'running')

    async def test_publication_month_does_not_override_effective_month(self):
        text = json.dumps({'items': [{'id': 'OFF1', 'model': '比亚迪汽车', 'published_at': '2026-09-29',
             '活动开始日期': '2026-10-01', '活动结束日期': '2026-10-31', '内容': '限时置换补贴正式发布'}]}, ensure_ascii=False)
        t = self.tool('mcp__rights_get_offer_detail', text)
        async def planner(p):
            return {}
        d = self.dag([t], planner)
        d.add({'tool': t.name, 'args': {}})
        await d.execute_pending()
        with self.assertRaisesRegex(ValueError, '有效期'):
            d.accept_evidence({'receipt_ids': ['R001'], 'quote': '限时置换补贴正式发布',
                'url_or_record_id': 'OFF1', 'published_at': '2026-09-29', 'applicable_month': '2026-09',
                'entities': ['比亚迪汽车'], 'verdict': 'supported'})

    async def test_plugin_candidates_are_preserved_without_model_repeating_them(self):
        rows = [{'记录编号': 'OFF1', '车型': '比亚迪汽车', '监测日期/发布日期': '2026-09-01',
                 '活动开始日期': '2026-09-01', '活动结束日期': '2026-09-30', '活动内容': '当月有效置换购车补贴活动'},
                {'记录编号': 'OFF2', '车型': '比亚迪汽车', '监测日期/发布日期': '2026-09-29',
                 '活动开始日期': '2026-10-01', '活动结束日期': '2026-10-31', '活动内容': '下月有效置换购车补贴活动'}]
        t = self.tool('mcp__rights_search_offers', json.dumps({'items': rows}, ensure_ascii=False))
        async def planner(p):
            return {}
        d = self.dag([t], planner)
        d.add({'tool': t.name, 'args': {}})
        await d.execute_pending()
        d.structured_candidates()
        self.assertEqual([e['url_or_record_id'] for e in d.state['evidence']], ['OFF1'])
        self.assertEqual(validate_research_ledger(self.path), [])

