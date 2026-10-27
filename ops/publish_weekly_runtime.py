import hashlib,json,shutil
from pathlib import Path
root=Path(__file__).resolve().parents[1];package=root/'skills/auto-weekly-report'
manifest_path=package/'package-manifest.json'
manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
manifest.update(version='1.1.0',execution_policy=dict(research_seconds_per_section=180,cached_source_repair_seconds=90,search_budget=6,max_iterations=8,stagnant_submissions=2))
manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for name in ['weekly_report_jobs.py','weekly_report_research.py']:
    shutil.copy2(root/'utils'/name,package/'scripts/web_runtime'/name)
integrity={p.relative_to(package).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in package.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='package-integrity.json' and p.suffix not in {'.pyc','.pyo'}}
(package/'package-integrity.json').write_text(json.dumps(integrity,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Published weekly runtime version 1.1.0; old run snapshots unchanged.')
