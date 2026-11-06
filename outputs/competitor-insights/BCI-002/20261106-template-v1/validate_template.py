"""BCI-002 静态校验：模板定义、人读镜像、下拉清单、前端接线。

只读，不改任何业务文件。运行（项目根目录）：
    ../Scripts/python.exe -B outputs/competitor-insights/BCI-002/20261106-template-v1/validate_template.py

退出码 0 = 全部断言通过；1 = 有失败。
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]  # outputs/competitor-insights/BCI-002/<run-id>/ -> 项目根
TPL_DIR = ROOT / "competitor_insight" / "templates"
TPL_JSON = TPL_DIR / "nev_user_insight_template.json"
TPL_MD = TPL_DIR / "nev_user_insight_template.md"
TPL_README = TPL_DIR / "README.md"
MANIFEST = ROOT / "competitor_insight" / "web" / "templates.json"
BCI_JS = ROOT / "competitor_insight" / "web" / "bci.js"

TYPES = {"text", "enum", "multi", "number", "date"}
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (" | " + str(detail) if detail else ""))


for path in (TPL_JSON, TPL_MD, TPL_README, MANIFEST, BCI_JS):
    check("文件存在：" + path.name, path.is_file(), str(path.relative_to(ROOT)))

tmpl = json.loads(TPL_JSON.read_text(encoding="utf-8"))
md = TPL_MD.read_text(encoding="utf-8")
manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
js = BCI_JS.read_text(encoding="utf-8")

# —— A1 模板标识 ——
check("A1 模板标识齐全",
      tmpl.get("template_id") == "nev_user_insight" and tmpl.get("name") and
      tmpl.get("version") == "v1" and tmpl.get("status") == "ready" and
      bool(tmpl.get("scenario")) and bool(tmpl.get("source_baseline", {}).get("path")),
      {k: tmpl.get(k) for k in ("template_id", "version", "status")})

groups = tmpl.get("groups") or []
dims = tmpl.get("dimensions") or []
check("A2 分组 8 个", len(groups) == 8, len(groups))
check("A2 维度 43 项", len(dims) == 43, len(dims))
check("A2 维度字段完整",
      all(all(d.get(k) not in (None, "", []) for k in
              ("id", "name", "group", "type", "description", "qualified")) and "required" in d
          for d in dims))

group_ids = {g["id"] for g in groups}
check("A2 维度分组均存在", all(d["group"] in group_ids for d in dims),
      sorted({d["group"] for d in dims} - group_ids))
check("A2 维度 ID 唯一", len({d["id"] for d in dims}) == len(dims), len(dims))

# —— A3 类型与选项 ——
check("A3 类型合法", all(d["type"] in TYPES for d in dims),
      sorted({d["type"] for d in dims}))
check("A3 enum/multi 均带 options",
      all(bool(d.get("options")) for d in dims if d["type"] in ("enum", "multi")))

# —— A4 说明与合格标准 ——
check("A4 每维说明长度 >= 8 字", all(len(d["description"]) >= 8 for d in dims))
check("A4 每维合格标准长度 >= 8 字", all(len(d["qualified"]) >= 8 for d in dims))
required = [d for d in dims if d["required"] is True]
check("A4 必填 28 项 / 选填 15 项", len(required) == 28 and len(dims) - len(required) == 15, len(required))

# —— A5 人读镜像与示例 ——
missing_ids = [d["id"] for d in dims if d["id"] not in md]
check("A5 md 覆盖全部 43 个维度 ID", not missing_ids, missing_ids[:5])
missing_groups = [g for g in group_ids if g not in md]
check("A5 md 覆盖全部 8 个分组 ID", not missing_groups, missing_groups)
check("A5 示例标注报告章节来源",
      all(("P%d" % i) in md for i in range(1, 11)))

# —— A8 清单与前端接线 ——
items = {t["id"]: t for t in manifest.get("templates", [])}
check("A8 清单含新能源模板且 ready",
      items.get("nev_user_insight", {}).get("status") == "ready",
      items.get("nev_user_insight"))
check("A8 清单含新车型模板且 pending 并写明待业务提供",
      items.get("new_model_user_insight", {}).get("status") == "pending" and
      "业务提供" in items.get("new_model_user_insight", {}).get("reason", ""),
      items.get("new_model_user_insight"))
check("A8 bci.js 不含写死的模板名", "新能源用户洞察模板" not in js and "新车型用户洞察模板" not in js)
check("A8 bci.js 不含旧待生成文案", "待生成" not in js and "已立 BCI-002" not in js)
check("A8 bci.js 从清单读取",
      "templatesUrl" in js and "loadTemplates" in js and "templates.json" in js)

# —— A9 加载失败降级 ——
check("A9 清单加载失败有降级分支",
      ".catch(() =>" in js and "模板清单加载失败" in js and "本次不选模板" in js)

failed = [r for r in results if not r[1]]
print("\n===== 汇总: %d/%d PASS =====" % (len(results) - len(failed), len(results)))
for name, _, detail in failed:
    print("  FAIL:", name, detail)
sys.exit(1 if failed else 0)
