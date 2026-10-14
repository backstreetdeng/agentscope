"""Verify the isolated presentation against the deployed formal reputation MCP."""
import json
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import httpx

parser=argparse.ArgumentParser()
parser.add_argument('--base-url',default='http://127.0.0.1:7861')
base_url=parser.parse_args().base_url.rstrip('/')
paths=['/api/reputation/overview','/api/reputation/reviews?limit=20',
       '/api/new-car/reputation?model=理想i8','/api/new-car/reputation?model=星光730新能源',
       '/api/new-car/reputation?model=不存在的车型验收', '/api/new-car/reputation-tree?model=理想i8',
       '/api/new-car/reputation?model=尊界V800']
def get(path):
    response=httpx.get(base_url+path,timeout=100)
    response.raise_for_status()
    return path,response.json()
data=dict(ThreadPoolExecutor(max_workers=4).map(get,paths))
assert all(d['success'] and d['source']=='mcp' for d in data.values())
assert data[paths[0]]['status']['review_count']==data[paths[1]]['total_count']==25592
assert data[paths[2]]['raw_total']==48 and data[paths[2]]['analysis_available']
assert data[paths[0]]['status']['analysis_current']
assert data[paths[0]]['status']['analysis_processed_review_count']==25592
assert data[paths[0]]['status']['analysis_processed_model_count']==409
assert data[paths[3]]['raw_total']==49 and data[paths[3]]['analysis_available'] and data[paths[3]]['analysis_current']
assert not data[paths[4]]['available']
assert data[paths[6]]['raw_total']==4 and data[paths[6]]['analysis_processed'] and not data[paths[6]]['analysis_available']
assert all(len(data[paths[3]]['groups'][direction])<=5 for direction in ['positive','negative'])
result={'total':25592,'tools':data[paths[0]]['tool_count'],
        '理想i8':{'raw':48,'analyzed':data[paths[2]]['total_reviews']},
        '星光730新能源':{'raw':49,'analysis_available':True},
        'neutral_model_scanned_without_filler':True,'analysis_current':True,
        'tagged_models':data[paths[0]]['status']['analysis_model_count'],
        'source_models_scanned':data[paths[0]]['status']['analysis_processed_model_count'],
        'genuine_empty':True,'verified_base_url':base_url,'production_restart_by_agent':False}
out=Path(__file__).resolve().parents[1]/'outputs/reputation-full-analysis'
out.mkdir(parents=True,exist_ok=True)
(out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
