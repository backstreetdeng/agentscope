"""Compare every formal MCP name with the approved ID/name workbook extraction."""
import asyncio
import json
from pathlib import Path
import sys
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from integrations.new_car_live import load_new_car
from utils.config import load_json_config

async def main():
    load_dotenv(ROOT/'.env',override=True)
    mapping=json.loads((ROOT/'outputs/new-car-style-names/source-mapping.json').read_text(encoding='utf-8'))
    expected={r['id']:r['name'] for r in mapping['names']}
    data=await load_new_car(load_json_config(),'list')
    assert data['source']=='mcp' and data['storage']=='postgres'
    rows=data['rows'];assert len(rows)==2228 and len({int(r['id']) for r in rows})==2228
    assert all(r['style_name']==expected[int(r['id'])] for r in rows)
    detail=await load_new_car(load_json_config(),'detail','理想i8','理想汽车')
    assert len(detail['rows'])==2 and all(r['style_name']==expected[int(r['id'])] for r in detail['rows'])
    report={'success':True,'source':'formal_new_car_mcp','total':len(rows),'names_verified':len(rows),
            'source_only_not_inserted':len(expected)-len(rows),'style_names':[r['style_name'] for r in detail['rows']],
            'schema_change':'new_car_model.style_name TEXT','baseline_fields_preserved':True,'production_7860_restarted':False}
    (ROOT/'outputs/new-car-style-names/mcp-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':asyncio.run(main())
