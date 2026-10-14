import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from pptx import Presentation
from tests.test_macro_historical import engine, history
from utils.macro_report_delivery import verified_retained_state, verified_retained_artifact, macro_evidence_fingerprint
import hashlib
from utils.macro_report_jobs import MacroReportJobManager

class RetainedTest(unittest.TestCase):
    def test_explicit_confirmation_and_caption_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'working').mkdir();(root/'inputs').mkdir()
            package={'delivery_mode':'historical_retained','report_month':'2026-08','cutoff_date':'2026-09-30','observations':[],'evidence_observations':[]}
            (root/'working/data-package.json').write_text(json.dumps(package))
            (root/'inputs/request.json').write_text('{}')
            with self.assertRaises(ValueError):engine.build('2026-08',package,root/'out.pptx',root/'ledger.json',root)
            (root/'inputs/request.json').write_text(json.dumps({'history_retention_confirmed':True}))
            actual={'request_id':'s13-shape17::当月同比','period':'2026-08-31','value':5.2,'unit':'%','provenance':'official_actual'}
            with patch.object(engine,'replay_sources',return_value=[actual]):
                engine.build('2026-08',package,root/'out.pptx',root/'ledger.json',root)
                self.assertTrue(engine.validate(root/'out.pptx',root/'ledger.json')['passed'])
                ledger=json.loads((root/'ledger.json').read_text(encoding='utf-8'))
                self.assertFalse(ledger['formal_delivery_allowed'])
                a=ledger['retention_annotations'][0];deck=Presentation(root/'out.pptx')
                engine._shape(deck.slides[a['slide']-1],a['annotation_shape_id']).text=''
                deck.save(root/'out.pptx')
                ledger['pptx_sha256']=engine.digest(root/'out.pptx')
                (root/'ledger.json').write_text(json.dumps(ledger),encoding='utf-8')
                result=engine.validate(root/'out.pptx',root/'ledger.json')
                self.assertTrue(any(i['code']=='retention_caption_missing' for i in result['issues']))

    def test_no_gate_shortcut(self):
        self.assertFalse(verified_retained_state({'delivery_mode':'historical_retained','history_retention_confirmed':True},'macro-20261013-200000-1234abcd'))
        with tempfile.TemporaryDirectory() as tmp:
            jobs=MacroReportJobManager(Path(tmp),lambda *args:{})
            with self.assertRaises(ValueError):jobs.start({'report_month':'2026-08','mode':'historical_update','delivery_mode':'historical_retained'})

    def test_month_only_default_and_partial_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs=MacroReportJobManager(Path(tmp),lambda *args:{})
            with patch.object(jobs,'_spawn'):
                created=jobs.start({'report_month':'2026-08','question':'生成8月月报'})
                self.assertEqual(created['payload']['mode'],'historical_update')
                self.assertEqual(created['payload']['delivery_mode'],'historical_retained')
                jobs.update(created['run_id'],'partial_completed','缺项保留模板',100,status='partial_completed')
                resumed=jobs.resume(created['run_id'])
                self.assertEqual(resumed['run_id'],created['run_id'])
                self.assertTrue(resumed['payload']['resume_missing_pages'])
                self.assertEqual(resumed['status'],'queued')

    def test_download_binds_artifact_ledger_and_original_receipts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run_id='macro-20261013-200000-1234abcd'
            (root/'out.pptx').write_bytes(b'unit-test-artifact')
            digest=hashlib.sha256((root/'out.pptx').read_bytes()).hexdigest()
            ledger={'pptx_sha256':digest,'delivery_mode':'historical_retained','formal_delivery_allowed':False,'retained_content_complete':True}
            (root/'ledger.json').write_text(json.dumps(ledger),encoding='utf-8')
            (root/'receipt.json').write_text('original-page')
            state={'run_id':run_id,'delivery_mode':'historical_retained','history_retention_confirmed':True,
                'status':'retained_ready','formal_delivery_allowed':False,'retained_delivery_allowed':True,'business_status':'retained_passed',
                'validation':{'status':'passed'},'retained_validation':{'status':'passed','artifact_sha256':digest},
                'artifact_validations':[{'validator':g,'passed':True,'path':'out.pptx','detail':{'artifact_sha256':digest}} for g in ['macro_retained_business','pptx_structure','powerpoint_render','macro_layout']],
                'retained_delivery':{'artifact_path':'out.pptx','artifact_sha256':digest,'ledger_path':'ledger.json',
                    'ledger_sha256':macro_evidence_fingerprint(root/'ledger.json',root),'evidence_sha256':{'receipt.json':macro_evidence_fingerprint(root/'receipt.json',root)},'url':f'/api/macro-report/retained/{run_id}'}}
            self.assertTrue(verified_retained_artifact(state,root,run_id)['success'])
            (root/'receipt.json').write_text('changed-page')
            with self.assertRaises(ValueError):verified_retained_artifact(state,root,run_id)
            state['artifact_validations'].pop()
            self.assertFalse(verified_retained_state(state,run_id))
