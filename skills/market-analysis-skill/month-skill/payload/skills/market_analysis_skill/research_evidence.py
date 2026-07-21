"""月报 Skill 的研究证据清单加载器。

研究工作流产生的 JSON 不能无条件注入月报提示词：它们有明确的观察月份、来源
边界和不确定项。本模块只读取通过 ``evidence_manifest.json`` 显式批准、且与当前
报告月份匹配的证据包，避免把 5 月结论错误带入其它月份。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ResearchSource:
    """研究证据包内一条可回溯来源的最小信息。"""

    title: str
    url_or_path: str
    tier: str
    published_or_observed_at: str


@dataclass(frozen=True)
class ResearchEvidence:
    """一份与当前月报周期匹配的经过门禁的研究证据。"""

    evidence_id: str
    title: str
    item_name: str
    overall_judgement: str
    observed_fact: str
    claim_boundary: str
    allowed_use: str
    sources: tuple[ResearchSource, ...]
    uncertain: tuple[str, ...]

    @property
    def source_tier(self) -> str:
        return self.sources[0].tier if self.sources else "C"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.evidence_id,
            "title": self.title,
            "item_name": self.item_name,
            "source_tier": self.source_tier,
            "source_count": len(self.sources),
            "uncertain": list(self.uncertain),
        }

    def to_prompt_block(self, max_chars: int) -> str:
        source_lines = [
            f"- [{source.tier}级] {source.title} | {source.url_or_path} | {source.published_or_observed_at}"
            for source in self.sources[:3]
        ]
        content = (
            f"{self.evidence_id}（研究证据；主题={self.title}）\n"
            f"已验证事实：{self.observed_fact}\n"
            f"可用判断：{self.overall_judgement}\n"
            f"允许用途：{self.allowed_use}\n"
            f"引用边界：{self.claim_boundary}\n"
            f"不确定项：{'、'.join(self.uncertain) if self.uncertain else '无'}\n"
            f"来源：\n" + "\n".join(source_lines)
        )
        return _compact(content, max_chars)


def load_research_evidence(
    settings: dict[str, Any] | None,
    report_period: str,
) -> tuple[list[ResearchEvidence], str]:
    """按报告周期读取获批证据包，失败时降级为无研究证据而非阻断月报。"""

    config = dict(settings or {})
    if not config.get("enabled", False):
        return [], "研究证据清单未启用。"

    manifest_value = str(config.get("manifest", "")).strip()
    if not manifest_value:
        return [], "研究证据清单未配置 manifest 路径。"
    manifest_path = _resolve_project_path(manifest_value)
    if not manifest_path.is_file():
        return [], f"未找到研究证据清单：{manifest_path.name}。"

    try:
        manifest = _read_json_object(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [], f"研究证据清单读取失败：{type(exc).__name__}。"

    if manifest.get("status") != "pilot_approved_for_runtime":
        return [], "研究证据清单尚未获准接入运行时。"

    max_items = max(1, min(int(config.get("max_items", 6)), 12))
    evidence: list[ResearchEvidence] = []
    skipped = 0
    for item in manifest.get("evidence_packs", []):
        if not isinstance(item, dict) or item.get("status") != "approved":
            continue
        periods = {str(value).strip() for value in item.get("applicable_periods", [])}
        if report_period not in periods:
            continue
        evidence_id = str(item.get("evidence_id", "")).strip()
        if not re.fullmatch(r"R\d+", evidence_id):
            skipped += 1
            continue
        pack_path = (manifest_path.parent / str(item.get("file", ""))).resolve()
        if manifest_path.parent.resolve() not in pack_path.parents or not pack_path.is_file():
            skipped += 1
            continue
        try:
            pack = _read_json_object(pack_path)
        except (OSError, ValueError, json.JSONDecodeError):
            skipped += 1
            continue
        if not str(pack.get("data_quality_status", "")).lower().startswith("passed"):
            skipped += 1
            continue
        evidence.append(
            ResearchEvidence(
                evidence_id=evidence_id,
                title=str(item.get("title") or pack.get("research_item_name") or evidence_id),
                item_name=str(pack.get("research_item_name") or "研究证据"),
                overall_judgement=str(pack.get("overall_judgement") or "[uncertain]"),
                observed_fact=str(pack.get("observed_fact") or "[uncertain]"),
                claim_boundary=str(pack.get("claim_boundary") or "仅作待核验线索。"),
                allowed_use=str(item.get("allowed_use") or "仅按来源和适用范围引用。"),
                sources=tuple(_build_sources(pack)),
                uncertain=tuple(str(value) for value in pack.get("uncertain", []) if str(value).strip()),
            ),
        )
        if len(evidence) >= max_items:
            break

    if not evidence:
        return [], f"当前周期 {report_period} 未匹配到可用研究证据。"
    suffix = f"；跳过 {skipped} 个无效包" if skipped else ""
    return evidence, f"当前周期 {report_period} 已加载 {len(evidence)} 个研究证据包{suffix}。"


def _build_sources(pack: dict[str, Any]) -> list[ResearchSource]:
    titles = _as_list(pack.get("source_title"))
    urls = _as_list(pack.get("source_url_or_path"))
    tiers = _as_list(pack.get("source_tier"))
    dates = _as_list(pack.get("published_or_observed_at"))
    source_count = max(len(titles), len(urls), len(tiers), len(dates), 1)
    sources: list[ResearchSource] = []
    for index in range(source_count):
        sources.append(
            ResearchSource(
                title=_item_at(titles, index, "未命名来源"),
                url_or_path=_item_at(urls, index, "未提供路径"),
                tier=_item_at(tiers, index, "C"),
                published_or_observed_at=_item_at(dates, index, "未提供日期"),
            ),
        )
    return sources


def _read_json_object(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object")
    return data


def _resolve_project_path(value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (PROJECT_DIR / path).resolve()


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)] if value not in (None, "") else []


def _item_at(items: list[str], index: int, fallback: str) -> str:
    return items[index] if index < len(items) and items[index].strip() else fallback


def _compact(value: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip("，。；; ") + "…"
