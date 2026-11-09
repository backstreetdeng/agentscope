"""BCI-003 收敛校验：docs/harness-study.md 是否已降格为三块决策记录。

只读。运行（项目根目录）：
    ../Scripts/python.exe -B outputs/competitor-insights/BCI-003/20261109-decision-record/check_decisions.py

输出每条断言与汇总；退出码 0 = 全部通过。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DOC = ROOT / "competitor_insight" / "docs" / "harness-study.md"
EVIDENCE = ROOT / "outputs" / "competitor-insights" / "BCI-003"

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (" | " + str(detail) if detail != "" else ""))


text = DOC.read_text(encoding="utf-8")
lines = text.splitlines()
words = len(re.findall(r"[\u4e00-\u9fa5]", text)) + len(re.findall(r"[A-Za-z0-9_./-]+", text))

check("文档存在且非空", DOC.is_file() and len(lines) > 20, f"{DOC.name} {len(lines)} 行")
print(f"  统计：{len(lines)} 行 / 约 {words} 字")

# —— 定位与真源 ——
check("写明定位：派单/改规则前查阅", "派单" in text and "改 `RULES.md`" in text)
check("写明状态真源：BOARD.md 与各 TASK.md", "BOARD.md" in text and "TASK.md" in text)
check("无「由谁维护」空泛承诺", "维护人" not in text and not re.search(r"由\s*(TRAE|Codex|开发|产品)\s*(负责)?维护", text))

# —— 只保留三块 ——
heads = [line.strip() for line in lines if line.startswith("## ")]
expected = ["## 1. 已采纳（4 条，均已落地）", "## 2. 已推翻（4 条）", "## 3. 不立项（5 条，逐条写明理由，避免重复提出）", "## 证据"]
check("章节只保留三块 + 证据", heads == expected, heads)

removed = ["## 0. 结论先行", "## 1. 三个来源分别读到了什么", "## 2. 五问", "## 3. 未验证清单",
           "## 4. 读取证据", "# 5. 全 workspace 复核", "### Q1", "### Q2", "### Q3", "### Q4", "### Q5"]
hit = [h for h in removed if h in text]
check("过程分析 / 五问 / 逐文件摘录已删除", hit == [], hit)


def rows_between(start, end):
    """取 start 标题之后、end 标题之前的表格数据行（跳过表头与分隔行）。"""
    seg = text.split(start, 1)[1].split(end, 1)[0]
    out = []
    for line in seg.splitlines():
        s = line.strip()
        if s.startswith("|") and not s.startswith("|---") and "---|" not in s:
            # 单元格内的 \| 是转义竖线，先占位再切分，避免列数被撑开。
            out.append([c.strip().replace("\x00", "|") for c in s.replace("\\|", "\x00").strip("|").split("|")])
    return out[1:]  # 去掉表头


adopted = rows_between("## 1. 已采纳", "## 2. 已推翻")
overturned = rows_between("## 2. 已推翻", "## 3. 不立项")
dropped = rows_between("## 3. 不立项", "## 证据")

check("已采纳 4 条", len(adopted) == 4, len(adopted))
check("已采纳每条写明落点与提交", all(len(r) == 4 and "`1bd7eee`" in r[2]
      and re.search(r"`[^`]+\.(json|py|md)`", r[2]) for r in adopted),
      [r[0] for r in adopted])
check("已采纳每条写明现在拦得住什么", all(len(r) == 4 and len(r[3]) > 10 for r in adopted))

check("已推翻 4 条", len(overturned) == 4, len(overturned))
check("已推翻每条含日期与依据", all(len(r) == 4 and "2026-11-06" in r[3] for r in overturned),
      [r[0] for r in overturned])

check("不立项 5 条", len(dropped) == 5, len(dropped))
check("不立项每条写明为什么不值得做", all(len(r) == 4 and len(r[2]) > 8 for r in dropped))
check("不立项每条写明重新考虑条件", all(len(r) == 4 and len(r[3]) > 5 for r in dropped), [r[0] for r in dropped])
check("整类不适用一次性记录", "整类不适用" in text and "插件" in text and "覆盖率" in text)

# —— 证据可回溯 ——
for run in ["20261106-harness-study", "20261106-workspace-rescan", "20261109-decision-record"]:
    check(f"证据目录存在：{run}", (EVIDENCE / run).is_dir())
check("证据段含文件链接", text.count("file:///") >= 4, text.count("file:///"))
check("关联落地实现证据（BCI-005）", "BCI-005" in text and "reverse-verify.log" in text)

print("\n===== 汇总: %d/%d PASS =====" % (sum(1 for _, ok, _ in results if ok), len(results)))
sys.exit(0 if all(ok for _, ok, _ in results) else 1)
