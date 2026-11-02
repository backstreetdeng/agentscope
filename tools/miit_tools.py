"""款型配置信息（miit schema）只读工具 + 硬参数映射 + car_id 对账（MKT-001 / S4）。

数据源：3.146 `vectordb` 库 `miit` schema（只读账户，psycopg2 直连）。
两张表：
  - ods_pz_base_info   款型基础信息（model_name / type_name / car_id / file_name / create_time）
  - ods_pz_detail_info 款型明细信息（key-value 长表：pz_name / pz_value，car_id 关联）

口径（2026-11-02 用户确认）：对外统一以「款型配置信息」描述，不带来源站点字样。
P0 硬参数以本表配置值为唯一锚；续航存在 CLTC/WLTC/NEDC 三种口径，P0 锚定优先 CLTC，
其余口径保留并标注，不得合并为单值。
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras
from agentscope.message import TextBlock
from agentscope.tool import ToolChunk

from tools.custom_tools import ReadOnlyBusinessTool, record_tool_call

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "miit"

# pz_name → 标准字段（硬参数映射表）。续航三口径并列，CLTC 为 P0 首选锚。
HARD_PARAM_KEYS: dict[str, list[str]] = {
    "cltc_range_km": ["CLTC纯电续航里程(km)"],
    "wltc_range_km": ["WLTC纯电续航里程(km)"],
    "nedc_range_km": ["NEDC纯电续航里程(km)"],
    "curb_weight_kg": ["整备质量(kg)"],
    "energy_consumption_kwh_100km": ["百公里耗电量(kWh/100km)"],
    "battery_energy_kwh": ["电池能量(kWh)"],
}


def _load_env() -> dict[str, str]:
    cfg: dict[str, str] = {}
    for name in (".env", ".env.new-car"):
        f = PROJECT_ROOT / name
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return cfg


class MiitService:
    """款型配置信息只读访问（miit schema）。"""

    def __init__(self) -> None:
        self._cfg = _load_env()

    def _connect(self) -> psycopg2.extensions.connection:
        return psycopg2.connect(
            host=self._cfg.get("NEW_CAR_PG_HOST", "192.168.3.146"),
            port=int(self._cfg.get("NEW_CAR_PG_PORT", "5432")),
            dbname=self._cfg.get("NEW_CAR_PG_DATABASE", "vectordb"),
            user=self._cfg.get("NEW_CAR_PG_USER", ""),
            password=self._cfg.get("NEW_CAR_PG_PASSWORD", ""),
            connect_timeout=8,
        )

    @staticmethod
    def _iso(ts: Any) -> str:
        return ts.strftime("%Y-%m-%d") if ts is not None else ""

    def search_models(self, keyword: str, limit: int = 10) -> dict[str, Any]:
        keyword = (keyword or "").strip()
        limit = max(1, min(int(limit), 50))
        conn = self._connect()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if keyword:
                    cur.execute(
                        f'SELECT model_name, type_name, car_id, file_name, create_time '
                        f'FROM "{SCHEMA}".ods_pz_base_info '
                        f'WHERE model_name ILIKE %s OR type_name ILIKE %s '
                        f'ORDER BY create_time DESC LIMIT %s',
                        (f"%{keyword}%", f"%{keyword}%", limit),
                    )
                else:
                    cur.execute(
                        f'SELECT model_name, type_name, car_id, file_name, create_time '
                        f'FROM "{SCHEMA}".ods_pz_base_info ORDER BY create_time DESC LIMIT %s',
                        (limit,),
                    )
                rows = cur.fetchall()
        finally:
            conn.close()
        items = [
            {"model_name": r["model_name"], "type_name": r["type_name"],
             "car_id": r["car_id"], "file_name": r["file_name"],
             "create_time": self._iso(r["create_time"])}
            for r in rows
        ]
        return {"success": True, "total": len(items), "items": items}

    def model_detail(self, car_id: str, max_items: int = 30) -> dict[str, Any]:
        car_id = (car_id or "").strip()
        if not car_id:
            raise ValueError("car_id 不能为空。")
        max_items = max(1, min(int(max_items), 60))
        hard_keys = [k for keys in HARD_PARAM_KEYS.values() for k in keys]
        conn = self._connect()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    f'SELECT model_name, type_name, car_id, file_name, create_time '
                    f'FROM "{SCHEMA}".ods_pz_base_info WHERE car_id = %s LIMIT 1',
                    (car_id,),
                )
                base = cur.fetchone()
                if base is None:
                    raise ValueError(f"款型不存在：{car_id}")
                # 硬参数优先返回，其余明细限量，避免整表 276 项撑爆上下文。
                cur.execute(
                    f'SELECT pz_name, pz_value, create_time '
                    f'FROM "{SCHEMA}".ods_pz_detail_info '
                    f'WHERE car_id = %s AND pz_name = ANY(%s) ORDER BY pz_name',
                    (car_id, hard_keys),
                )
                hard_rows = cur.fetchall()
                cur.execute(
                    f'SELECT pz_name, pz_value, create_time '
                    f'FROM "{SCHEMA}".ods_pz_detail_info '
                    f'WHERE car_id = %s AND NOT (pz_name = ANY(%s)) ORDER BY pz_name LIMIT %s',
                    (car_id, hard_keys, max(0, max_items - len(hard_rows))),
                )
                other_rows = cur.fetchall()
                rows = hard_rows + other_rows
        finally:
            conn.close()
        items = [
            {"car_id": car_id, "model_name": base["model_name"], "type_name": base["type_name"],
             "create_time": self._iso(r["create_time"]), "pz_name": r["pz_name"], "pz_value": r["pz_value"]}
            for r in rows
        ]
        return {
            "success": True,
            "car_id": car_id,
            "model_name": base["model_name"],
            "type_name": base["type_name"],
            "total": len(items),
            "items": items,
            "hard_params": self.extract_hard_params(rows),
        }

    @staticmethod
    def extract_hard_params(rows: list[dict[str, Any]]) -> dict[str, Any]:
        """从 detail 行提取硬参数，保留口径并列与原始 pz_name。"""
        by_name: dict[str, str] = {r["pz_name"]: r["pz_value"] for r in rows}
        params: dict[str, Any] = {}
        for field, keys in HARD_PARAM_KEYS.items():
            params[field] = {k: by_name.get(k) for k in keys if by_name.get(k) is not None}
        # 便捷字段：P0 首选 CLTC 续航
        cltc = params["cltc_range_km"]
        params["_primary_range_km"] = next((v for v in cltc.values() if v), "")
        return params

    def reconcile(self) -> dict[str, Any]:
        """base 与 detail 的 car_id 一致性对账（只读，不落库）。"""
        conn = self._connect()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(f'SELECT count(DISTINCT car_id) AS n FROM "{SCHEMA}".ods_pz_base_info')
                base_count = cur.fetchone()["n"]
                cur.execute(f'SELECT count(DISTINCT car_id) AS n FROM "{SCHEMA}".ods_pz_detail_info')
                detail_count = cur.fetchone()["n"]
                cur.execute(
                    f'SELECT count(*) AS n FROM ('
                    f'SELECT car_id FROM "{SCHEMA}".ods_pz_base_info '
                    f'EXCEPT SELECT car_id FROM "{SCHEMA}".ods_pz_detail_info) t'
                )
                missing_detail = cur.fetchone()["n"]
                cur.execute(
                    f'SELECT count(*) AS n FROM ('
                    f'SELECT car_id FROM "{SCHEMA}".ods_pz_detail_info '
                    f'EXCEPT SELECT car_id FROM "{SCHEMA}".ods_pz_base_info) t'
                )
                missing_base = cur.fetchone()["n"]
        finally:
            conn.close()
        return {
            "success": True,
            "base_car_count": base_count,
            "detail_car_count": detail_count,
            "missing_in_detail": missing_detail,
            "missing_in_base": missing_base,
            "consistent": missing_detail == 0 and missing_base == 0,
        }


def _chunk(result: dict[str, Any]) -> ToolChunk:
    return ToolChunk(content=[TextBlock(text=json.dumps(result, ensure_ascii=False, default=str))])


class MiitSearchModelsTool(ReadOnlyBusinessTool):
    """按车型/款型名搜索款型基础信息（P0 款型配置信息）。"""

    name = "miit_search_models"
    description = (
        "在款型配置信息库（P0）中按车型名或款型名模糊搜索款型基础信息，"
        "返回 car_id、model_name、type_name、create_time。car_id 用于后续查询配置明细。"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "model": {"type": "string", "description": "车型名或款型名关键词，例如：宋PLUS。"},
            "limit": {"type": "integer", "description": "返回条数，默认 10，最大 50。", "default": 10},
        },
        "required": ["model"],
    }

    async def call(self, model: str, limit: int = 10) -> ToolChunk:
        try:
            result = await asyncio.to_thread(MiitService().search_models, model, limit)
            record_tool_call(self.name, "success", f"model={model[:60]}; total={result.get('total', 0)}")
            return _chunk(result)
        except Exception as exc:
            record_tool_call(self.name, "error", f"model={model[:60]}; error={type(exc).__name__}: {exc}")
            raise


class MiitGetModelDetailTool(ReadOnlyBusinessTool):
    """按 car_id 获取款型配置明细（P0 款型配置信息）。"""

    name = "miit_get_model_detail"
    description = (
        "按 car_id 获取某款型的配置明细（硬参数优先，其余明细限量返回，默认 30 项），"
        "并附硬参数汇总（CLTC/WLTC/NEDC 续航、整备质量、百公里耗电量、电池能量）。"
        "P0 硬参数以此返回值为唯一锚。"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "car_id": {"type": "string", "description": "款型唯一标识，来自 miit_search_models 返回。"},
            "max_items": {"type": "integer", "description": "返回明细条数上限（硬参数不计入），默认 30，最大 60。", "default": 30},
        },
        "required": ["car_id"],
    }

    async def call(self, car_id: str, max_items: int = 30) -> ToolChunk:
        try:
            result = await asyncio.to_thread(MiitService().model_detail, car_id, max_items)
            record_tool_call(self.name, "success", f"car_id={car_id}; total={result.get('total', 0)}")
            return _chunk(result)
        except Exception as exc:
            record_tool_call(self.name, "error", f"car_id={car_id}; error={type(exc).__name__}: {exc}")
            raise


def build_miit_toolkit() -> list[ReadOnlyBusinessTool]:
    """竞品对标 Agent 的 P0 款型配置信息只读工具集。"""
    return [MiitSearchModelsTool(), MiitGetModelDetailTool()]
