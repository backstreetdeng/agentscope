"""Read only A/U of the supplied workbook; retain exact ID/name evidence."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
from openpyxl import load_workbook

def normalize_id(value):
    if isinstance(value,bool) or value is None:return None
    text=str(value).strip()
    if text.endswith('.0'):text=text[:-2]
    return int(text) if text.isascii() and text.isdigit() and int(text)>0 else None

def extract(path):
    workbook=load_workbook(path,read_only=True,data_only=True)
    groups=defaultdict(list);invalid=[];blank=[];count=0
    try:
        sheet=workbook['数据表']
        header=next(sheet.iter_rows(max_row=1,max_col=21,values_only=True))
        if header[0]!='汽车之家款型ID' or header[20]!='汽车之家款型名称':raise ValueError('Unexpected A/U headers')
        for number,row in enumerate(sheet.iter_rows(min_row=2,max_col=21,values_only=True),2):
            if all(v is None for v in row):continue
            count+=1
            sid=normalize_id(row[0]);name=str(row[20] or '').strip()
            if sid is None:invalid.append(number);continue
            if not name or name in {'—','-','暂无','无','待补充'} or name.startswith('#'):blank.append({'id':sid,'row':number});continue
            groups[sid].append({'row':number,'name':name,'model':row[9],'brand':row[8]})
        conflicts={str(sid):values for sid,values in groups.items() if len({v['name'] for v in values})!=1}
        names=[{'id':sid,'name':values[0]['name'],'rows':[v['row'] for v in values],
                'source_models':sorted({str(v['model']) for v in values if v['model']})} for sid,values in sorted(groups.items()) if str(sid) not in conflicts]
        return {'source':str(path.resolve()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'sheet':'数据表',
                'id_column':'A','name_column':'U','source_records':count,'invalid_id_rows':invalid,
                'blank_name_rows':blank,'conflicts':conflicts,'same_name_duplicate_ids':sum(len(v)>1 for sid,v in groups.items() if str(sid) not in conflicts),
                'names':names}
    finally:workbook.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--workbook',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();data=extract(a.workbook);a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in data.items() if k not in {'names','conflicts','blank_name_rows'}}|{'unique_names':len(data['names']),'conflict_ids':len(data['conflicts']),'blank_names':len(data['blank_name_rows'])},ensure_ascii=False))
