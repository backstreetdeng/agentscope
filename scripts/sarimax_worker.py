"""Local subprocess: calculate a SARIMAX job; input and output are JSON."""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / 'runtime' / 'sarimax-deps'))


def main():
    try:
        from integrations.chronos2_data import read_workbook
        from integrations.sarimax_forecast import calculate
        args = json.load(sys.stdin)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            if args.get('profile') == 'gd_oil':
                from integrations.oil_forecast import calculate as calculate_oil
                from integrations.sarimax_forecast import validate
                result = calculate_oil(read_workbook(), validate(args))
            else:
                result = calculate(read_workbook(), args)
        print(json.dumps({'ok': True, 'result': result}, ensure_ascii=False, allow_nan=False))
        return 0
    except Exception as exc:
        print(json.dumps({'ok': False, 'error': f'{type(exc).__name__}: {str(exc)[:250]}'}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
