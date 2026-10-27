"""Read the business dictionary only; never edit the source workbook."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
from openpyxl import load_workbook

parser=argparse.ArgumentParser()
parser.add_argument('--output',required=True,type=Path)
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
path=Path(r'E:/AI/migration-backup/5.4 晓亚\乘用车-新车明细板块-0927\汽车口碑标签字典_V1.0.xlsx')
wb=load_workbook(path,read_only=True,data_only=True)
taxonomy={}
rows=iter(wb['三级标签字典'].values)
for row in rows:
    if row and row[0]=='三级编码':break
for row in rows:
    if not row or not row[0]:continue
    name=str(row[3]).strip()
    if name in taxonomy:raise ValueError('Duplicate tertiary label')
    taxonomy[name]={'code':str(row[0]),'l1':str(row[1]),'l2':str(row[2])}
wb.close()
tree=ast.parse((root/'tools/new_car_detail_sync.py').read_text(encoding='utf-8-sig'))
patterns={}
for node in tree.body:
    if isinstance(node,ast.AnnAssign) and isinstance(node.target,ast.Name) and node.target.id=='TAG_PATTERNS':
        patterns=ast.literal_eval(node.value)
if not taxonomy or not patterns:raise ValueError('Missing dictionary/patterns')
payload={'taxonomy':taxonomy,'patterns':{k:v for k,v in patterns.items() if k in taxonomy},
         'dictionary_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'dictionary_path':str(path)}
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'labels':len(taxonomy),'patterned_labels':len(payload['patterns'])}))
