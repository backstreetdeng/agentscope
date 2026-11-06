"""BCI-002 第二轮验收：第二份模板 user_insight_archive 与原型 P.TROWS 的对齐校验。

输入：
  D:/work/2026/7.1 同事 义欣/用户洞察需求/目标车型本竞品洞察智能体_交互原型v2.html（第 386 行 P.TROWS，只读）
  competitor_insight/templates/user_insight_archive_template.json
  competitor_insight/templates/nev_user_insight_template.json（只读，验证未被改动）
  competitor_insight/web/templates.json
输出：stdout 检查明细；退出码 0 = 全部通过。不改任何业务文件。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
PROTO = Path(r"D:/work/2026/7.1 同事 义欣/用户洞察需求/目标车型本竞品洞察智能体_交互原型v2.html")
TPL = ROOT / "competitor_insight/templates/user_insight_archive_template.json"
NEV = ROOT / "competitor_insight/templates/nev_user_insight_template.json"
MANIFEST = ROOT / "competitor_insight/web/templates.json"


def slice_array(text: str, start: int) -> str:
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ValueError("数组未闭合")


def main() -> int:
    fails: list[str] = []
    raw = PROTO.read_text(encoding="utf-8", errors="replace")
    pos = raw.find('"TROWS":')
    rows = json.loads(slice_array(raw, raw.find("[", pos)))
    proto_names = [(r[0], r[1] or r[0]) for r in rows]

    tpl = json.loads(TPL.read_text(encoding="utf-8"))
    dims = tpl["dimensions"]
    groups = [g["id"] for g in tpl["groups"]]

    if len(proto_names) != 43:
        fails.append(f"原型行数 {len(proto_names)} != 43")
    if len(dims) != 43:
        fails.append(f"模板维度数 {len(dims)} != 43")
    if len(tpl["groups"]) != 12:
        fails.append(f"分组数 {len(tpl['groups'])} != 12")

    diff = [
        (i + 1, p[1], d["name"])
        for i, (p, d) in enumerate(zip(proto_names, dims))
        if p[1] != d["name"]
    ]
    if diff:
        fails.extend([f"名称差异 #{i}: 原型={a} 模板={b}" for i, a, b in diff])
    print(f"A11 子项名称/顺序: {len(dims) - len(diff)}/{len(proto_names)} 一致")

    ids = [d["id"] for d in dims]
    if len(set(ids)) != len(ids):
        fails.append("维度 id 重复")
    for d in dims:
        if d["group"] not in groups:
            fails.append(f"{d['id']} 的 group={d['group']} 悬空")
        for key in ("description", "qualified"):
            if not str(d.get(key, "")).strip():
                fails.append(f"{d['id']} 缺 {key}")
        if d["type"] in ("enum", "multi") and not d.get("options"):
            fails.append(f"{d['id']} 为 {d['type']} 但无 options")
    print(f"A12 结构: ids={len(set(ids))}, groups={groups and len(groups)}, 必填={sum(1 for d in dims if d['required'])}")

    nev = json.loads(NEV.read_text(encoding="utf-8"))
    if len(nev["dimensions"]) != 43 or len(nev["groups"]) != 8:
        fails.append("nev_user_insight 结构发生变化")
    print(f"A14 nev 未改: 8 组/43 维 = {len(nev['groups'])}/{len(nev['dimensions'])}，sha256={hashlib.sha256(NEV.read_bytes()).hexdigest()[:16]}")

    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    ready = [t for t in man["templates"] if t.get("status") == "ready"]
    pending = [t for t in man["templates"] if t.get("status") == "pending"]
    for t in man["templates"]:
        if t.get("status") == "ready" and not (ROOT / t["definition"]).exists():
            fails.append(f"{t['id']} 的 definition 文件不存在")
        if t.get("status") == "pending" and not t.get("reason"):
            fails.append(f"{t['id']} pending 但无 reason")
    labels = [t["label"] for t in ready]
    print(f"A13 清单: ready={labels} pending={[t['label'] for t in pending]}")
    if "用户洞察档案模板" not in labels:
        fails.append("清单缺少「用户洞察档案模板」")
    if "new_model_user_insight" not in [t["id"] for t in pending]:
        fails.append("新车型模板不在 pending")

    if fails:
        print("\nFAIL")
        for f in fails:
            print(" -", f)
        return 1
    print("\nPASS: 全部检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
