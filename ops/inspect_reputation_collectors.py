"""Inspect collector connection configuration without exposing credentials."""
import ast
import re
from pathlib import Path
from urllib.parse import urlsplit
from dotenv import dotenv_values

for name in ['dongchedi_koubei','carhome_koubei']:
    root=Path('E:/AI/data/envs/car_agent_env/py/skills')/name
    tree=ast.parse((root/'web_monitor.py').read_text(encoding='utf-8-sig'))
    for path in root.glob('启动*口碑*.bat'):
        match=re.search(r'postgres(?:ql)?://[^\s"]+',path.read_text(encoding='utf-8-sig'))
        if match:
            u=urlsplit(match.group())
            print(name,'launcher',{'host':u.hostname,'port':u.port,'database':u.path,'user':u.username})
    constants={}
    for node in tree.body:
        if isinstance(node,ast.Assign):
            try:
                value=ast.literal_eval(node.value)
            except (ValueError,TypeError):
                continue
            for target in node.targets:
                if isinstance(target,ast.Name): constants[target.id]=value
    for key,value in constants.items():
        if isinstance(value,str) and value.startswith('postgresql'):
            u=urlsplit(value)
            print(name,key,{'host':u.hostname,'port':u.port,'database':u.path,'user':u.username})
    for path in [root/'.env',root.parent/'.env',root.parent.parent/'.env']:
        if path.is_file():
            for key,value in dotenv_values(path).items():
                if value and value.startswith('postgresql'):
                    u=urlsplit(value)
                    print(name,str(path),key,{'host':u.hostname,'port':u.port,'database':u.path,'user':u.username})
    for node in tree.body:
        if isinstance(node,ast.FunctionDef) and node.name=='get_db_url':
            for sub in ast.walk(node):
                if isinstance(sub,ast.Call) and isinstance(sub.func,ast.Attribute) and sub.func.attr=='getenv':
                    print(name,'env-key',ast.literal_eval(sub.args[0]))
                if isinstance(sub,ast.Constant) and isinstance(sub.value,str) and sub.value.startswith('postgresql'):
                    u=urlsplit(sub.value)
                    print(name,'fallback',{'host':u.hostname,'port':u.port,'database':u.path,'user':u.username})

import httpx
print('running dashboard database',httpx.get('http://127.0.0.1:8765/api/dashboard',timeout=10).json()['db']['label'])
