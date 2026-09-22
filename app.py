"""AgentScope 2.0.3 多智能体业务协作 Web 服务。

设计依据：
    - doc/乘用车市场战略决策AI智能体.html：系统首页、场景卡片、右侧 Agent 状态面板。
    - doc/市场战略决策智能体开发.html：输入执行区、智能体执行过程、分析结果区。
    - doc/中汽中心AI-UI设计规范.md：深蓝主色、灰白背景、8px 卡片、6px 按钮、4px 输入框。

运行方式：
    python app.py
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse
import urllib.error
import urllib.request

HOST = "127.0.0.1"
PORT = 7860
NEW_CAR_MONITOR_URL = "http://127.0.0.1:8776/api/dashboard"
AGENT_RUN_LOCK = Lock()
LATEST_AGENT_RUN: dict[str, Any] = {}
LATEST_AGENT_RUN_LOCK = Lock()


class AgentEventLoopRunner:
    """为 Web 服务维持单一常驻 asyncio 事件循环。

    AgentScope/OpenAIChatModel 内部使用异步 HTTP 客户端。若每个 HTTP 请求都用
    ``asyncio.run(...)`` 新建并关闭事件循环，客户端的异步关闭任务可能落到已关闭
    的循环，从而产生 ``Event loop is closed``。本类让所有 Agent 调用复用同一条
    常驻循环；它只使用 Python 标准库，不依赖 AgentScope 的未稳定底层 API。
    """

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: Thread | None = None
        self._ready = Event()
        self._lock = Lock()

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive() and self._loop and not self._loop.is_closed():
                return
            self._ready.clear()
            self._thread = Thread(target=self._run_loop, name="agentscope-web-loop", daemon=True)
            self._thread.start()
        if not self._ready.wait(timeout=5):
            raise RuntimeError("Agent 异步事件循环启动超时。")

    def run(self, coroutine: Any) -> Any:
        self.start()
        loop = self._loop
        if loop is None or loop.is_closed():
            raise RuntimeError("Agent 异步事件循环不可用。")
        return asyncio.run_coroutine_threadsafe(coroutine, loop).result()

    def stop(self) -> None:
        loop = self._loop
        thread = self._thread
        if not loop or loop.is_closed():
            return
        loop.call_soon_threadsafe(loop.stop)
        if thread and thread.is_alive():
            thread.join(timeout=5)

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._ready.set()
        try:
            loop.run_forever()
        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()


AGENT_LOOP_RUNNER = AgentEventLoopRunner()

# 候选文件当前放在 backup 目录中；未来也可能被复制到项目根目录并命名为 app.py。
# 这里先确定真实项目根目录，再导入 main/tools/utils，避免把 backup 误当成工程根。
APP_FILE = Path(__file__).resolve()
PROJECT_DIR = APP_FILE.parent.parent if APP_FILE.parent.name.lower() == "backup" else APP_FILE.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from dotenv import load_dotenv
from openai import AuthenticationError
from agentscope.message import UserMsg

from main import (
    ENV_PATH,
    build_market_strategy_agent,
    build_user_insight_agent,
    expand_env,
    load_json_config,
    strip_thinking,
)
from skills.market_analysis_skill import MarketAnalysisSkill
from skills.market_analysis_skill.runtime import (
    SkillEvent,
    normalize_external_evidence_marker_format,
    normalize_top15_summary_wording,
    strip_internal_evidence_markers,
)
from tools.custom_tools import clear_tool_call_events, get_tool_call_events
from utils.audio_tagging_engine import DEFAULT_TAG_TAXONOMY, run_audio_tagging_workflow
from utils.html_ppt_builder import build_consulting_html_ppt
from utils.monthly_report_pptx import build_monthly_report_pptx
from utils.quality_gate import QUALITY_RULES, evaluate_report_quality


PPT_OUTPUT_DIR = PROJECT_DIR / "outputs" / "ppt"
HTML_REPORT_SKILL_RUNNER = (
    Path.home()
    / ".openclaw"
    / "workspace-report-agent"
    / "skills"
    / "html-report-generator"
    / "executors"
    / "run.py"
)


def build_final_answer_retry_config(config: dict[str, Any]) -> dict[str, Any]:
    """构造 MiniMax-M3 未产出正文时的最终交付重试配置。

    首轮继续保留 MiniMax-M3 的自适应思考能力。仅当首轮没有产生任何可展示正文时，
    才使用 MiniMax OpenAI 兼容接口公开支持的 ``thinking={"type": "disabled"}``
    重试，避免模型再次停留在推理阶段而没有报告正文。这里仍通过 AgentScope 2.0.3
    稳定的 ``extra_body`` 参数透传厂商字段，不使用任何 dev 接口。
    """

    retry_config = deepcopy(config)
    provider_name = str(retry_config.get("active_provider", ""))
    providers = retry_config.get("providers", {})
    provider = providers.get(provider_name)
    if not isinstance(provider, dict):
        return retry_config

    model_name = str(expand_env(provider.get("model", ""))).strip()
    if model_name != "MiniMax-M3":
        return retry_config

    extra_body = dict(provider.get("extra_body") or {})
    extra_body["reasoning_split"] = True
    extra_body["thinking"] = {"type": "disabled"}
    provider["extra_body"] = extra_body
    return retry_config
REPORT_FILE_TYPES = {
    ".txt": "文字报告",
    ".md": "Markdown报告",
    ".html": "HTML PPT",
    ".pptx": "可编辑 PPTX",
}

HTML = (PROJECT_DIR / 'home.html').read_text(encoding='utf-8')
LEGACY_WORKBENCH_HTML = (PROJECT_DIR / 'legacy_workbench.html').read_text(encoding='utf-8')
NEW_CAR_DETAIL_HTML = (PROJECT_DIR / 'new-car-detail.html').read_text(encoding='utf-8')


class AgentDemoHandler(BaseHTTPRequestHandler):
    """极简 HTTP 服务，避免引入额外 Web 框架。"""

    server_version = "AgentScopeAutoDecisionDemo/0.2"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        request_path = parsed.path

        if request_path == "/":
            self._send_html(HTML)
            return

        if request_path in ('/legacy/workbench.html', '/legacy/workbench'):
            self._send_html(LEGACY_WORKBENCH_HTML)
            return

        if request_path in ('/new-car-detail', '/new-car-detail.html'):
            self._send_html(NEW_CAR_DETAIL_HTML)
            return

        if request_path.startswith("/outputs/") or request_path.startswith("/skills/html-ppt-skill/assets/"):
            self._send_file(request_path)
            return

        if request_path.startswith('/assets/'):
            asset_relative = request_path[len('/assets/'):]
            asset_path = PROJECT_DIR / 'assets' / asset_relative
            if asset_path.is_file():
                self._send_file('/' + str(asset_path.relative_to(PROJECT_DIR)).replace('\\', '/'))
                return
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        if request_path == "/api/config":
            config = load_json_config()
            provider_name = config.get("active_provider", "")
            provider = config.get("providers", {}).get(provider_name, {})
            self._send_json({
                "active_provider": provider_name,
                "model": expand_env(provider.get("model", "")),
                "endpoint": expand_env(provider.get("base_url") or provider.get("host") or ""),
                "agents": config.get("agents", {}),
            })
            return

        if request_path == "/api/reports":
            params = parse_qs(parsed.query)
            query = params.get("q", [""])[0]
            self._send_json(list_generated_reports(query))
            return

        if request_path == "/api/audio-tags/config":
            self._send_json({"taxonomy": DEFAULT_TAG_TAXONOMY})
            return

        if request_path == "/api/quality-gate/rules":
            self._send_json({"rules": QUALITY_RULES})
            return

        if request_path == "/api/market-skill/status":
            self._send_json(MarketAnalysisSkill(load_json_config()).status())
            return

        if request_path == "/api/new-car/dashboard":
            try:
                request = urllib.request.Request(
                    NEW_CAR_MONITOR_URL,
                    headers={"Accept": "application/json", "User-Agent": "strategy-cockpit/1.0"},
                )
                with urllib.request.urlopen(request, timeout=3) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                self._send_json(payload)
            except (OSError, ValueError, urllib.error.URLError) as exc:
                self._send_json({"error": "新车监测台暂不可用", "detail": str(exc)}, HTTPStatus.BAD_GATEWAY)
            return

        if request_path == "/api/new-car/list":
            self._send_json(load_new_car_rows())
            return

        if request_path == "/api/new-car/planned":
            self._send_json(load_planned_new_car_rows())
            return

        if request_path == "/api/new-car/reputation":
            params = parse_qs(parsed.query)
            model = params.get("model", [""])[0].strip()
            self._send_json(load_new_car_reputation(model))
            return

        if request_path == "/api/agent-run/latest":
            with LATEST_AGENT_RUN_LOCK:
                self._send_json(dict(LATEST_AGENT_RUN))
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if self.path not in {"/api/chat", "/api/ppt", "/api/audio-tags/run", "/api/quality-gate", "/api/market-skill/validate"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8") if length else "{}"
        payload = json.loads(body or "{}")

        try:
            if self.path == "/api/audio-tags/run":
                instruction = str(payload.get("instruction", "")).strip()
                selected_tags = payload.get("selected_tags", [])
                if not isinstance(selected_tags, list):
                    selected_tags = []
                selected_tags = [str(tag) for tag in selected_tags]
                result = run_audio_tagging_workflow(
                    instruction or "执行访谈类音频处理工作流，并生成用户标签洞察。",
                    selected_tags,
                )
                self._send_json(result)
                return

            if self.path == "/api/quality-gate":
                tool_events = payload.get("tool_events", [])
                if not isinstance(tool_events, list):
                    tool_events = []
                self._send_json(evaluate_report_quality(
                    str(payload.get("report", "")),
                    str(payload.get("question", "")),
                    tool_events,
                ))
                return

            if self.path == "/api/market-skill/validate":
                skill = MarketAnalysisSkill(load_json_config())
                context = skill.prepare(
                    str(payload.get("question", "请生成中国乘用车月度市场分析报告。")),
                    "market_monthly_report",
                    payload.get("dataset_path"),
                    payload.get("sheet_name"),
                )
                self._send_json(context.as_response())
                return

            if self.path == "/api/ppt":
                markdown = str(payload.get("markdown", "")).strip()
                title = str(payload.get("title", "乘用车市场战略决策AI智能体PPT")).strip()
                analysis_type = str(payload.get("analysis_type", "")).strip()
                if not markdown:
                    self._send_json({"error": "PPT Markdown 内容不能为空。"}, status=400)
                    return
                result = generate_ppt_from_markdown(
                    markdown,
                    title,
                    analysis_type,
                    payload.get("dataset_path"),
                    payload.get("sheet_name"),
                )
                self._send_json(result)
                return

            question = str(payload.get("question", "")).strip()
            agent_key = str(payload.get("agent", "market_strategy")).strip() or "market_strategy"
            analysis_type = str(payload.get("analysis_type", "")).strip()
            if not question:
                self._send_json({"error": "问题不能为空。"}, status=400)
                return
            # AgentScope 2.0.3 的本地工具审计事件由 tools.custom_tools 暂存；
            # 串行化 chat 请求可避免并发演示时不同请求的工具日志相互串线。
            with AGENT_RUN_LOCK:
                result = AGENT_LOOP_RUNNER.run(
                    run_agent_once(
                        agent_key,
                        question,
                        analysis_type,
                        payload.get("dataset_path"),
                        payload.get("sheet_name"),
                    ),
                )
            store_latest_agent_run(result, question, analysis_type)
            self._send_json(result)
        except AuthenticationError:
            self._send_json({
                "error": "MiniMax/OpenAI 兼容接口鉴权失败：请检查 .env 中的 API Key 是否有效、是否属于 https://api.minimaxi.com/v1 对应的平台。"
            }, status=401)
        except Exception as exc:
            self._send_json({"error": type(exc).__name__ + ": " + str(exc)}, status=500)

    def log_message(self, fmt: str, *args: Any) -> None:
        print("[web] " + self.address_string() + " - " + (fmt % args))

    def _send_html(self, html: str) -> None:
        data = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, request_path: str) -> None:
        """只允许访问 outputs 与 html-ppt-skill 静态资产。"""
        relative = unquote(request_path).lstrip("/").replace("\\", "/")
        output_root = (PROJECT_DIR / "outputs").resolve()
        skill_asset_root = (PROJECT_DIR / "skills" / "html-ppt-skill" / "assets").resolve()
        home_asset_root = (PROJECT_DIR / "assets").resolve()
        file_path = (PROJECT_DIR / relative).resolve()
        allowed = False
        try:
            if output_root in file_path.parents:
                allowed = True
            if skill_asset_root in file_path.parents:
                allowed = True
            if home_asset_root in file_path.parents:
                allowed = True
        except Exception:
            allowed = False

        if not allowed or not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        suffix = file_path.suffix.lower()
        content_type_map = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".svg": "image/svg+xml",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        }
        content_type = content_type_map.get(suffix, "text/plain; charset=utf-8")
        data = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        if suffix == ".pptx":
            safe_download_name = quote(file_path.name)
            self.send_header(
                "Content-Disposition",
                f"attachment; filename=market_monthly_report.pptx; filename*=UTF-8''{safe_download_name}",
            )
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def extract_report_search_text(path: Path) -> str:
    """提取报告正文片段，用于业务侧模糊检索。

    这里不解析完整 PPT 结构，只抽取可读文本，保持 Demo 足够轻量；
    后续可替换为 SQLite 全文索引、向量检索或 MCP 文件库检索。
    """
    if path.suffix.lower() == ".pptx":
        try:
            from pptx import Presentation

            presentation = Presentation(path)
            raw = " ".join(
                shape.text
                for slide in presentation.slides
                for shape in slide.shapes
                if getattr(shape, "has_text_frame", False) and shape.text
            )
        except Exception:
            return ""
        return re.sub(r"\s+", " ", raw).strip()

    raw = path.read_text(encoding="utf-8", errors="ignore")[:160000]
    if path.suffix.lower() == ".html":
        raw = re.sub(r"<script[\s\S]*?</script>", " ", raw, flags=re.IGNORECASE)
        raw = re.sub(r"<style[\s\S]*?</style>", " ", raw, flags=re.IGNORECASE)
        raw = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", raw).strip()


def build_report_snippet(text: str, keyword: str) -> str:
    """根据关键词生成一段命中摘要，便于业务人员快速判断是否打开报告。"""
    if not text:
        return ""
    if not keyword:
        return text[:180]
    lower_text = text.lower()
    lower_keyword = keyword.lower()
    index = lower_text.find(lower_keyword)
    if index < 0:
        return text[:180]
    start = max(0, index - 70)
    end = min(len(text), index + len(keyword) + 130)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return prefix + text[start:end] + suffix


def list_generated_reports(query: str) -> dict[str, Any]:
    """扫描 outputs/ppt 下的历史报告，返回前端报告资产库列表。"""
    keyword = query.strip()
    items: list[dict[str, Any]] = []
    if not PPT_OUTPUT_DIR.exists():
        return {"query": keyword, "items": items}

    for path in PPT_OUTPUT_DIR.rglob("*"):
        suffix = path.suffix.lower()
        if not path.is_file() or suffix not in REPORT_FILE_TYPES:
            continue
        try:
            relative_to_ppt = path.relative_to(PPT_OUTPUT_DIR)
            if "template" in relative_to_ppt.parts:
                continue
            search_text = extract_report_search_text(path)
            haystack = "\n".join([path.name, str(relative_to_ppt), search_text]).lower()
            if keyword and keyword.lower() not in haystack:
                continue
            stat = path.stat()
            relative_to_project = path.relative_to(PROJECT_DIR)
            item = {
                "name": path.name,
                "type": REPORT_FILE_TYPES.get(suffix, suffix),
                "ext": suffix,
                "relative_path": relative_to_project.as_posix(),
                "url": "/" + relative_to_project.as_posix(),
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "mtime": stat.st_mtime,
                "snippet": build_report_snippet(search_text, keyword),
            }
            items.append(item)
        except OSError:
            continue

    items.sort(key=lambda item: item["mtime"], reverse=True)
    for item in items:
        item.pop("mtime", None)
    return {"query": keyword, "items": items[:80]}


def safe_filename(text: str) -> str:
    """生成适合 Windows 文件系统的短文件名。"""
    cleaned = re.sub(r'[\\/:*?"<>|\s]+', "_", text).strip("_")[:60]
    return cleaned or "agent_report_ppt"


def store_latest_agent_run(result: dict[str, Any], question: str, analysis_type: str) -> None:
    """保存最近一次运行的非敏感审计摘要，便于前端和联调排障。

    不记录 API Key、完整系统提示词或模型内部思考过程；报告仅保留短前览，完整正文仍
    由本轮 /api/chat 响应返回给调用方。
    """

    answer = str(result.get("answer", ""))
    audit = {
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "agent": result.get("agent", ""),
        "analysis_type": analysis_type or "自动识别",
        "question": question[:500],
        "answer_length": len(answer),
        "answer_preview": answer[:1200],
        "tool_events": result.get("tool_events", []),
        "skill": result.get("skill"),
    }
    with LATEST_AGENT_RUN_LOCK:
        LATEST_AGENT_RUN.clear()
        LATEST_AGENT_RUN.update(audit)


def generate_ppt_from_markdown(
    markdown: str,
    title: str,
    analysis_type: str = "",
    dataset_path: str | Path | None = None,
    sheet_name: str | None = None,
) -> dict[str, Any]:
    """生成独立 HTML PPT。

    优先使用项目内 consulting-html-ppt-generator 生成咨询风 deck；如果本地生成器异常，
    再回退到原 html-report-generator，保证前端按钮可用。
    """
    PPT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = safe_filename(title) + "_" + stamp
    markdown_path = PPT_OUTPUT_DIR / (base_name + ".md")
    markdown_path.write_text(markdown, encoding="utf-8")

    if analysis_type == "market_monthly_report":
        skill_context = MarketAnalysisSkill(load_json_config()).prepare(
            "生成乘用车市场月度报告",
            analysis_type,
            dataset_path,
            sheet_name,
        )
        if skill_context.dataset_path is None:
            raise RuntimeError("月报 Skill 未找到可用验数数据集，无法生成可编辑 PPTX。")
        pptx_path = PPT_OUTPUT_DIR / (base_name + ".pptx")
        result = build_monthly_report_pptx(
            markdown,
            pptx_path,
            skill_context.dataset_path,
            sheet_name=skill_context.selected_sheet or sheet_name,
        )
        result["markdown_path"] = str(markdown_path.relative_to(PROJECT_DIR)).replace("\\", "/")
        result["pptx_url"] = "/" + str(pptx_path.relative_to(PROJECT_DIR)).replace("\\", "/")
        result["input_gate"] = skill_context.input_gate()
        return result

    html_path = PPT_OUTPUT_DIR / (base_name + ".html")

    try:
        result = build_consulting_html_ppt(markdown, title, html_path, PROJECT_DIR)
        result["markdown_path"] = str(markdown_path.relative_to(PROJECT_DIR)).replace("\\", "/")
        result["html_url"] = "/" + str(html_path.relative_to(PROJECT_DIR)).replace("\\", "/")
        return result
    except Exception as exc:
        if not HTML_REPORT_SKILL_RUNNER.is_file():
            raise RuntimeError("咨询风 HTML PPT 生成失败，且未找到兜底执行器：" + str(exc)) from exc

    completed = subprocess.run(
        [sys.executable, str(HTML_REPORT_SKILL_RUNNER), str(markdown_path), str(html_path)],
        cwd=str(HTML_REPORT_SKILL_RUNNER.parent),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    raw = (completed.stdout or "").strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError("html-report-generator 返回非 JSON 内容：" + raw[:500] + "；stderr=" + (completed.stderr or ""))

    if completed.returncode != 0 or not result.get("success"):
        raise RuntimeError(result.get("error") or "HTML PPT 生成失败")

    html = html_path.read_text(encoding="utf-8", errors="ignore")
    html = html.replace('class="slide active"', 'class="slide"', 1)
    html_path.write_text(html, encoding="utf-8")
    result["markdown_path"] = str(markdown_path.relative_to(PROJECT_DIR)).replace("\\", "/")
    result["html_url"] = "/" + str(html_path.relative_to(PROJECT_DIR)).replace("\\", "/")
    result["file_size"] = html_path.stat().st_size
    result["engine"] = "html-report-generator-fallback"
    return result


def load_new_car_rows() -> dict[str, Any]:
    """新车款型真实数据（3.146 vectordb.new_car_model），失败时返回空列表由前端兜底。"""
    try:
        import psycopg2
        load_dotenv(ENV_PATH, override=False)
        load_dotenv(PROJECT_DIR / ".env.new-car", override=False)
        conn = psycopg2.connect(
            host=os.getenv("NEW_CAR_PG_HOST", "192.168.3.146"),
            port=int(os.getenv("NEW_CAR_PG_PORT", "5432")),
            dbname=os.getenv("NEW_CAR_PG_DATABASE", "vectordb"),
            user=os.getenv("NEW_CAR_PG_USER", "vectordb"),
            password=os.getenv("NEW_CAR_PG_PASSWORD", ""),
            connect_timeout=4,
        )
        with conn, conn.cursor() as cur:
            cur.execute(
                "SELECT model_style_id, launch_year, launch_month, launch_date, region, brand, model,"
                " attr, vehicle_type, vehicle_level, series, enterprise, energy_type,"
                " import_batch"
                " FROM new_car_model ORDER BY launch_date DESC NULLS LAST, model_style_id"
            )
            rows = [
                {
                    "id": r[0], "year": r[1], "month": r[2],
                    "launch_date": r[3].isoformat() if r[3] else None,
                    "region": r[4], "brand": r[5], "model": r[6], "attr": r[7],
                    "cat": r[8], "level": r[9], "series": r[10], "corp": r[11],
                    "energy": r[12], "batch": r[13],
                }
                for r in cur.fetchall()
            ]
        batches = sorted({str(row["batch"]) for row in rows if row.get("batch")}, reverse=True)
        return {
            "source": "postgresql",
            "total": len(rows),
            "batch": batches[0] if batches else "",
            "rows": rows,
        }
    except Exception as exc:  # noqa: BLE001 — 数据库不可用时前端回退 demo 数据
        return {"source": "unavailable", "error": str(exc), "rows": []}


def load_planned_new_car_rows() -> dict[str, Any]:
    """读取规划新车数据，失败时返回空列表供前端显示明确的空状态。"""
    try:
        import psycopg2
        load_dotenv(ENV_PATH, override=False)
        load_dotenv(PROJECT_DIR / ".env.new-car", override=False)
        connection = psycopg2.connect(
            host=os.getenv("NEW_CAR_PG_HOST", "192.168.3.146"),
            port=int(os.getenv("NEW_CAR_PG_PORT", "5432")),
            dbname=os.getenv("NEW_CAR_PG_DATABASE", "vectordb"),
            user=os.getenv("NEW_CAR_PG_USER", "vectordb"),
            password=os.getenv("NEW_CAR_PG_PASSWORD", ""),
            connect_timeout=4,
        )
        with connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT source_batch, source_row, origin_series, enterprise, brand, model_code,"
                " attr, vehicle_level, vehicle_type, energy_type, msrp, price_band, market_status,"
                " launch_year, launch_month, launch_quarter, selling_points, competitor, notes"
                " FROM planned_new_car ORDER BY source_batch DESC, source_row"
            )
            rows = [
                {
                    "batch": row[0], "source_row": row[1], "series": row[2],
                    "enterprise": row[3], "brand": row[4], "model": row[5],
                    "attr": row[6], "level": row[7], "cat": row[8], "energy": row[9],
                    "msrp": row[10], "price_band": row[11], "status": row[12],
                    "year": row[13], "month": row[14], "quarter": row[15],
                    "selling_points": row[16], "competitor": row[17], "notes": row[18],
                }
                for row in cursor.fetchall()
            ]
        batches = sorted({row["batch"] for row in rows if row["batch"]}, reverse=True)
        return {
            "source": "postgresql",
            "total": len(rows),
            "batch": batches[0] if batches else "",
            "rows": rows,
        }
    except Exception as exc:  # noqa: BLE001 — 规划数据不可用时前端展示空状态
        return {"source": "unavailable", "error": str(exc), "rows": []}


def load_new_car_reputation(model: str) -> dict[str, Any]:
    """读取车型级正负口碑 TOP3；数据由两份业务口碑明细离线聚合生成。"""
    if not model:
        return {"source": "unavailable", "error": "缺少车型名称", "model": model, "groups": {}}
    try:
        import psycopg2
        load_dotenv(ENV_PATH, override=False)
        load_dotenv(PROJECT_DIR / ".env.new-car", override=False)
        connection = psycopg2.connect(
            host=os.getenv("NEW_CAR_PG_HOST", "192.168.3.146"),
            port=int(os.getenv("NEW_CAR_PG_PORT", "5432")),
            dbname=os.getenv("NEW_CAR_PG_DATABASE", "vectordb"),
            user=os.getenv("NEW_CAR_PG_USER", "vectordb"),
            password=os.getenv("NEW_CAR_PG_PASSWORD", ""),
            connect_timeout=4,
        )
        with connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT direction, rank, primary_label, secondary_labels, mention_count, mention_share,"
                " dongchedi_count, autohome_count, source_mentions, import_batch"
                " FROM new_car_reputation_summary WHERE model=%s ORDER BY direction, rank",
                (model,),
            )
            records = cursor.fetchall()
        groups: dict[str, list[dict[str, Any]]] = {"positive": [], "negative": []}
        for row in records:
            groups[row[0]].append({
                "rank": row[1], "label": row[2], "secondary": row[3],
                "mentions": row[4], "share": float(row[5]), "source_mentions": row[8],
            })
        if not records:
            return {"source": "postgresql", "model": model, "available": False, "groups": groups}
        return {
            "source": "postgresql", "model": model, "available": True,
            "total_reviews": records[0][6] + records[0][7],
            "sources": {"dongchedi": records[0][6], "autohome": records[0][7]},
            "batch": records[0][9], "groups": groups,
            "method": "一级标签声量占比；懂车帝评分维度 + 汽车之家满意/不满意文本",
        }
    except Exception as exc:  # noqa: BLE001 — 口碑不可用时前端展示空状态
        return {"source": "unavailable", "error": str(exc), "model": model, "groups": {}}


def monthly_report_check_score(checks: list[Any]) -> tuple[int, int, int]:
    """比较首稿与重写稿，避免不完整的重写结果覆盖更好的首稿。"""

    weight = {"通过": 3, "待补充": 1, "风险": -3, "阻断": -6}
    return (
        sum(weight.get(getattr(item, "status", ""), -2) for item in checks),
        sum(getattr(item, "status", "") == "通过" for item in checks),
        -sum(getattr(item, "status", "") in {"风险", "阻断"} for item in checks),
    )


async def run_agent_once(
    agent_key: str,
    question: str,
    analysis_type: str = "",
    dataset_path: str | Path | None = None,
    sheet_name: str | None = None,
) -> dict[str, Any]:
    """按前端选择调用对应业务智能体。"""
    load_dotenv(ENV_PATH, override=True)
    clear_tool_call_events()
    config = load_json_config()
    market_skill_context = None
    if agent_key == "user_insight_config":
        agent = build_user_insight_agent(config)
    else:
        agent_key = "market_strategy"
        market_skill = MarketAnalysisSkill(config)
        # 只有真实月报执行才采集外部证据；前端预检和 PPT 导出只读取已生成文本，
        # 避免同一任务因两次 prepare 重复发起 Agent Reach 搜索。
        market_skill_context = market_skill.prepare(
            question,
            analysis_type,
            dataset_path,
            sheet_name,
            include_external_evidence=True,
        )
        monthly_report_max_tokens = (
            int(config["agents"]["market_strategy"].get("monthly_report_max_tokens", 0))
            if market_skill_context.active and config["agents"]["market_strategy"].get("monthly_report_max_tokens")
            else None
        )
        agent = build_market_strategy_agent(
            config,
            skill_instruction=market_skill_context.prompt_context,
            monthly_report=market_skill_context.active,
            max_tokens_override=monthly_report_max_tokens,
        )

    reply = await agent.reply(UserMsg(name="业务用户", content=question))
    answer = strip_thinking(reply.get_text_content())
    if not answer:
        # MiniMax-M3 偶发只完成推理阶段而未进入正文。使用全新会话执行一次
        # “最终交付模式”重试，避免把不可展示的推理片段直接抛给业务侧。
        retry_config = build_final_answer_retry_config(config)
        if market_skill_context and market_skill_context.active:
            market_skill_context.events.append(
                SkillEvent("model-retry", "running", "首轮未返回可展示正文，正在使用最终交付模式重试一次。"),
            )
            retry_agent = build_market_strategy_agent(
                retry_config,
                skill_instruction=market_skill_context.prompt_context,
                monthly_report=True,
                max_tokens_override=monthly_report_max_tokens,
            )
        elif agent_key == "market_strategy":
            retry_agent = build_market_strategy_agent(retry_config)
        else:
            retry_agent = build_user_insight_agent(retry_config)
        retry_reply = await retry_agent.reply(UserMsg(name="业务用户", content=question))
        answer = strip_thinking(retry_reply.get_text_content())
        if answer and market_skill_context and market_skill_context.active:
            market_skill_context.events.append(
                SkillEvent("model-retry", "success", "已获得可展示正文，继续执行月报输出门禁。"),
            )

    tool_events = get_tool_call_events()
    if not answer:
        raise RuntimeError(
            "MiniMax-M3 连续两次未返回可展示的最终正文，系统已拦截推理文本；"
            "请稍后重试。若持续发生，请检查 MiniMax 服务状态与任务规模。"
        )

    if market_skill_context and market_skill_context.active:
        answer, wording_events = normalize_top15_summary_wording(answer, market_skill_context)
        for detail in wording_events:
            market_skill_context.events.append(SkillEvent("report-normalize", "success", detail))
        answer, marker_events = normalize_external_evidence_marker_format(answer, market_skill_context)
        for detail in marker_events:
            market_skill_context.events.append(SkillEvent("report-normalize", "success", detail))
        output_checks = market_skill.validate_report(answer, market_skill_context)
        first_answer = answer
        first_checks = list(output_checks)
        first_score = monthly_report_check_score(first_checks)
        failed_checks = [item for item in output_checks if item.status != "通过"]
        if failed_checks:
            # 首轮输出没有通过质量门禁时，执行一次同上下文的完整重写。这里不是
            # 续写残稿，而是要求模型从标题开始交付可直接入库的完整月报。
            market_skill_context.events.append(
                SkillEvent("report-repair", "running", "首轮月报未通过输出门禁，正在执行一次完整重写。"),
            )
            failed_evidence = "；".join(f"{item.name}：{item.evidence}" for item in failed_checks)
            # 新建一个 Agent 执行重写，避免首轮长报告已写入的会话历史挤占修订轮的
            # 输出空间，或让模型错误地把“重写”理解为继续追加残稿。
            repair_agent = build_market_strategy_agent(
                config,
                skill_instruction=market_skill_context.prompt_context,
                monthly_report=True,
                max_tokens_override=monthly_report_max_tokens,
            )
            repair_reply = await repair_agent.reply(
                UserMsg(
                    name="月报质量门禁",
                    content=(
                        "上一版月报未通过输出质量门禁（"
                        + failed_evidence
                        + "）。请基于已注入的数据摘要，重新从总标题开始输出一份完整、"
                        "独立的 Markdown 月报。必须覆盖 Skill 规定的全部固定标题，"
                        "只输出报告正文，不要解释修订过程，也不要续写或引用上一版残稿。"
                    ),
                ),
            )
            repaired_answer = strip_thinking(repair_reply.get_text_content())
            if repaired_answer:
                repaired_answer, repaired_wording_events = normalize_top15_summary_wording(
                    repaired_answer,
                    market_skill_context,
                )
                repaired_answer, repaired_marker_events = normalize_external_evidence_marker_format(
                    repaired_answer,
                    market_skill_context,
                )
                repaired_checks = market_skill.validate_report(repaired_answer, market_skill_context)
                if monthly_report_check_score(repaired_checks) > first_score:
                    answer = repaired_answer
                    for detail in repaired_wording_events:
                        market_skill_context.events.append(SkillEvent("report-normalize", "success", detail))
                    for detail in repaired_marker_events:
                        market_skill_context.events.append(SkillEvent("report-normalize", "success", detail))
                    market_skill_context.events.append(
                        SkillEvent("report-repair", "success", "已采用质量门禁结果更优的完整重写版本。"),
                    )
                else:
                    answer = first_answer
                    market_skill_context.output_checks = first_checks
                    market_skill_context.events.append(
                        SkillEvent("report-repair", "warning", "重写版本未优于首轮，已保留章节更完整的首轮版本。"),
                    )
            else:
                market_skill_context.events.append(
                    SkillEvent("report-repair", "warning", "完整重写未返回可展示正文，保留首轮结果并标记输出门禁。"),
                )

        # 输出门禁、证据编号格式化和必要的重写均针对“审计草稿”完成。业务交付
        # 不暴露〔E/R〕编号，避免在无法查看服务端来源链的 PPT 中产生误解。
        answer, delivery_events = strip_internal_evidence_markers(answer)
        for detail in delivery_events:
            market_skill_context.events.append(SkillEvent("report-delivery", "success", detail))

    if "tavily_search" in question and not any(item.get("name") == "tavily_search" for item in tool_events):
        answer += "\n\n---\n【工具审计提示】本轮问题要求使用 tavily_search，但后端未捕获到真实 tavily_search 工具调用。请检查模型是否选择了工具、TAVILY_API_KEY 是否配置，以及 AgentScope ReAct 是否进入工具调用流程。"
    if "any_search" in question and not any(item.get("name") == "any_search" for item in tool_events):
        answer += "\n\n---\n【工具审计提示】本轮问题要求使用 any_search，但后端未捕获到真实 any_search 工具调用。请检查模型是否选择了工具、ANYSEARCH_API_KEY 是否配置，以及 AgentScope ReAct 是否进入工具调用流程。"

    return {
        "answer": answer,
        "agent": agent_key,
        "tool_events": tool_events,
        "skill": market_skill_context.as_response() if market_skill_context and market_skill_context.active else None,
    }


def main() -> None:
    """启动本地 Web 服务。"""
    load_dotenv(ENV_PATH, override=True)
    AGENT_LOOP_RUNNER.start()
    httpd = ThreadingHTTPServer((HOST, PORT), AgentDemoHandler)
    print("AgentScope 多智能体 Web 服务已启动: http://" + HOST + ":" + str(PORT))
    print("界面已按中汽中心AI-UI设计规范重做，并支持双 Agent 选择。")
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
        AGENT_LOOP_RUNNER.stop()


if __name__ == "__main__":
    main()
