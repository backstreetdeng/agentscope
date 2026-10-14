"""Execute Codex-authored research branches; no web-agent model writes this run."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
from integrations.market_mcp_plugins import load_market_mcp_plugins
from tools.custom_tools import build_business_toolkit
from utils.config import load_json_config
from utils.monthly_research_dag import ResearchDAG,validate_research_ledger

async def main():
    load_dotenv(ROOT/'.env',override=True)
    root=Path((ROOT/'.work/september-codex-run.txt').read_text(encoding='utf-8'))
    pages=json.loads((root/'facts.json').read_text(encoding='utf-8'))
    bundle=await load_market_mcp_plugins(load_json_config(),agent_key='market_strategy',selected_plugin_ids=['policy','rights','new-car','reputation'])
    async def no_model(prompt):
        raise RuntimeError('Codex run uses Codex-authored planning, not the web model')
    dag=ResearchDAG(path=root/'research-dag.json',run_id=root.name,month='2026-09',pages=pages,
        tools=[*bundle.tools,*build_business_toolkit()],planner=no_model,max_nodes=60,
        progress=lambda message,_:print(message,flush=True))
    if not dag.state['nodes']:
        prior=json.loads((ROOT/'.work/monthly-research-dag-release/research-dag.json').read_text(encoding='utf-8'))
        for old in prior['nodes']:
            node=deepcopy(old)
            if node.get('receipt'):
                target=root/'research-receipts'/f"{node['id']}.txt";target.parent.mkdir(exist_ok=True)
                shutil.copyfile(node['receipt'],target);node['receipt']=str(target)
            node['reused_from']='research-validation-20261013'
            dag.state['nodes'].append(node)
        dag.state['evidence']=deepcopy(prior['evidence'])
        dag.state['provenance_note']='Verified historical query receipts reused; new branches and narratives authored by Codex.'
    suffixes={t.name.split('__')[-1]:t.name for t in bundle.tools}
    actions=json.loads((root/'codex-research-actions.json').read_text(encoding='utf-8'))
    for action in actions:
        action['tool']=suffixes.get(action['tool'],action['tool'])
        dag.add(action)
    await dag.execute_pending()
    dag.structured_candidates()
    dag.state.update(status='completed',execution_origin='codex',planner='Codex',
                     gaps=[f"{n['id']}: {n.get('error','')}" for n in dag.state['nodes'] if n['status']=='failed'])
    dag.persist()
    result=dag.output()
    (root/'research-evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    errors=validate_research_ledger(dag.path)
    print(json.dumps({'research':result['research'],'materials':len(result['evidence']),'errors':errors},ensure_ascii=False),flush=True)
    if errors:raise ValueError('; '.join(errors))

if __name__=='__main__':asyncio.run(main())
