"""Run the first-stage Chronos-2 forecast independently of the web service.

Reads the approved workbook and local model only. Saves a new internal evidence
manifest under outputs/chronos-002; never changes source data or model weights.
"""
from __future__ import annotations
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from uuid import uuid4

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from integrations.chronos2_data import ALL_PROVINCES, FOUR_TYPES, read_workbook
from integrations.chronos2_forecast import OUTPUTS, calculate, model, validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--operation', choices=('forecast', 'backtest'), default='forecast')
    parser.add_argument('--province', default=ALL_PROVINCES)
    parser.add_argument('--energy', default=FOUR_TYPES)
    parser.add_argument('--cutoff', default=None, help='历史截止月 YYYY-MM，默认采用最新月')
    parser.add_argument('--horizon', type=int, default=6, help='预测未来 1–24 个月；回测固定 12 个月')
    args = validate(vars(parser.parse_args()))
    result = calculate(read_workbook(), args, model())
    run_id = 'chronos-' + uuid4().hex
    run_dir = OUTPUTS / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    receipt = dict(run_id=run_id, operation=args['operation'], arguments=args, result=result,
                   completed_at=datetime.now().astimezone().isoformat(),
                   retention='内部计算证据，需人工确认后清理；不含模型权重。')
    path = run_dir / 'manifest.json'
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    print(f'已完成内部核验，计算回执：{path}')
    return 0


if __name__ == '__main__': raise SystemExit(main())
