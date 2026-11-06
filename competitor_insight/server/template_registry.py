"""BCI-004 · 模板注册表。

职责：读取 `competitor_insight/web/templates.json` 清单（只读，不修改），
按清单加载模板定义与同名 `*.source-map.json`，并完成两者的一致性校验。

约定：
- 清单里的 `definition` 是相对项目根的路径；
- source-map 与模板定义同目录，文件名为 `<template_id>.source-map.json`；
- 只有 `status=ready` 且 source-map 校验通过的模板才允许生成档案。

本模块只读文件，不连接数据库、不写任何状态。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from competitor_insight.server.source_map import (
    SourceMap,
    SourceMapError,
    load_source_map,
    load_template_definition,
    validate_against_template,
)

ARCHIVE_TEMPLATE_ID = "user_insight_archive"


class TemplateRegistryError(ValueError):
    """模板清单、定义或 source-map 不可用。"""


@dataclass(frozen=True)
class TemplateBundle:
    template_id: str
    label: str
    version: str
    status: str
    definition_path: Path
    definition: dict[str, Any]
    source_map_path: Path | None
    source_map: SourceMap | None

    @property
    def dimension_count(self) -> int:
        return len(self.definition.get("dimensions", []))

    def require_source_map(self) -> SourceMap:
        if self.source_map is None:
            raise TemplateRegistryError(f"模板 {self.template_id} 缺少 source-map，不能生成档案")
        return self.source_map


class TemplateRegistry:
    """模板清单 + 定义 + source-map 的只读加载器。"""

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = Path(project_root or Path(__file__).resolve().parents[2]).resolve()
        self.catalog_path = self.project_root / "competitor_insight" / "web" / "templates.json"

    def _read_catalog(self) -> dict[str, Any]:
        if not self.catalog_path.exists():
            raise TemplateRegistryError(f"模板清单不存在：{self.catalog_path}")
        try:
            data = json.loads(self.catalog_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise TemplateRegistryError(f"模板清单解析失败：{exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("templates"), list):
            raise TemplateRegistryError("模板清单缺少 templates 数组")
        return data

    def list_entries(self) -> list[dict[str, Any]]:
        return [dict(entry) for entry in self._read_catalog()["templates"]]

    def find_entry(self, template_id: str) -> dict[str, Any]:
        for entry in self.list_entries():
            if entry.get("id") == template_id:
                return entry
        raise TemplateRegistryError(f"模板清单中没有 {template_id}")

    def resolve_definition_path(self, entry: dict[str, Any]) -> Path:
        raw = entry.get("definition")
        if not isinstance(raw, str) or not raw.strip():
            raise TemplateRegistryError(f"模板 {entry.get('id')} 缺少 definition 路径")
        path = Path(raw)
        return path if path.is_absolute() else (self.project_root / path)

    def load(self, template_id: str) -> TemplateBundle:
        entry = self.find_entry(template_id)
        definition_path = self.resolve_definition_path(entry)
        definition = load_template_definition(definition_path)

        # 约定：source-map 与模板定义同目录，文件名用 template_id，便于与清单 id 对应
        source_map_path = definition_path.with_name(f"{template_id}.source-map.json")
        source_map: SourceMap | None = None
        if source_map_path.exists():
            source_map = load_source_map(source_map_path)
            validate_against_template(source_map, definition)

        return TemplateBundle(
            template_id=str(entry.get("id")),
            label=str(entry.get("label", entry.get("id"))),
            version=str(entry.get("version", definition.get("version", ""))),
            status=str(entry.get("status", "")),
            definition_path=definition_path,
            definition=definition,
            source_map_path=source_map_path if source_map_path.exists() else None,
            source_map=source_map,
        )

    def load_ready(self, template_id: str) -> TemplateBundle:
        bundle = self.load(template_id)
        if bundle.status != "ready":
            raise TemplateRegistryError(f"模板 {template_id} 状态为 {bundle.status}，不可用于生成档案")
        return bundle

    def validate_all(self) -> dict[str, list[str]]:
        """返回每个模板的问题列表；空列表表示通过。清单里未声明的模板不在此列。"""
        result: dict[str, list[str]] = {}
        for entry in self.list_entries():
            template_id = str(entry.get("id", ""))
            problems: list[str] = []
            try:
                self.load(template_id)
            except (TemplateRegistryError, SourceMapError) as exc:
                problems.append(str(exc))
            result[template_id] = problems
        return result
