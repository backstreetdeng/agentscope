import hashlib, json, time, unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from utils.weekly_report_research import EvidenceStore, research_stop_reason

class ResearchBudgetTests(unittest.TestCase):
    def store(self, count=0, stagnant=0, submissions=0, section='policy'):
        return SimpleNamespace(spec={'id':section},submission={'items':[{}]*count},stagnant_submissions=stagnant,submission_count=submissions,last_accepted_at=None)

    def test_zero_results_stop_after_repeated_rejection(self):
        self.assertTrue(research_stop_reason(self.store(stagnant=2,submissions=2),20))

    def test_new_source_work_has_time_to_proceed(self):
        self.assertEqual(research_stop_reason(self.store(),20),'')

    def test_elapsed_budget_stops_even_without_submission(self):
        self.assertTrue(research_stop_reason(self.store(),180))

    def test_one_good_result_does_not_wait_for_ten(self):
        store=self.store(count=1);store.last_accepted_at=time.monotonic()-46
        self.assertTrue(research_stop_reason(store,50))

    def test_joint_two_results_do_not_count_as_sufficient(self):
        self.assertEqual(research_stop_reason(self.store(count=2,section='joint'),20),'')

    def test_joint_three_results_end_research_but_not_validation(self):
        self.assertTrue(research_stop_reason(self.store(count=3,section='joint'),20))

    def test_source_with_matching_fingerprint_is_not_fetched_again(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);working=root/'working';working.mkdir()
            url='https://example.com/news';sid='src-'+hashlib.sha256(url.encode()).hexdigest()[:24]
            path=working/'source-text'/(sid+'.txt');path.parent.mkdir();path.write_text('已保存原文',encoding='utf-8')
            record=dict(id=sid,url=url,title='原文',fetched=True,text='已保存原文',text_path=path.relative_to(root).as_posix(),text_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            (working/'sources.json').write_text(json.dumps({sid:record}),encoding='utf-8')
            ctx=SimpleNamespace(root=root,working_dir=working,checkpoint=lambda *args:None)
            store=EvidenceStore(ctx,{'id':'policy'},{},lambda:None)
            with patch('utils.weekly_report_research.public_url'),patch('utils.weekly_report_research.fetch_url_text') as fetch:
                self.assertEqual(store.fetch(url)['text'],'已保存原文');fetch.assert_not_called()

if __name__=='__main__':unittest.main()
