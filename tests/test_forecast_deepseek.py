"""Privacy boundary tests; all HTTP is intercepted and inputs are synthetic."""
import copy
import json
import unittest
from unittest.mock import patch

from integrations import forecast_deepseek as module

RUN = 'chronos-' + 'a' * 32
SENTINEL = 'HISTORY_PRIVATE_874923'


def fixture():
    data = {
        'province': '上海', 'energy': '纯电动', 'metric': '零售', 'unit': '辆',
        'data_cutoff': '2026-09', 'model': 'amazon/chronos-2',
        'scenario': '基准（未叠加事件系数）',
        'forecast': [{'month':'2026-10', 'p10':100, 'p50':120, 'p90':140},
                     {'month':'2026-11', 'p10':110, 'p50':130, 'p90':150}],
        'source': SENTINEL, 'source_sha256': SENTINEL,
        'history': [SENTINEL], 'backtest': {'actual': SENTINEL},
        'decision_meaning': SENTINEL,
    }
    return {'run_id':RUN, 'status':'completed', 'operation':'forecast', 'data':data}


class Response:
    status_code = 200
    def json(self):
        return {'choices':[{'message':{'content':'观察预测波动，结合区间谨慎安排资源。'}}]}


class PrivacyTests(unittest.TestCase):
    def setUp(self):
        self.job = fixture()
        self.payload = {'run_id':RUN, 'intent':'strategy', 'model':'flash'}

    def run_with_capture(self, job=None, payload=None):
        job = self.job if job is None else job
        captured = []
        class Client:
            def __init__(self, **kw): captured.append(('config',kw))
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def post(self, url, **kw):
                captured.append(('post',url,kw))
                return Response()
        with patch.object(module.CHRONOS_JOBS, 'get', return_value=job), \
             patch.object(module, 'load_result', return_value={'result':job['data']}), \
             patch.object(module.httpx, 'Client', Client), \
             patch.object(module, 'dotenv_values', return_value={'DASHSCOPE_API_KEY':'synthetic-test-key'}):
            result = module.answer(self.payload if payload is None else payload)
        return result, captured

    def test_final_wire_contains_only_forecast_and_fixed_messages(self):
        result, captured = self.run_with_capture()
        self.assertEqual(result['mode'], 'forecast_only_deepseek')
        config, post = captured
        self.assertFalse(config[1]['trust_env'])
        self.assertFalse(config[1]['follow_redirects'])
        self.assertEqual(post[1], 'https://api.deepseek.com/chat/completions')
        body = post[2]['json']
        wire = json.dumps(body, ensure_ascii=False)
        self.assertNotIn(SENTINEL, wire)
        self.assertNotIn('backtest', wire)
        self.assertNotIn('source_sha256', wire)
        self.assertNotIn('data_cutoff', wire)
        self.assertEqual(body['model'], 'deepseek-v4-flash')
        projection = json.loads(body['messages'][1]['content'].split('\n',1)[1])
        self.assertEqual(set(projection), {'region','energy','metric','unit','scenario','forecast'})
        self.assertTrue(all(set(row) == {'month','p10','p50','p90'} for row in projection['forecast']))

    def test_arbitrary_question_and_context_rejected_before_http(self):
        for key in ('question', 'prior_questions', 'history', 'extra'):
            request = dict(self.payload, **{key:SENTINEL})
            with self.subTest(key=key), patch.object(module.httpx,'Client') as client:
                with self.assertRaises(ValueError): module.answer(request)
                client.assert_not_called()

    def test_bad_jobs_and_rows_never_open_connection(self):
        cases = []
        for field, value in [('status','running'),('operation','backtest')]:
            job = fixture(); job[field] = value; cases.append(job)
        for field, value in [('month','2026-09'), ('p10',float('nan')), ('p50',False),
                             ('p90',99), ('secret',SENTINEL)]:
            job = fixture(); job['data']['forecast'][0][field] = value; cases.append(job)
        job = fixture(); job['data']['forecast'][1]['month'] = '2026-12'; cases.append(job)
        job = fixture(); job['data']['province'] = SENTINEL; cases.append(job)
        job = fixture(); job['data']['scenario'] = SENTINEL; cases.append(job)
        for job in cases:
            with self.subTest(job=job), patch.object(module.CHRONOS_JOBS,'get',return_value=job), \
                 patch.object(module,'load_result',return_value={'result':job['data']}), \
                 patch.object(module.httpx,'Client') as client:
                with self.assertRaises(ValueError): module.answer(self.payload)
                client.assert_not_called()

    def test_changed_receipt_refused_before_http(self):
        changed = copy.deepcopy(self.job['data'])
        changed['forecast'][0]['p50'] = 125
        with patch.object(module.CHRONOS_JOBS,'get',return_value=self.job), \
             patch.object(module,'load_result',return_value={'result':changed}), \
             patch.object(module.httpx,'Client') as client:
            with self.assertRaises(ValueError): module.answer(self.payload)
            client.assert_not_called()

    def test_unknown_model_or_intent_rejected(self):
        for field in ('model','intent'):
            with self.subTest(field=field), patch.object(module.httpx,'Client') as client:
                with self.assertRaises(ValueError): module.answer(dict(self.payload, **{field:SENTINEL}))
                client.assert_not_called()

    def test_redirect_is_failure_and_not_followed(self):
        class Redirect(Response):
            status_code = 307
        class Client:
            def __init__(self, **kw): self.options=kw
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def post(self, *args, **kwargs):
                self.assert_no_redirect()
                return Redirect()
            def assert_no_redirect(self): self_outer.assertFalse(self.options['follow_redirects'])
        self_outer = self
        with patch.object(module.CHRONOS_JOBS,'get',return_value=self.job), \
             patch.object(module,'load_result',return_value={'result':self.job['data']}), \
             patch.object(module.httpx,'Client',Client), \
             patch.object(module,'dotenv_values',return_value={'DASHSCOPE_API_KEY':'synthetic-test-key'}):
            with self.assertRaisesRegex(ValueError,'HTTP 307'): module.answer(self.payload)

    def test_unsupported_model_claims_rejected(self):
        for text in ('春节导致增长', '季节性规律明显', '销量增长20%', '2027年销量增长'):
            class UnsafeResponse(Response):
                def json(self):
                    return {'choices':[{'message':{'content':text}}]}
            class Client:
                def __init__(self, **kw): pass
                def __enter__(self): return self
                def __exit__(self, *args): return False
                def post(self, *args, **kw): return UnsafeResponse()
            with self.subTest(text=text), patch.object(module.CHRONOS_JOBS,'get',return_value=self.job), \
                 patch.object(module,'load_result',return_value={'result':self.job['data']}), \
                 patch.object(module.httpx,'Client',Client), \
                 patch.object(module,'dotenv_values',return_value={'DASHSCOPE_API_KEY':'synthetic-test-key'}):
                with self.assertRaisesRegex(ValueError, '质量门拦截'): module.answer(self.payload)


if __name__ == '__main__':
    unittest.main()
