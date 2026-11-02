"""竞品对标矩阵独立验收器（MKT-001 / S5 实现）。

输入：
  argv[1]           矩阵 JSON 文件路径（契约：assets/matrix-schema.json）
  --miit-dsn DSN    可选，PostgreSQL 连接串（3.146 vectordb），用于 P0 锚定对账
输出：
  stdout  结构化结果 JSON：{"passed": bool, "failures": [...]}
  退出码  0=通过；1=验收失败；2=用法错误
副作用：无（只读校验）

规则实现见 utils/benchmark_validation.py；验收门槛见 references/benchmark-matrix.md。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# skill 包目录带连字符，作为独立脚本执行时需手动定位项目根以导入 utils。
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from utils.benchmark_validation import validate_matrix


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: validate_matrix.py <matrix.json> [--miit-dsn DSN]", file=sys.stderr)
        return 2
    matrix_path = Path(sys.argv[1])
    # skill runtime 以隔离工作区为 cwd 执行，相对参数按 SKILL_RUN_ROOT 解析。
    if not matrix_path.is_absolute():
        run_root = os.environ.get("SKILL_RUN_ROOT")
        if run_root:
            matrix_path = Path(run_root) / matrix_path
    if not matrix_path.is_file():
        print(json.dumps({"passed": False, "failures": [f"矩阵文件不存在：{matrix_path}"]}, ensure_ascii=False))
        return 2
    matrix = json.loads(matrix_path.read_text(encoding="utf-8-sig"))
    miit_dsn = None
    if "--miit-dsn" in sys.argv:
        miit_dsn = sys.argv[sys.argv.index("--miit-dsn") + 1]
    failures = validate_matrix(matrix, miit_dsn)
    print(json.dumps({"passed": not failures, "failures": failures}, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
