"""定位 D7 missing_evidence：打印首个 LLM 维的提示与模型原始返回（不含密钥）。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from competitor_insight.server import db  # noqa: E402
from competitor_insight.server.archive_generator import (  # noqa: E402
    ArchiveGenerator,
    GenerationError,
    PostgresInterviewSource,
)
from competitor_insight.server.llm_client import build_deepseek_client  # noqa: E402

client = build_deepseek_client()
calls = {"n": 0}


def traced(prompt: str) -> str:
    raw = client(prompt)
    calls["n"] += 1
    print("\n--- 调用", calls["n"], "---")
    print(prompt[:1200])
    print("--- 返回 ---")
    print(raw[:800])
    return raw


generator = ArchiveGenerator(PostgresInterviewSource(db.connect), llm=traced, model=client.model)
try:
    draft = generator.generate("R003")
    print("OK fields:", len(draft.fields))
except GenerationError as exc:
    print("FAIL:", exc.code, str(exc))
