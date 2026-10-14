"""Run the real research boundary on archived facts without changing the report."""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
from agentscope.message import UserMsg
from agents.market_strategy_agent import build_monthly_narrative_agent
from integrations.market_mcp_plugins import load_market_mcp_plugins
from tools.custom_tools import build_business_toolkit
from utils.config import load_json_config
from utils.monthly_report_narrative import _extract_json, _structured_retry_config
from utils.monthly_research_dag import ResearchDAG, validate_research_ledger


async def main():
    load_dotenv(ROOT / '.env', override=True)
    config = load_json_config()
    config['active_provider'] = 'minimax'
    bundle = await load_market_mcp_plugins(config, agent_key='market_strategy',
                                         selected_plugin_ids=['policy', 'rights', 'new-car', 'reputation'])
    print('plugins_ready', bundle.as_dict()['ready'], flush=True)
    run = 'month-20261013-014046-cd5ae8ff'
    rows = []
    for p in (ROOT / 'outputs/monthly-report-data' / run).glob('facts-B*.json'):
        rows.extend(json.loads(p.read_text(encoding='utf-8')))

    async def planner(prompt):
        agent = build_monthly_narrative_agent(_structured_retry_config(config), allow_tools=False)
        reply = await agent.reply(UserMsg(name='月报研究DAG验收', content=prompt))
        return _extract_json(reply.get_text_content())

    output = sys.argv[1] if len(sys.argv) > 1 else '.work/monthly-research-dag-validation'
    path = ROOT / output / 'research-dag.json'
    if '--continue' in sys.argv and path.is_file():
        state = json.loads(path.read_text(encoding='utf-8'))
        state.update(status='running', wave=0)
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    dag = ResearchDAG(path=path,
                      run_id='research-validation-20261013', month='2026-09', pages=rows,
                      tools=[*bundle.tools, *build_business_toolkit()], planner=planner,
                      progress=lambda message, _: print(message, flush=True), max_nodes=28, max_waves=6)
    result = await dag.run()
    errors = validate_research_ledger(dag.path)
    if errors:
        raise RuntimeError('Independent research acceptance failed: ' + '; '.join(errors))
    (dag.path.parent / 'acceptance.json').write_text(json.dumps({
        'status': 'passed', 'run_id': dag.run_id, 'report_month': dag.month,
        'checks': ['acyclic_dependencies', 'terminal_nodes', 'receipt_hashes',
                   'verbatim_quotes', 'source_ids', 'dates', 'entities', 'web_originals'],
        'research': result['research'], 'evidence_count': len(result['evidence'])
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    (dag.path.parent / 'research-evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'research': result['research'], 'evidence': len(result['evidence']),
                      'gaps': result['evidence_gaps']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
