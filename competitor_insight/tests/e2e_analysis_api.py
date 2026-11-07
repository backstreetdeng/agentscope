"""BCI-006 · 即时分析接口端到端断言（真实服务 + 真实库）。

运行：
    E:\\AI\\data\\envs\\helloagent\\Scripts\\python.exe -B competitor_insight/tests/e2e_analysis_api.py
    （可加 --base-url http://127.0.0.1:7860）

断言：
- 五款配置车型四源计数均 >0；
- 每款车四个磁贴齐全，样本基数 n 与定量源计数一致；
- 所有比例项同时带分子/分母；n<10 或题目作答<10 时不出比例并给原因；
- 「第一排序」「对手为什么赢」为空态且有具体原因；
- 选择/放弃原因各 16 维，且两侧维度标签一致；
- Q29 / Q27-Q28 定性原话带人数，未命中原话单列；
- Q5_5 推荐意愿用真实文本打分计算；
- 抽查 5 个指标回表重算，与接口数值一致。
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from competitor_insight.server import db  # noqa: E402
from competitor_insight.server.analysis_service import load_config  # noqa: E402

EXPECTED_LABELS = ["零跑B10", "铂智3X", "奇瑞iCAR V23", "海狮05 EV", "钛3"]
FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        FAILURES.append(message)
        print(f"FAIL  {message}")
    else:
        print(f"PASS  {message}")


def get_json(base: str, path: str) -> dict:
    with urllib.request.urlopen(base.rstrip("/") + path, timeout=120) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload.get("ok"):
        raise RuntimeError(f"{path} 返回失败：{payload}")
    return payload["data"]


def ratio_items(metric: dict) -> list[dict]:
    items = []
    for key in ("items", "top"):
        for item in metric.get(key) or []:
            if "count" in item:
                items.append(item)
    return items


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:7860")
    args = parser.parse_args()

    models_payload = get_json(args.base_url, "/api/bci/analysis/models")
    models = models_payload["models"]
    check(len(models) == 5, "车型清单为 5 款配置车型")
    check([item["label"] for item in models] == EXPECTED_LABELS, "车型顺序与配置一致")
    for item in models:
        for source, label in (("quant", "定量"), ("interview", "深访"), ("reputation", "口碑"), ("miit", "配置")):
            check(item["sources"][source] > 0, f"{item['label']} {label}源 > 0（{item['sources'][source]}）")

    analyses = {}
    for model in models:
        data = get_json(args.base_url, "/api/bci/analysis/analyze?model=" + model["key"])
        analyses[model["label"]] = data
        tiles = data["tiles"]
        check(set(tiles) == {"profile", "attention", "winloss", "satisfaction"}, f"{model['label']} 四个磁贴齐全")
        check(data["model"]["sources"]["quant"] == data["sources"]["quant"], f"{model['label']} 样本基数与源计数一致")

        attention = next(m for m in tiles["attention"]["metrics"] if m["key"] == "attention")
        check(attention["n"] == model["sources"]["quant"], f"{model['label']} 关注题 n 等于定量总样本")
        check(len(attention["items"]) == 16, f"{model['label']} 关注题 16 维")
        first = next(m for m in tiles["attention"]["metrics"] if m["key"] == "first_ranking")
        check(first["status"] == "empty" and "无排序题" in first["reason"], f"{model['label']} 第一排序空态+原因")

        metrics = {m["key"]: m for m in tiles["winloss"]["metrics"]}
        check(len(metrics["q3_23"]["items"]) == 16, f"{model['label']} 选择原因 16 维")
        check(len(metrics["q3_24_1"]["items"]) == 16, f"{model['label']} 放弃原因 16 维")
        check(
            [i["label"] for i in metrics["q3_23"]["items"]]
            == [i["label"] for i in metrics["q3_24_1"]["items"]],
            f"{model['label']} 选择/放弃两侧维度标签一致",
        )
        check(metrics["opponent_why_win"]["status"] == "empty", f"{model['label']} 对手为什么赢为空态")
        check(bool(metrics["opponent_why_win"]["reason"]), f"{model['label']} 对手为什么赢有空态原因")
        for key in ("win_quotes", "abandon_quotes"):
            quotes = metrics[key]
            check(quotes["status"] in {"ok", "insufficient", "empty"}, f"{model['label']} {key} 状态合法")
            check(quotes["people"] >= 0, f"{model['label']} {key} 标注深访人数")
            check("不做比例" in quotes["note"], f"{model['label']} {key} 声明不做比例")
            check(
                all(item["dimensions"] or item in quotes["unmatched"] for item in quotes["items"]),
                f"{model['label']} {key} 未命中原话单列",
            )

        satisfaction = {m["key"]: m for m in tiles["satisfaction"]["metrics"]}
        check(len(satisfaction["dimensions"]["items"]) == 16, f"{model['label']} 满意度 16 维")
        check(satisfaction["overall"]["answered"] > 0, f"{model['label']} 整体满意度有作答")
        check(satisfaction["recommendation"]["answered"] > 0, f"{model['label']} 推荐意愿有真实作答（Q5_5）")
        check(satisfaction["recommendation"]["mean"] is not None, f"{model['label']} 推荐意愿有均分")

        for tile in tiles.values():
            for metric in tile["metrics"]:
                for item in ratio_items(metric):
                    if item.get("ratio") is None:
                        check(bool(item.get("ratio_hidden_reason")), f"{model['label']} {metric['key']} 隐藏比例有原因")
                    else:
                        check(item["n"] >= 10, f"{model['label']} {metric['key']} 比例分母 >=10")
                        check(
                            abs(item["ratio"] - round(item["count"] / item["n"] * 100, 1)) < 0.05,
                            f"{model['label']} {metric['key']} 比例可复算（{item['count']}/{item['n']}）",
                        )
        check(len(data["summary"]) >= 3, f"{model['label']} 综合结论至少 3 条")
        print(
            f"  摘要 {model['label']}：定量 {data['sources']['quant']} / 深访 {data['sources']['interview']}"
            f" / 口碑 {data['sources']['reputation']} / 配置 {data['sources']['miit']}；"
            f"关注 TOP1 {attention['top'][0]['label']} {attention['top'][0]['count']}/{attention['top'][0]['n']}"
            f"（{attention['top'][0]['ratio']}%）；整体 {satisfaction['overall']['mean']} 分；"
            f"推荐 {satisfaction['recommendation']['mean']} 分（n={satisfaction['recommendation']['answered']}）"
        )

    # 回表抽查：每款车抽 1 个关注维、1 个放弃维、1 个满意度均分。
    cfg = db.load_env()
    conn = db.connect(cfg)
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor()
    config_models = {item["label"]: item for item in load_config()["models"]}
    for label, data in analyses.items():
        model = config_models[label]
        attention = next(m for m in data["tiles"]["attention"]["metrics"] if m["key"] == "attention")
        sample = next(item for item in attention["items"] if item["count"] > 0)
        qid = sample["key"]
        cur.execute(
            "SELECT count(*) FROM user_insight.quant_sample "
            "WHERE purchase_model = ANY(%s) AND answers_text ? %s",
            (model["quant_models"], qid),
        )
        actual = int(cur.fetchone()[0])
        check(actual == sample["count"], f"{label} 回表重算关注 {qid} = {actual}")

        abandon = next(m for m in data["tiles"]["winloss"]["metrics"] if m["key"] == "q3_24_1")
        sample = next(item for item in abandon["items"] if item["count"] > 0)
        qid = sample["key"]
        cur.execute(
            "SELECT count(*) FROM user_insight.quant_sample "
            "WHERE purchase_model = ANY(%s) AND answers_text ? %s",
            (model["quant_models"], qid),
        )
        actual = int(cur.fetchone()[0])
        check(actual == sample["count"], f"{label} 回表重算放弃 {qid} = {actual}")

        dims = next(m for m in data["tiles"]["satisfaction"]["metrics"] if m["key"] == "dimensions")
        sample = dims["top"][0]
        qid = sample["key"]
        cur.execute(
            "SELECT round(avg(CASE WHEN answers_text->>%s ~ '^[0-9]+$' "
            "THEN (answers_text->>%s)::numeric END), 2), "
            "count(*) FILTER (WHERE answers_text->>%s ~ '^[0-9]+$') "
            "FROM user_insight.quant_sample WHERE purchase_model = ANY(%s)",
            (qid, qid, qid, model["quant_models"]),
        )
        mean, answered = cur.fetchone()
        check(float(mean) == sample["mean"], f"{label} 回表重算满意度 {qid} 均分 = {mean}")
        check(int(answered) == sample["answered"], f"{label} 回表重算满意度 {qid} 作答 = {answered}")
    conn.close()

    print("\n===== RESULT =====")
    if FAILURES:
        print(f"FAILED {len(FAILURES)} 项")
        for item in FAILURES:
            print(" -", item)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
