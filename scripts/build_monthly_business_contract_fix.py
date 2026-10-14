"""Private revalidation, not a fresh web/background/model run."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from copy import deepcopy
import json
import hashlib
from zipfile import ZipFile
from utils.monthly_report_narrative import (NARRATIVE_RULE_VERSION, BATCHES,
    _page_payload, load_page_card_map, _normalize_batch,
    _validate_batch_facts, validate_narrative_package, apply_narratives_to_ppt)

ASSETS=ROOT/'skills/market-analysis-skill/passenger-car-monthly-report/assets'
HERE=ROOT/'outputs/monthly-report-data/business-contract-review-20261008'
PACKAGE=ROOT/'outputs/monthly-report-data/data-source-package-20261008-081855.json'
OLD=ROOT/'outputs/monthly-report-data/horizontal-review-20261008/narrative_evidence.json'
BASE=ASSETS/'乘用车月报PPT兼容模板.pptx'
OUTPUT=ROOT/'outputs/ppt/2026年8月中国乘用车市场月度分析报告_业务口径与库存版式修正版_20261009.pptx'

def main():
    data=json.loads(PACKAGE.read_text(encoding='utf-8'))
    old=json.loads(OLD.read_text(encoding='utf-8'))
    narrative=deepcopy(old)
    narrative['run_id']=HERE.name
    cards={c['code']:c for c in data['cards']}
    mapping=ASSETS/'乘用车月报-数据源映射指标.xlsx'
    examples_path=ASSETS/'expert-headline-examples.json'
    packets=[p for pages in BATCHES for p in _page_payload(pages,load_page_card_map(mapping),cards,
                                                       json.loads(examples_path.read_text(encoding='utf-8'))['pages'],data['report_month'])]
    inventory=next(p for p in packets if p['slide']==5)
    draft=_normalize_batch({'slides':[deepcopy(inventory['fact_grounded_draft'])],'evidence':[]},
                           'B1',(5,),data['report_month'])['slides'][0]
    draft['generation_method']='fact_grounded_title_only'
    narrative['slides']=[draft if s['slide']==5 else s for s in narrative['slides']]
    for batch in BATCHES:
        _validate_batch_facts({'slides':[s for s in narrative['slides'] if s['slide'] in batch]},
                              [p for p in packets if p['slide'] in batch])
    # Assign the private upgraded version only after actual local revalidation;
    # preserve the old artifact and formal web task/checkpoints unchanged.
    narrative['narrative_rule_version']=NARRATIVE_RULE_VERSION
    narrative['private_review']={'source':str(OLD),'new_web_job':False,
                                 'reason':'annual structural reference and title-only inventory correction'}
    validate_narrative_package(narrative,data,run_id=HERE.name,mapping_path=mapping,examples_path=examples_path)
    HERE.mkdir(parents=True,exist_ok=True)
    (HERE/'narrative_evidence.json').write_text(json.dumps(narrative,ensure_ascii=False,indent=2),encoding='utf-8')
    receipt=apply_narratives_to_ppt(BASE,OUTPUT,narrative)
    with ZipFile(BASE) as original,ZipFile(OUTPUT) as final:
        assert final.testzip() is None
        changed=[p for p in original.namelist() if original.read(p)!=final.read(p)]
        assert all(p.startswith('ppt/slides/slide') and p.endswith('.xml') for p in changed),changed
        assert all(original.read(p)==final.read(p) for p in original.namelist()
                   if p.startswith(('ppt/charts/','ppt/embeddings/')))
    receipt.update(output=str(OUTPUT),source=str(BASE),changed_parts=changed,
                   output_sha256=hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
                   data_sha256=hashlib.sha256(PACKAGE.read_bytes()).hexdigest(),
                   narrative_rule_version=NARRATIVE_RULE_VERSION,new_web_job=False)
    (HERE/'corrected-acceptance.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(receipt,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
