"""BCI-004 · 原话检索与证据刷新。

两条只读能力：
- `search()`：在答案 / 证据 / 标签证据 / 当前档案值里按关键词找人话；
- `refresh_refs()`：档案里存的是原话快照，读取时按 ID 回库复查，
  查不到则标 `source_missing=true`，但保留快照，不静默删除。

所有查询按 `interview_id` 过滤；`tag_evidence` 本身没有受访者列，
必须 `JOIN user_insight.tag` 后再过滤。
"""

from __future__ import annotations

import re
from typing import Any, Iterable

MAX_KEYWORD_LENGTH = 30
MAX_QUOTE_CHARS = 300
DEFAULT_LIMIT = 50
MAX_LIMIT = 50


class QuoteError(RuntimeError):
    """关键词、限制或查询参数非法。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def escape_like(keyword: str) -> str:
    """转义 ILIKE 通配符，避免用户输入变成模式匹配。"""
    return keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def _quoted(value: Any) -> str:
    return _clean_text(value)[:MAX_QUOTE_CHARS]


class QuoteService:
    def __init__(self, connect_fn) -> None:
        self._connect = connect_fn

    # ------------------------------------------------------------------ search

    def search(
        self,
        interview_id: str,
        keyword: str,
        *,
        limit: int = DEFAULT_LIMIT,
        archive_fields: Iterable[dict[str, Any]] = (),
    ) -> dict[str, Any]:
        cleaned = self._validate_keyword(keyword)
        if not 1 <= int(limit) <= MAX_LIMIT:
            raise QuoteError("invalid_limit", f"limit 必须在 1–{MAX_LIMIT} 之间")
        if not interview_id:
            raise QuoteError("invalid_interview", "interview_id 不能为空")

        pattern = f"%{escape_like(cleaned)}%"
        items: list[dict[str, Any]] = []
        counts = {"answer": 0, "evidence": 0, "tag_evidence": 0, "archive": 0}

        conn = self._connect()
        try:
            with conn.cursor() as cur:
                for kind, sql in (
                    (
                        "answer",
                        """
                        SELECT 'answer', answer_id, question_id, NULL, answer_text
                        FROM user_insight.answer
                        WHERE interview_id = %s AND answer_text ILIKE %s ESCAPE '\\'
                        ORDER BY question_id
                        LIMIT %s
                        """,
                    ),
                    (
                        "evidence",
                        """
                        SELECT 'evidence', evidence_id, question_id, speaker_label, quote_text
                        FROM user_insight.evidence
                        WHERE interview_id = %s AND quote_text ILIKE %s ESCAPE '\\'
                        ORDER BY question_id
                        LIMIT %s
                        """,
                    ),
                    (
                        "tag_evidence",
                        """
                        SELECT 'tag_evidence', te.tag_evidence_id, te.question_id,
                               te.speaker_label, te.quote_text
                        FROM user_insight.tag_evidence te
                        JOIN user_insight.tag t ON t.tag_id = te.tag_id
                        WHERE t.interview_id = %s AND te.quote_text ILIKE %s ESCAPE '\\'
                        ORDER BY te.question_id
                        LIMIT %s
                        """,
                    ),
                ):
                    remaining = int(limit) - len(items)
                    if remaining <= 0:
                        break
                    cur.execute(sql, (interview_id, pattern, remaining))
                    for row in cur.fetchall():
                        counts[kind] += 1
                        items.append(
                            {
                                "kind": kind,
                                "id": row[1],
                                "question_id": row[2],
                                "speaker": row[3],
                                "quote": _quoted(row[4]),
                                "source": kind,
                            }
                        )
        finally:
            conn.close()

        for field in archive_fields:
            if len(items) >= int(limit):
                break
            value = field.get("value_text")
            if value and cleaned.lower() in str(value).lower():
                counts["archive"] += 1
                items.append(
                    {
                        "kind": "archive",
                        "id": field.get("dimension_id"),
                        "dimension_id": field.get("dimension_id"),
                        "value_text": value,
                        "quote": _quoted(value),
                        "source": "archive",
                    }
                )

        return {
            "interview_id": interview_id,
            "keyword": cleaned,
            "total": len(items),
            "counts": counts,
            "items": items,
        }

    # ------------------------------------------------------------- refresh refs

    def refresh_refs(
        self, interview_id: str, refs: Iterable[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        original = [dict(ref) for ref in refs or []]
        if not original or not interview_id:
            return original

        evidence_ids = [
            str(ref.get("id"))
            for ref in original
            if ref.get("kind") == "evidence" and ref.get("id")
        ]
        tag_ids = [
            str(ref.get("id"))
            for ref in original
            if ref.get("kind") == "tag_evidence" and ref.get("id")
        ]
        latest: dict[tuple[str, str], dict[str, Any]] = {}

        conn = self._connect()
        try:
            with conn.cursor() as cur:
                if evidence_ids:
                    cur.execute(
                        """
                        SELECT 'evidence', evidence_id, question_id, speaker_label, quote_text
                        FROM user_insight.evidence
                        WHERE interview_id = %s AND evidence_id = ANY(%s)
                        """,
                        (interview_id, evidence_ids),
                    )
                    for row in cur.fetchall():
                        latest[(row[0], row[1])] = {
                            "question_id": row[2],
                            "speaker": row[3],
                            "quote": _quoted(row[4]),
                        }
                if tag_ids:
                    cur.execute(
                        """
                        SELECT 'tag_evidence', te.tag_evidence_id, te.question_id,
                               te.speaker_label, te.quote_text
                        FROM user_insight.tag_evidence te
                        JOIN user_insight.tag t ON t.tag_id = te.tag_id
                        WHERE t.interview_id = %s AND te.tag_evidence_id = ANY(%s)
                        """,
                        (interview_id, tag_ids),
                    )
                    for row in cur.fetchall():
                        latest[(row[0], row[1])] = {
                            "question_id": row[2],
                            "speaker": row[3],
                            "quote": _quoted(row[4]),
                        }
        finally:
            conn.close()

        refreshed: list[dict[str, Any]] = []
        for ref in original:
            found = latest.get((str(ref.get("kind")), str(ref.get("id"))))
            if found is None:
                ref["source_missing"] = True
            else:
                ref.update(found)
                ref["source_missing"] = False
            refreshed.append(ref)
        return refreshed

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _validate_keyword(keyword: str) -> str:
        if not isinstance(keyword, str):
            raise QuoteError("invalid_keyword", "关键词必须是字符串")
        cleaned = keyword.strip()
        if not 1 <= len(cleaned) <= MAX_KEYWORD_LENGTH:
            raise QuoteError(
                "invalid_keyword", f"关键词长度必须在 1–{MAX_KEYWORD_LENGTH} 之间"
            )
        return cleaned
