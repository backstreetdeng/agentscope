"""D6 探针：验证 `/api/bci/archive/*` 已挂到真实 Web 服务、静态资源可访问、
首页已启用 tab ②，并用 loader 账号走真实库只读请求。

不启动 7860，使用临时端口；不做写库（generate 只验证参数校验分支）。
"""

from __future__ import annotations

import json
import sys
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

import app as web  # noqa: E402

RESULTS: list[tuple[bool, str]] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    RESULTS.append((ok, label))
    print(("PASS" if ok else "FAIL") + " | " + label + (" | " + detail if detail else ""))


def request(method: str, path: str, body: dict | None = None):
    conn = HTTPConnection("127.0.0.1", PORT, timeout=180)
    headers: dict[str, str] = {}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
        headers["Content-Length"] = str(len(data))
    conn.request(method, path, body=data, headers=headers)
    resp = conn.getresponse()
    raw = resp.read()
    content_type = resp.getheader("Content-Type", "")
    status = resp.status
    conn.close()
    return status, content_type, raw


server = ThreadingHTTPServer(("127.0.0.1", 0), web.AgentDemoHandler)
PORT = server.server_address[1]
threading.Thread(target=server.serve_forever, daemon=True).start()
print(f"临时服务端口 {PORT}（未占用 7860）")

# 1. 模板
status, _, raw = request("GET", "/api/bci/archive/template")
payload = json.loads(raw)
template = payload.get("data") or {}
check(status == 200 and payload.get("ok") is True, "GET /template 200/ok", f"status={status}")
check(int(template.get("dimension_count") or 0) == 43, "模板 43 维", str(template.get("dimension_count")))
check(len(template.get("groups") or []) == 12, "模板 12 组", str(len(template.get("groups") or [])))

# 2. 受访者（真实库只读）
status, _, raw = request("GET", "/api/bci/archive/respondents?limit=3")
payload = json.loads(raw)
data = payload.get("data") or {}
items = data.get("items") or []
check(status == 200 and payload.get("ok") is True, "GET /respondents 200/ok", f"status={status}")
check(int(data.get("total") or 0) == 63, "真实库受访者 63 人", str(data.get("total")))
check(len(items) == 3, "分页 3 条", str(len(items)))
interview_id = str(items[0]["interview_id"]) if items else ""
check(bool(interview_id), "取到 interview_id", interview_id)

# 3. 详情空态
if interview_id:
    status, _, raw = request(
        "GET", "/api/bci/archive/detail?interview_id=" + quote(interview_id)
    )
    payload = json.loads(raw)
    detail = payload.get("data") or {}
    check(status == 200 and payload.get("ok") is True, "GET /detail 200/ok", f"status={status}")
    check(not detail.get("archive"), "详情人未生成时 archive 为空", str(detail.get("archive")))

    # 4. 找原话
    status, _, raw = request(
        "GET",
        "/api/bci/archive/quote?interview_id=" + quote(interview_id) + "&keyword=%E7%A9%BA%E9%97%B4&limit=5",
    )
    payload = json.loads(raw)
    quote_data = payload.get("data") or {}
    check(status == 200 and payload.get("ok") is True, "GET /quote 200/ok", f"status={status}")
    groups = quote_data.get("groups") or quote_data
    print("     原话分组键：" + ",".join(sorted(groups.keys())) if isinstance(groups, dict) else "")

# 5. 导出缺档案 → 409
status, _, raw = request(
    "POST",
    "/api/bci/archive/export",
    {"interview_ids": [interview_id or "R001"], "format": "xlsx"},
)
payload = json.loads(raw)
code = (payload.get("error") or {}).get("code")
check(status == 409 and code == "archive_missing", "POST /export 缺档案 409", f"status={status} code={code}")

# 6. 生成参数校验（不写库）
status, _, raw = request(
    "POST",
    "/api/bci/archive/generate",
    {"interview_ids": [interview_id or "R001"], "mode": "bogus"},
)
payload = json.loads(raw)
code = (payload.get("error") or {}).get("code")
check(status == 400 and code == "invalid_mode", "POST /generate 非法 mode 400", f"status={status} code={code}")

# 7. 未知接口
status, _, raw = request("GET", "/api/bci/archive/nope")
check(status == 404, "GET /nope 404", f"status={status}")

# 8. 静态资源
status, ctype, raw = request("GET", "/competitor-insight/bci-profile.css")
check(status == 200 and "text/css" in ctype, "bci-profile.css 可访问", f"status={status} {ctype}")
status, ctype, raw = request("GET", "/competitor-insight/bci-profile.js")
check(status == 200 and "javascript" in ctype, "bci-profile.js 可访问", f"status={status} {ctype}")

# 9. 首页接线
status, _, raw = request("GET", "/")
html = raw.decode("utf-8", "replace")
check(status == 200, "首页 200", f"status={status}")
check("data-bci-profile" in html, "首页含 [data-bci-profile] 挂载点")
check("bci-profile.js" in html and "bci-profile.css" in html, "首页引入档案资源")
check(
    "data-bci-tab='profile' disabled" not in html,
    "tab ② 已启用（无 disabled）",
)

server.shutdown()

failed = [label for ok, label in RESULTS if not ok]
print(f"\n合计 {len(RESULTS)} 项，通过 {len(RESULTS) - len(failed)}，失败 {len(failed)}")
if failed:
    print("失败项：" + "、".join(failed))
sys.exit(1 if failed else 0)
