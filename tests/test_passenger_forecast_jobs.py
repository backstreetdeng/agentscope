"""Persistence and publication guards; domain and Office tests run separately."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from utils.passenger_forecast_jobs import PassengerForecastJobs


class ForecastJobsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.skill = self.root / 'skills/passenger-car-market-forecast'
        self.skill.mkdir(parents=True)
        (self.skill / 'SKILL.md').write_text('---\nname: passenger-car-market-forecast\ndescription: Test package\n---\nTest rules.', encoding='utf-8')
        for name in ('input-contract', 'monthly-input', 'annual-monthly', 'nev-penetration', 'output-formats'):
            target = self.skill / 'references' / (name + '.md')
            target.parent.mkdir(exist_ok=True)
            target.write_text('Test resource.', encoding='utf-8')
        for name in ('utils/passenger_forecast.py', 'utils/passenger_forecast_jobs.py', 'utils/passenger_forecast_exports.py', 'scripts/export_passenger_forecast.mjs'):
            target = self.root / name
            target.parent.mkdir(exist_ok=True)
            target.write_text('test source', encoding='utf-8')
        self.manager = PassengerForecastJobs(self.root, self.skill)
        self.raw = '年份,月份,乘用车总量,新能源销量\n2025,1,1000000,300000\n'.encode('utf-8')
        self.history = self.manager.upload('history.csv', self.raw, 'vehicle')

    def tearDown(self):
        self.tmp.cleanup()

    def payload(self):
        return dict(history_id=self.history['history_id'], target_year=2027, annual_targets={'2026':1960, '2027':2060}, as_of_date='2026-10-10', allow_draft=True, task='monthly')

    def test_upload_original_and_normalized_survive_new_manager(self):
        other = PassengerForecastJobs(self.root, self.skill)
        current = other.history(include_records=True)
        self.assertEqual(current['history_id'], self.history['history_id'])
        self.assertEqual(current['records'][0]['total'],100)
        original = self.root / 'data/passenger-forecast' / current['history_id'] / 'source.csv'
        self.assertEqual(original.read_bytes(), self.raw)
        with self.assertRaises(ValueError):
            other.history('../secrets')

    def test_invalid_upload_keeps_previous_input(self):
        for filename, content, unit in [('data.xlsx',b'invalid','vehicle'),('data.csv',self.raw,'unknown')]:
            with self.assertRaises(ValueError):
                self.manager.upload(filename,content,unit)
            self.assertEqual(self.manager.history()['history_id'],self.history['history_id'])

    def test_draft_and_annual_values_required(self):
        for change in ({'allow_draft':False},{'annual_targets':{}},{'target_year':True}):
            with self.assertRaises(ValueError):
                self.manager.start(dict(self.payload(),**change))

    def test_failure_cannot_publish_and_pinned_input_remains(self):
        with patch.object(self.manager,'_launch'):
            job = self.manager.start(self.payload())
        run_id=job['run_id']
        root=self.root/'runtime/passenger-forecast'/run_id
        self.assertTrue((root/'inputs/history.json').is_file())
        self.assertTrue((root/'working/skill-package/passenger-car-market-forecast/references/annual-monthly.md').is_file())
        self.manager._execute(run_id)
        job=self.manager.get(run_id)
        self.assertEqual(job['status'],'failed')
        self.assertEqual(job['artifacts'],[])
        self.assertNotIn('result',job)
        with self.assertRaises(ValueError):
            self.manager.download(run_id,'xlsx')
        (self.root/'utils/passenger_forecast.py').write_text('changed',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'版本'):
            self.manager.resume(run_id)

    def test_normalized_values_must_match_original(self):
        with patch.object(self.manager,'_launch'):
            job = self.manager.start(self.payload())
        normalized=self.root/'runtime/passenger-forecast'/job['run_id']/'inputs/history.json'
        history=json.loads(normalized.read_text(encoding='utf-8'))
        history['records'][0]['total']+=1
        normalized.write_text(json.dumps(history),encoding='utf-8')
        self.manager._execute(job['run_id'])
        failed=self.manager.get(job['run_id'])
        self.assertEqual(failed['status'],'failed')
        self.assertIn('原Excel/CSV不一致',failed['error'])


if __name__=='__main__':
    unittest.main()
