"""用户洞察自由问答的会话历史（内存版）。

只暴露三个函数：get_history / append_turn / reset。
后续若要持久化到本地文件或数据库，替换这三个函数的实现即可，调用方无需改动。
"""
from __future__ import annotations

import time
from typing import Any

MAX_TURNS = 6
SESSION_TTL_SECONDS = 3600

_SESSIONS: dict[str, dict[str, Any]] = {}


def _now() -> float:
    return time.time()


def _sweep(now: float) -> None:
    expired = [
        session_id
        for session_id, session in _SESSIONS.items()
        if now - float(session.get("updated", 0)) > SESSION_TTL_SECONDS
    ]
    for session_id in expired:
        _SESSIONS.pop(session_id, None)


def get_history(session_id: str) -> list[dict[str, str]]:
    """返回该会话最近若干轮问答，按时间从旧到新。"""
    if not session_id:
        return []
    _sweep(_now())
    session = _SESSIONS.get(session_id)
    return list(session["turns"]) if session else []


def append_turn(session_id: str, question: str, answer: str) -> None:
    """记录一问一答；超过 MAX_TURNS 时丢弃最早的轮次。"""
    if not session_id or not answer:
        return
    now = _now()
    _sweep(now)
    session = _SESSIONS.setdefault(session_id, {"turns": [], "updated": now})
    session["turns"].append({"question": question, "answer": answer})
    session["turns"] = session["turns"][-MAX_TURNS:]
    session["updated"] = now


def reset(session_id: str) -> None:
    """清空指定会话历史。"""
    _SESSIONS.pop(session_id, None)
