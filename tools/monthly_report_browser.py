"""Read-only Playwright MCP connector for the passenger-car monthly report.

The browser is launched only when the monthly-report preflight runs.  A
dedicated persistent Chrome profile keeps the data-source login separate from
the user's everyday browser.  Raw navigation/evaluation tools are never
registered on the business agent; this module exposes only constrained status
and snapshot operations.
"""

from __future__ import annotations

import asyncio
import getpass
import json
import os
import re
import shutil
import socket
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from agentscope.mcp import MCPClient, StdioMCPConfig
from agentscope.message import TextBlock
from agentscope.permission import PermissionBehavior, PermissionContext, PermissionDecision
from agentscope.tool import ToolBase, ToolChunk
from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright


PROJECT_DIR = Path(__file__).resolve().parents[1]
PLAYWRIGHT_MCP_CLI = PROJECT_DIR / "node_modules" / "@playwright" / "mcp" / "cli.js"
PROFILE_DIR = PROJECT_DIR / "runtime" / "monthly-report-browser-profile"
SESSION_METADATA_FILE = PROJECT_DIR / "runtime" / "monthly-report-browser-session.json"
BROWSER_RUNTIME_FILE = PROJECT_DIR / "runtime" / "monthly-report-browser-runtime.json"
MCP_OUTPUT_DIR = PROJECT_DIR / "runtime" / "monthly-report-browser-output"
MCP_LOCAL_APP_DATA = PROJECT_DIR / "runtime" / "playwright-mcp-localappdata"
SNAPSHOT_DIR = PROJECT_DIR / "outputs" / "monthly-report-data"
MAPPING_FILE = (
    PROJECT_DIR
    / "skills"
    / "market-analysis-skill"
    / "passenger-car-monthly-report"
    / "assets"
    / "乘用车月报-数据源映射指标.xlsx"
)
DEFAULT_SOURCE_URL = "https://dicp.catarc-adc.com:18083/page/d970579d9b333471c8c900e3"
DEFAULT_CDP_PORT = 9231


class MonthlyReportSessionOwnerMismatch(RuntimeError):
    """Raised when a durable browser profile is opened by another OS user."""


class MonthlyReportBrowserReconnectionRequired(RuntimeError):
    """An existing pipe-only Chrome must not be replaced without permission."""


def _dedicated_chrome_processes() -> list[dict[str, Any]]:
    """Inspect only process identity; never read the profile or cookie store."""
    if os.name != "nt":
        raise RuntimeError("月报独立浏览器进程检查当前仅支持 Windows。")
    script = r'''
$ErrorActionPreference = 'Stop'
$targetProfile = [IO.Path]::GetFullPath($env:MONTHLY_BROWSER_PROFILE_CHECK)
$items = @(Get-CimInstance Win32_Process -Filter "name='chrome.exe'" | ForEach-Object {
    $command = $_.CommandLine
    if ($command -and $command -notmatch '--type=') {
        $m = [regex]::Match($command, '(?:"--user-data-dir=([^"]+)"|--user-data-dir="([^"]+)"|--user-data-dir=([^\s"]+))')
        if ($m.Success) {
            $profile = @($m.Groups[1].Value, $m.Groups[2].Value, $m.Groups[3].Value | Where-Object { $_ })[0]
            if ([IO.Path]::GetFullPath($profile) -eq $targetProfile) {
                $owner = Invoke-CimMethod -InputObject $_ -MethodName GetOwner
                $ownerSid = Invoke-CimMethod -InputObject $_ -MethodName GetOwnerSid
                if ($owner.ReturnValue -ne 0 -or $ownerSid.ReturnValue -ne 0) { throw 'Cannot verify dedicated Chrome owner' }
                $debug = [regex]::Match($command, '--remote-debugging-port=(\d+)')
                $debugPort = if ($debug.Success) { [int]$debug.Groups[1].Value } else { 0 }
                $listenerPid = 0
                if ($debugPort -gt 0) {
                    foreach ($line in (netstat -ano -p TCP)) {
                        if ($line -match ("^\s*TCP\s+127\.0\.0\.1:" + $debugPort + "\s+.*LISTENING\s+(\d+)\s*$")) {
                            $listenerPid = [int]$Matches[1]
                        }
                    }
                }
                [pscustomobject]@{pid=[int]$_.ProcessId; owner=$owner.User; owner_sid=$ownerSid.Sid; executable=$_.ExecutablePath; cdp_port=$debugPort; listener_pid=$listenerPid}
            }
        } elseif ($command.IndexOf($targetProfile, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
            throw 'Cannot safely parse dedicated Chrome profile identity'
        }
    }
})
ConvertTo-Json -InputObject @($items) -Compress
'''
    environment = dict(os.environ)
    environment["MONTHLY_BROWSER_PROFILE_CHECK"] = str(PROFILE_DIR.resolve())
    powershell = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    result = subprocess.run(
        [str(powershell), "-NoProfile", "-NonInteractive", "-Command", script],
        env=environment, capture_output=True, text=True, timeout=15,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode:
        raise RuntimeError("无法核验月报 Chrome 进程身份；为保护已登录窗口，本次未启动第二个浏览器。")
    try:
        value = json.loads(result.stdout.strip())
        return value if isinstance(value, list) else [value]
    except (ValueError, TypeError) as exc:
        raise RuntimeError("月报 Chrome 进程检查没有返回可靠结果，已停止启动。") from exc


def _direct_browser_proxy() -> dict[str, str] | None:
    """Resolve the proxy used only by the dedicated report browser.

    An explicit environment value wins.  Otherwise use the local Vortex mixed
    proxy when it is listening; this keeps the agent portable to machines that
    reach the intranet directly while matching the operator's current setup.
    """

    configured = os.getenv("MONTHLY_REPORT_BROWSER_PROXY", "").strip()
    if configured.lower() in {"none", "direct", "off"}:
        return None
    if configured:
        return {"server": configured}
    try:
        with socket.create_connection(("127.0.0.1", 7897), timeout=0.25):
            return {"server": "http://127.0.0.1:7897"}
    except OSError:
        return None


def _port_is_listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return True
    except OSError:
        return False

# These two source cards are present on the dashboard but are not referenced by
# the current PPT mapping workbook.  Keep them in the source-page inventory so
# status messages reflect the real dashboard total (45 cards, not 43).
SUPPLEMENTAL_PAGE_CARD_CODES = ["P1.2-3A", "P1.2-3B"]

# The live source keeps a legacy punctuation convention for nine cards while
# the approved PPT mapping workbook uses the canonical convention on the left.
# Treat these as aliases of the same business card, not as missing data.
SOURCE_CARD_CODE_ALIASES: dict[str, tuple[str, ...]] = {
    "P2-8.1": ("P2.8-1",),
    "P2-8.2": ("P2.8-2",),
    "P2-9.1": ("P2.9-1",),
    "P2-9.2": ("P2.9-2",),
    "P2-10.1": ("P2.10-1",),
    "P2-10.2": ("P2.10-2",),
    "P2-11.1": ("P2.11-1",),
    "P2-11.2": ("P2.11-2",),
    "P2-12.1": ("P2.12-1",),
}

# These cards inherit the selected report period from the dashboard context.
# Their visible tables intentionally do not expose a YYYY-MM field: the region
# cards show year-comparison columns and the inventory/registration cards are
# point-in-time snapshots.  Requiring a literal ``2026-08`` in their DOM text
# creates false negatives even when the dashboard itself is on that period.
DASHBOARD_CONTEXT_PERIOD_CARD_CODES = {
    "P2-8.1",
    "P2-8.2",
    "P1.2-3A",
    "P1.2-3B",
}

# These source grids are month-indexed (01..12) and inherit the report year
# from the dashboard.  They intentionally do not repeat the year in each row.
MONTH_INDEXED_PERIOD_CARD_CODES = {
    "P1.1-2",
    "P1.2-2B",
    "P1.2-2D",
}

# Virtualized monthly grids must be read to the target row before deciding
# that they are late. A first viewport often ends at the previous month.
MONTHLY_PERIOD_GRID_CODES = ('P2-1.1', 'P2-2.1', 'P2-5.1', 'P2-6.1', 'P2-12.1', 'P2-12.2')


def _card_has_current_period(code: str, text: str, report_month: str) -> bool:
    """Check business freshness, not merely whether a card contains numbers."""

    if not report_month:
        return False
    title = text.splitlines()[0] if text.splitlines() else ""
    report_year, report_month_number = report_month.split("-")
    if code in {"P2-8.1", "P2-8.2"}:
        # The dashboard filter supplies the month; these cards expose only the
        # current/prior year comparison in their own grid.
        return bool(re.search(rf"(?m)^{re.escape(report_year)}$", text))
    if code in {"P1.2-3A", "P1.2-3B"}:
        # Current point-in-time snapshots have no period column.  Presence and
        # numeric-table checks are applied separately before this function.
        return True
    if code in MONTH_INDEXED_PERIOD_CARD_CODES:
        # Historical averages and monthly new-car splits intentionally have no year.
        return bool(re.search(rf"(?m)^0?{int(report_month_number)}$", text))
    if "累计" in title:
        return bool(re.search(rf"(?m)^{re.escape(report_year)}$", text))
    if report_month in text:
        return True
    return (
        bool(re.search(rf"(?m)^{re.escape(report_year)}$", text))
        and bool(re.search(rf"(?m)^0?{int(report_month_number)}$", text))
    )

INTERNAL_TOOLS = [
    "browser_navigate",
    "browser_snapshot",
    "browser_find",
    "browser_evaluate",
    "browser_resize",
    "browser_take_screenshot",
    "browser_wait_for",
]


def _now() -> datetime:
    try:
        return datetime.now(ZoneInfo("Asia/Shanghai"))
    except Exception:
        return datetime.now()


def _report_month_from_text(text: str) -> str:
    """Return the latest explicit YYYY-MM period visible in lightweight page text."""

    periods = set(re.findall(r"20\d{2}-(?:0[1-9]|1[0-2])", text))
    for year, month in re.findall(r"(20\d{2})\s*年\s*(1[0-2]|0?[1-9])\s*月", text):
        periods.add(f"{year}-{int(month):02d}")
    return max(periods) if periods else ""


def _chunk_text(chunk: Any) -> str:
    parts: list[str] = []
    for block in getattr(chunk, "content", []) or []:
        text = getattr(block, "text", "")
        if text:
            parts.append(str(text))
    return "\n".join(parts)


def _mapping_card_codes() -> list[str]:
    """Return unique card identifiers used by the fixed mapping workbook."""

    if not MAPPING_FILE.is_file():
        return []
    try:
        from openpyxl import load_workbook

        workbook = load_workbook(MAPPING_FILE, read_only=True, data_only=True)
        sheet = workbook.active
        codes: list[str] = []
        for row in sheet.iter_rows(min_row=2, values_only=True):
            source = str(row[8] or "")
            for code in re.findall(r"P\d+(?:[.-]\d+)*(?:[A-Z])?", source):
                if code not in codes:
                    codes.append(code)
        workbook.close()
        return codes
    except Exception:
        return []


def _page_card_codes() -> list[str]:
    """Return the complete known card inventory for the source page."""

    codes = _mapping_card_codes()
    for code in SUPPLEMENTAL_PAGE_CARD_CODES:
        if code not in codes:
            codes.append(code)
    return codes


class MonthlyReportBrowserConnector:
    """Own one persistent AgentScope 2.0.3 MCP client."""

    def __init__(self) -> None:
        self._client: MCPClient | None = None
        self._direct_playwright: Playwright | None = None
        self._direct_browser: Browser | None = None
        self._direct_context: BrowserContext | None = None
        self._direct_page: Page | None = None
        self._lock = asyncio.Lock()
        self._last_result: dict[str, Any] = {
            "installed": PLAYWRIGHT_MCP_CLI.is_file(),
            "connected": False,
            "page_ready": False,
            "generation_ready": False,
        }

    @property
    def source_url(self) -> str:
        return os.getenv("MONTHLY_REPORT_SOURCE_URL", DEFAULT_SOURCE_URL).strip() or DEFAULT_SOURCE_URL

    @property
    def headless(self) -> bool:
        return os.getenv("MONTHLY_REPORT_BROWSER_HEADLESS", "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @property
    def backend(self) -> str:
        return os.getenv("MONTHLY_REPORT_BROWSER_BACKEND", "direct").strip().lower() or "direct"

    @property
    def cdp_port(self) -> int:
        value = os.getenv("MONTHLY_REPORT_BROWSER_CDP_PORT", str(DEFAULT_CDP_PORT)).strip()
        try:
            port = int(value)
            if not 1024 <= port <= 65535:
                raise RuntimeError("月报浏览器 CDP 端口必须在 1024 到 65535 之间。")
            return port
        except ValueError as exc:
            raise RuntimeError("月报浏览器 CDP 端口配置不是有效整数，已停止连接。") from exc

    @property
    def cdp_endpoint(self) -> str:
        return f"http://127.0.0.1:{self.cdp_port}"

    def status(self) -> dict[str, Any]:
        result = dict(self._last_result)
        session = self._load_session_metadata()
        result.update(
            {
                "installed": PLAYWRIGHT_MCP_CLI.is_file(),
                "package": "@playwright/mcp",
                "transport": "cdp" if self.backend == "direct" else "stdio",
                "browser_profile": "月报专用持久浏览器",
                "headless": self.headless,
                "backend": self.backend,
                "cdp_endpoint": self.cdp_endpoint,
                "auth_session_owner": session.get("windows_user", ""),
                "auth_session_last_verified_at": session.get("verified_at", ""),
                "auth_session_last_verified_url": session.get("verified_url", ""),
            },
        )
        return result

    @staticmethod
    def _current_windows_user() -> str:
        """Return the OS account that can decrypt this Chrome profile."""

        try:
            return getpass.getuser().strip()
        except Exception:
            return ""

    @staticmethod
    def _current_windows_sid() -> str:
        if os.name != "nt":
            return ""
        powershell = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        try:
            result = subprocess.run(
                [str(powershell), "-NoProfile", "-NonInteractive", "-Command",
                 "[Security.Principal.WindowsIdentity]::GetCurrent().User.Value"],
                capture_output=True, text=True, timeout=8,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            return result.stdout.strip() if result.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            return ""

    @staticmethod
    def _load_session_metadata() -> dict[str, Any]:
        """Load non-sensitive session evidence; never read or copy cookies."""

        try:
            payload = json.loads(SESSION_METADATA_FILE.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _assert_session_owner(self) -> None:
        """Prevent an OS-account switch from silently invalidating the profile."""

        session = self._load_session_metadata()
        recorded_user = str(session.get("windows_user", "")).strip()
        current_user = self._current_windows_user()
        if (
            recorded_user
            and current_user
            and recorded_user.casefold() != current_user.casefold()
        ):
            raise MonthlyReportSessionOwnerMismatch(
                "月报专用浏览器登录会话由 Windows 账号 "
                f"{recorded_user} 验证，当前服务账号为 {current_user}；"
                "为避免破坏已登录会话，本次未启动该专用浏览器。"
            )

    def _record_verified_session(self, *, url: str, report_month: str) -> dict[str, Any]:
        """Persist only who/when verified the live BI page, never auth secrets."""

        SESSION_METADATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "windows_user": self._current_windows_user(),
            "profile_path": str(PROFILE_DIR),
            "source_url": self.source_url,
            "verified_url": url,
            "report_month": report_month,
            "verified_at": _now().isoformat(timespec="seconds"),
            "contains_credentials": False,
        }
        temporary = SESSION_METADATA_FILE.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(SESSION_METADATA_FILE)
        return payload

    def _select_source_page(self, pages: list[Page]) -> Page | None:
        """Prefer the requested BI dashboard over an older login tab."""

        source = urlsplit(self.source_url)
        live_pages = [page for page in pages if not page.is_closed()]
        for page in reversed(live_pages):
            current = urlsplit(page.url)
            if current.netloc == source.netloc and current.path == source.path:
                return page
        for page in reversed(live_pages):
            if urlsplit(page.url).netloc == source.netloc:
                return page
        for page in reversed(live_pages):
            current = urlsplit(page.url)
            if current.hostname == source.hostname and current.port == 18082:
                return page
        return live_pages[-1] if live_pages else None

    async def _verify_cdp_profile(self, browser: Browser) -> None:
        """Reject an unrelated Chrome using the same local debugging port."""

        session = await browser.new_browser_cdp_session()
        try:
            payload = await session.send("Browser.getBrowserCommandLine")
            arguments = payload.get("arguments", [])
            profile = next(
                (
                    str(argument).split("=", 1)[1]
                    for argument in arguments
                    if str(argument).startswith("--user-data-dir=")
                ),
                "",
            )
            if not profile or Path(profile).resolve() != PROFILE_DIR.resolve():
                raise RuntimeError("本机调试端口不属于月报专用浏览器，已拒绝附着。")
        finally:
            await session.detach()

    def _launch_detached_chrome(self) -> subprocess.Popen:
        """Launch Chrome independently; all backend drivers only attach to it."""
        if os.name != "nt":
            raise RuntimeError("月报独立浏览器启动当前仅支持 Windows。")
        candidates = [
            Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        ]
        executable = next((path for path in candidates if path.is_file()), None)
        if executable is None:
            raise RuntimeError("未找到 Google Chrome，未启动月报专用浏览器。")
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        arguments = [
            str(executable), f"--user-data-dir={PROFILE_DIR.resolve()}",
            f"--remote-debugging-port={self.cdp_port}",
            "--remote-debugging-address=127.0.0.1", "--enable-automation",
            "--no-first-run", "--no-default-browser-check", "--window-size=1920,1080",
        ]
        proxy = _direct_browser_proxy()
        if proxy:
            arguments.append(f"--proxy-server={proxy['server']}")
        if self.headless:
            arguments.append("--headless=new")
        arguments.append("about:blank")
        process = subprocess.Popen(
            arguments, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, close_fds=True,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        return process

    def _record_browser_runtime(self, identity: dict[str, Any]) -> None:
        BROWSER_RUNTIME_FILE.parent.mkdir(parents=True, exist_ok=True)
        metadata = {
            "mode": "detached_cdp", "pid": int(identity["pid"]),
            "windows_user": self._current_windows_user(),
            "windows_sid": self._current_windows_sid(),
            "profile_path": str(PROFILE_DIR.resolve()), "cdp_port": self.cdp_port,
            "verified_at": _now().isoformat(timespec="seconds"), "contains_credentials": False,
        }
        temporary = BROWSER_RUNTIME_FILE.with_name(
            f"{BROWSER_RUNTIME_FILE.stem}.{os.getpid()}.{time.time_ns()}.tmp"
        )
        temporary.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(BROWSER_RUNTIME_FILE)

    async def _ensure_detached_endpoint(self) -> dict[str, Any]:
        self._assert_session_owner()
        existing = await asyncio.to_thread(_dedicated_chrome_processes)
        if len(existing) > 1:
            raise RuntimeError("发现多个月报专用 Chrome 主进程，未启动或关闭任何窗口，请先核对进程身份。")
        process = existing[0] if existing else None
        current_sid = self._current_windows_sid()
        if not current_sid:
            raise MonthlyReportSessionOwnerMismatch("无法核验当前 Windows 安全身份；为保护登录会话，未连接月报浏览器。")
        if process:
            if str(process.get("owner", "")).casefold() != self._current_windows_user().casefold():
                raise MonthlyReportSessionOwnerMismatch("运行中的月报 Chrome 与当前服务 Windows 账号不同，已拒绝附着。")
            if not process.get("cdp_port"):
                raise MonthlyReportBrowserReconnectionRequired(
                    "已登录的月报专用 Chrome 仍在运行，但使用旧版私有管道，不能重新连接。"
                    "为保护登录会话，本次没有重复启动或关闭窗口；需要经你允许后做一次连接方式迁移，原任务检查点保留。"
                )
            if int(process["cdp_port"]) != self.cdp_port:
                raise RuntimeError("月报专用 Chrome 的调试端口与配置不一致，已停止连接；未关闭现有窗口。")
            if str(process.get("owner_sid", "")) != current_sid:
                raise MonthlyReportSessionOwnerMismatch("运行中的月报 Chrome 与当前服务安全身份不同，已拒绝附着。")
            executable = Path(str(process.get("executable", "")))
            if executable.name.casefold() != "chrome.exe" or not executable.is_file():
                raise RuntimeError("月报浏览器进程不是已安装的 Google Chrome，已拒绝附着。")
        else:
            if _port_is_listening(self.cdp_port):
                raise RuntimeError("月报调试端口被其他进程占用，已拒绝连接和启动。")
            await asyncio.to_thread(self._launch_detached_chrome)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if _port_is_listening(self.cdp_port):
                verified = await asyncio.to_thread(_dedicated_chrome_processes)
                if (
                    len(verified) == 1
                    and int(verified[0].get("cdp_port", 0)) == self.cdp_port
                    and int(verified[0].get("listener_pid", 0)) == int(verified[0]["pid"])
                    and str(verified[0].get("owner", "")).casefold() == self._current_windows_user().casefold()
                    and str(verified[0].get("owner_sid", "")) == current_sid
                    and Path(str(verified[0].get("executable", ""))).name.casefold() == "chrome.exe"
                    and Path(str(verified[0].get("executable", ""))).is_file()
                ):
                    self._record_browser_runtime(verified[0])
                    return verified[0]
                raise RuntimeError("调试端口监听进程与月报 Chrome 的配置目录或账号不一致，已拒绝附着。")
            await asyncio.sleep(0.3)
        raise TimeoutError("月报专用 Chrome 在20秒内未开放本机连接端口；没有关闭现有浏览器。")

    async def _ensure_direct_connected(self) -> Page:
        async with self._lock:
            # A user may close the originally tracked tab while leaving the
            # dedicated browser and another authenticated BI tab open. Reuse
            # that live context instead of trying to launch a second Chrome
            # against the locked persistent profile.
            if self._direct_context is not None:
                page = self._select_source_page(self._direct_context.pages)
                if page is not None:
                    page.set_default_timeout(60_000)
                    page.set_default_navigation_timeout(90_000)
                    self._direct_page = page
                    return page
            if self._direct_page is not None and not self._direct_page.is_closed():
                return self._direct_page
            identity = await self._ensure_detached_endpoint()
            PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            MCP_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            runtime = await async_playwright().start()
            try:
                proxy = _direct_browser_proxy()
                browser: Browser | None = None
                browser = await runtime.chromium.connect_over_cdp(self.cdp_endpoint, timeout=20_000)
                await self._verify_cdp_profile(browser)
                contexts = browser.contexts
                if not contexts:
                    raise RuntimeError("月报专用浏览器调试端口已连接，但没有可用浏览器上下文。")
                context = contexts[0]
            except Exception:
                await runtime.stop()
                raise
            page = self._select_source_page(context.pages)
            if page is None:
                page = await context.new_page()
            page.set_default_timeout(60_000)
            page.set_default_navigation_timeout(90_000)
            self._direct_playwright = runtime
            self._direct_browser = browser
            self._direct_context = context
            self._direct_page = page
            self._last_result.update(
                {
                    "connected": True,
                    "last_error": "",
                    "backend": "direct",
                    "cdp_endpoint": self.cdp_endpoint,
                    "cdp_attached": bool(browser),
                    "browser_pid": identity["pid"],
                    "browser_proxy": proxy["server"] if proxy else "direct",
                },
            )
            return page

    async def ensure_connected(self) -> Any:
        if self.backend == "direct":
            return await self._ensure_direct_connected()
        async with self._lock:
            if self._client is not None and self._client.is_connected:
                return self._client

            node = shutil.which("node")
            if not node:
                raise RuntimeError("未找到 Node.js，无法启动数据源读取连接器。")
            if not PLAYWRIGHT_MCP_CLI.is_file():
                raise RuntimeError("Playwright MCP 尚未安装到当前项目。")

            identity = await self._ensure_detached_endpoint()
            PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            MCP_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            MCP_LOCAL_APP_DATA.mkdir(parents=True, exist_ok=True)
            args = [
                str(PLAYWRIGHT_MCP_CLI),
                "--cdp-endpoint",
                self.cdp_endpoint,
                "--ignore-https-errors",
                "--output-dir",
                str(MCP_OUTPUT_DIR),
                "--idle-timeout",
                "0",
                "--no-webmcp",
            ]
            proxy = _direct_browser_proxy()

            client = MCPClient(
                name="monthly_report_browser",
                is_stateful=True,
                mcp_config=StdioMCPConfig(
                    command=node,
                    args=args,
                    cwd=PROJECT_DIR,
                    # Playwright 1.64 writes its browser-server registry below
                    # LOCALAPPDATA/ms-playwright/b. Redirect that registry into
                    # the project runtime so the subprocess has write access.
                    env={"LOCALAPPDATA": str(MCP_LOCAL_APP_DATA)},
                ),
                enable_tools=INTERNAL_TOOLS,
                # A complete 45-card pass must traverse both the dashboard
                # canvas and card-level virtual scrollers. On the real monthly
                # page this can legitimately exceed two minutes; 120 seconds
                # caused a false connection failure after the page had already
                # loaded. Keep the limit bounded but large enough for one full
                # deterministic read.
                execution_timeout=int(os.getenv("MONTHLY_REPORT_MCP_TIMEOUT", "360")),
            )
            await client.connect()
            self._client = client
            self._last_result.update(
                {
                    "connected": True,
                    "last_error": "",
                    "backend": "mcp",
                    "browser_pid": identity["pid"],
                    "cdp_endpoint": self.cdp_endpoint,
                    "browser_proxy": proxy["server"] if proxy else "direct",
                },
            )
            return client

    async def _call(self, name: str, **kwargs: Any) -> Any:
        if self.backend == "direct":
            page = await self._ensure_direct_connected()
            if name == "browser_navigate":
                await page.goto(str(kwargs["url"]), wait_until="domcontentloaded")
                return {"url": page.url, "title": await page.title()}
            if name == "browser_resize":
                await page.set_viewport_size({"width": int(kwargs["width"]), "height": int(kwargs["height"])})
                return {"ok": True}
            if name == "browser_wait_for":
                await asyncio.sleep(float(kwargs.get("time", 1)))
                return {"ok": True}
            if name == "browser_evaluate":
                return await page.evaluate(str(kwargs["function"]))
            if name == "browser_find":
                locator = page.get_by_text(str(kwargs["text"]), exact=False).first
                return await locator.inner_text()
            raise ValueError(f"direct browser does not support tool: {name}")
        client = await self.ensure_connected()
        tool = await client.get_tool(name)
        result = await tool(**kwargs)
        return _chunk_text(result)

    async def _quick_page_status(self) -> dict[str, Any]:
        """Check the current page without building a full accessibility tree.

        A complete accessibility snapshot of this dashboard expands every
        virtualized table and can itself take several minutes. The full-card
        reader only needs a lightweight identity/login check before running its
        fixed DOM extractor.
        """

        raw = await self._call(
            "browser_evaluate",
            function=(
                "() => {"
                "const bodyText = String(document.body && document.body.innerText || '');"
                "const dialogs = Array.from(document.querySelectorAll('[role=dialog], .ant-modal, .ant-modal-wrap, [role=alert]'))"
                ".filter(el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden')"
                ".map(el => String(el.innerText || '')).join('\\n').slice(0, 4000);"
                "return {url: location.href, title: document.title, "
                "dialogText: dialogs, "
                "text: bodyText.slice(0, 12000), "
                "reportMonths: Array.from(new Set(bodyText.match(/20\\d{2}-(?:0[1-9]|1[0-2])/g) || []))};"
                "}"
            ),
        )
        payload = self._parse_evaluate_payload(raw)
        text = str(payload.get("text", ""))
        url = str(payload.get("url", ""))
        title = str(payload.get("title", ""))
        lowered = text.lower()
        lowered_url = url.lower()
        lowered_title = title.lower()
        page_markers = ("P1.1-1", "P2-3.1", "整体市场销量")
        has_page_markers = any(marker in text for marker in page_markers)
        explicit_login_form = any(
            marker in lowered
            for marker in ("用户名", "密码", "sign in", "log in")
        )
        login_url = any(
            marker in lowered_url
            for marker in ("/auth/", "/#/login", "/login", ":18082/")
        )
        login_title = "登录" in title or "login" in lowered_title
        dialog_text = str(payload.get("dialogText", ""))
        session_invalidated = any(marker in dialog_text for marker in (
            "本设备已自动下线", "其他设备登录", "登录已过期", "登录状态已失效", "登录会话已失效",
        ))
        login_required = bool(
            session_invalidated or (not has_page_markers
            and (explicit_login_form or login_url or login_title)
            )
        )
        source_identity = urlsplit(self.source_url)
        page_identity = urlsplit(url)
        page_ready = bool(
            (source_identity.scheme, source_identity.netloc, source_identity.path.rstrip("/"))
            == (page_identity.scheme, page_identity.netloc, page_identity.path.rstrip("/"))
            and has_page_markers
            and not login_required
        )
        reported_periods = [
            str(item)
            for item in payload.get("reportMonths", [])
            if re.fullmatch(r"20\d{2}-(?:0[1-9]|1[0-2])", str(item))
        ]
        report_month = max(reported_periods) if reported_periods else _report_month_from_text(text)
        if login_required:
            report_month = ""
        return {
            "installed": True,
            "connected": True,
            "page_ready": page_ready,
            "generation_ready": False,
            "code": (
                "data_source_page_ready"
                if page_ready
                else "data_source_login_required"
                if login_required
                else "data_source_page_not_ready"
            ),
            "message": (
                "数据源页面已连接。"
                if page_ready
                else "BI登录已失效（网站提示其他设备登录或会话过期）。请在现有月报专用浏览器重新登录并打开仪表板；不会重采卡片或关闭浏览器。"
                if session_invalidated
                else (
                    "月报专用浏览器已打开，但上次登录会话未恢复。"
                    "请在该浏览器完成一次认证；系统不会关闭浏览器，也不会读取短信验证码。"
                )
                if login_required
                else "当前页面尚未加载月报卡片。"
            ),
            "report_month": report_month,
            "current_url": url,
            "page_title": title,
            "auth_session_state": (
                "verified" if page_ready else "login_required" if login_required else "page_not_ready"
            ),
            "page_text": text,
            "session_invalidated": session_invalidated,
        }

    async def read_card(self, card_code: str) -> dict[str, Any]:
        """Read the accessibility-snapshot context for one mapped card code."""

        normalized = card_code.strip().upper()
        expected = _page_card_codes()
        if normalized not in expected:
            raise ValueError(f"卡片编号不在月报映射中：{normalized}")
        result = await self.preflight(open_page=False)
        if not result.get("page_ready"):
            return result
        text = await self._call("browser_find", text=normalized)
        return {
            "card_code": normalized,
            "captured_at": _now().isoformat(timespec="seconds"),
            "content": text[:30000],
            "truncated": len(text) > 30000,
        }

    async def _confirm_page_month(self, status: dict[str, Any], report_month: str = "") -> dict[str, Any]:
        """A report period requires independent sales and inventory evidence."""
        if not status.get("page_ready"):
            return status
        if self.backend != "direct":
            return {**status, "page_ready": False, "generation_ready": False,
                    "report_month": "", "code": "report_month_unconfirmed",
                    "message": "当前连接尚未提供跨主题月份证据，已停止批量采集。"}
        anchors, available, evidence, probe_errors = {}, {}, [], {}
        for code in ("P1.1-1", "P1.2-1"):
            try:
                recovered, trace = await asyncio.wait_for(
                    self._recapture_cards_with_native_scroll([code], "", period_probe=True), timeout=20)
                text = recovered.get(code, "")
                anchors[code] = _report_month_from_text(text)
                available[code] = sorted(set(re.findall(r"20\d{2}-(?:0[1-9]|1[0-2])", text)))
                evidence.extend(trace)
            except Exception as exc:
                anchors[code] = ""
                available[code] = []
                probe_errors[code] = f"{type(exc).__name__}: {exc}"
        months = set(anchors.values())
        confirmed = len(months) == 1 and "" not in months
        live_month = next(iter(months)) if confirmed else ""
        detail = "；".join(f"{code}：{month or '未确认'}" for code, month in anchors.items())
        confirmation = {"status": "confirmed" if confirmed else "conflict" if "" not in months else "unconfirmed",
                        "anchors": anchors, "available_periods": available, "evidence": evidence,
                        "report_month": live_month, "context_period_verified": confirmed, "probe_errors": probe_errors}
        target = report_month or (max(months) if "" not in months else "")
        if target and "" not in months and max(months) == target:
            delayed = {code: month for code, month in anchors.items() if month < target}
            confirmation.update(status="confirmed_with_delays" if delayed else "confirmed",
                                report_month=target, context_period_verified=True,
                                delayed_anchors=delayed)
            return {**status, "report_month": target, "month_confirmation": confirmation,
                    "message": f"报告月份已锁定为 {target}。" +
                    (f"部分卡片更新滞后（{detail}），对应PPT内容保留原样。" if delayed else "")}
        if report_month and all(report_month in available.get(code, []) for code in ("P1.1-1", "P1.2-1")):
            confirmation.update(status="confirmed" if live_month == report_month else "explicit_historical",
                                report_month=report_month, context_period_verified=live_month == report_month)
            return {**status, "report_month": report_month, "month_confirmation": confirmation}
        if not confirmed or (report_month and live_month != report_month):
            code = "report_month_unconfirmed" if "" in months else "report_month_conflict"
            return {**status, "page_ready": False, "generation_ready": False, "report_month": "",
                    "code": code, "month_confirmation": confirmation,
                    "message": f"报告月份未统一（{detail}）。" + (f"指定月份为 {report_month}。" if report_month else "") +
                               "已在批量采集前停止；请明确目标月份，同月完整历史包会直接复用。"}
        return {**status, "report_month": live_month, "month_confirmation": confirmation}

    def _partial_package_cards(self, report_month: str) -> dict[str, str]:
        """Reuse only independently dated cards from incomplete same-month packages.

        A year-only cumulative table cannot prove its cutoff month. Such cards
        are reused only as part of an already validated complete package.
        """
        cards: dict[str, str] = {}
        expected = set(_page_card_codes())
        for path in sorted(SNAPSHOT_DIR.glob("data-source-package-*.json"), reverse=True):
            try:
                package = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(package, dict) or package.get("report_month") != report_month or package.get("source_url") != self.source_url:
                continue
            confirmation = package.get("month_confirmation") or {}
            anchors = confirmation.get("anchors") or {}
            context_verified = bool(confirmation.get('context_period_verified') is True
                                    and confirmation.get('report_month') == report_month
                                    and anchors.get('P1.1-1') == report_month
                                    and anchors.get('P1.2-1') and anchors['P1.2-1'] <= report_month)
            package_diagnostics = self._card_diagnostics(
                {str(card.get('code', '')): str(card.get('text', ''))
                 for card in package.get('cards', []) if isinstance(card, dict)},
                report_month, context_verified=context_verified)
            for card in package.get("cards", []):
                if not isinstance(card, dict):
                    continue
                code, text = str(card.get("code", "")), str(card.get("text", ""))
                if code in expected and code not in cards and (package_diagnostics[code]['status'] == 'delayed_allowed'
                        or (len(text) >= 40 and (report_month in text or context_verified) and _card_has_current_period(code, text, report_month))):
                    cards[code] = text
        return cards

    @staticmethod
    def _card_diagnostics(card_map: dict[str, str], report_month: str, *, context_verified: bool = True, reused_codes: set[str] | None = None) -> dict[str, Any]:
        result = {}
        for code in _page_card_codes():
            text = card_map.get(code, "")
            periods = sorted(set(re.findall(r"20\d{2}-(?:0[1-9]|1[0-2])", text)))
            valid = len(text) >= 40 and bool(re.search(r"\d", text)) and _card_has_current_period(code, text, report_month)
            reason = "valid" if valid else "missing_card" if not text else "incomplete_rows" if len(text) < 40 else "target_month_absent"
            message = "已通过当期校验" if valid else "未读取到卡片" if not text else "卡片表格内容不完整" if len(text) < 40 else f"已读取卡片，但未发现目标月份 {report_month} 的数据；最新显式月份为 {periods[-1] if periods else '未标注'}"
            contextual = code in DASHBOARD_CONTEXT_PERIOD_CARD_CODES or "累计" in (text.splitlines()[0] if text else "")
            latest = _report_month_from_text(text) if text else ""
            if (not valid and len(text) >= 40 and latest and latest < report_month
                    and not contextual and re.search(r"\d", text)):
                reason = "delayed_allowed"
                message = f"卡片更新滞后，实际月份 {latest}；允许继续，对应PPT内容保留原样，不作为目标月事实。"
            if text and contextual and not context_verified and report_month not in text and code not in (reused_codes or set()):
                reason = "ambiguous_period"
                message = "该卡片仅有年度或当前快照，当前页面已跨月份，无法证明目标月截止口径；需目标月已验收卡片或切回目标月份。"
            result[code] = {"status": reason, "reason": reason, "message": message,
                            "latest_period": latest or (periods[-1] if periods else ""), "available_periods": periods}
        return result

    def ready_package_for_month(self, payload: dict[str, Any], report_month: str) -> bool:
        """Validate both cross-run and same-run data checkpoints before reuse."""
        if not report_month or str(payload.get("report_month", "")) != report_month:
            return False
        if str(payload.get("source_url", "")) != self.source_url:
            return False
        expected_codes = _page_card_codes()
        try:
            expected = int(payload.get("cards_expected", 0) or 0)
            usable = int(payload.get("cards_usable", 0) or 0)
        except (ValueError, TypeError):
            return False
        cards = payload.get("cards", [])
        if not isinstance(cards, list):
            return False
        card_map = {str(item.get("code", "")): str(item.get("text", ""))
                    for item in cards if isinstance(item, dict)}
        diagnostics = self._card_diagnostics(card_map, report_month)
        return bool(
            payload.get("generation_ready")
            and expected == len(expected_codes) and usable == expected
            and set(card_map) == set(expected_codes)
            and all(_card_has_current_period(code, card_map[code], report_month)
                    or diagnostics[code]['status'] == 'delayed_allowed'
                    for code in expected_codes)
        )

    def _load_recent_ready_package(self, report_month: str = "") -> dict[str, Any] | None:
        """Reuse the newest validated package for the confirmed report month.

        A monthly package is a durable business checkpoint, not an eight-hour
        browser cache. It remains reusable across runs for the explicit report
        month when source identity and all current mapping cards pass validation;
        live login is required only for capture or an explicit refresh.
        """

        # Refresh is an explicit per-request decision; a deployment setting
        # must not silently turn all future monthly runs into full recaptures.
        if not report_month:
            return None
        # A validated monthly package is keyed by business period and mapping,
        # never by a wall-clock TTL.
        for path in sorted(SNAPSHOT_DIR.glob("data-source-package-*.json"), reverse=True):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                continue
            if not isinstance(payload, dict) or not self.ready_package_for_month(payload, report_month):
                continue
            package_month = str(payload["report_month"])
            payload["snapshot_path"] = str(path)
            payload["snapshot_reused"] = True
            payload["collection_mode"] = "reuse"
            payload["cards_reused"] = len(_page_card_codes())
            payload["cards_collected"] = 0
            payload["cards_to_collect"] = 0
            payload["snapshot_reuse_reason"] = "same_report_month_verified"
            payload["reused_from_snapshot_path"] = str(path)
            payload["reused_at"] = _now().isoformat(timespec="seconds")
            payload["code"] = "data_package_ready_cached"
            payload["message"] = (
                f"已复用 {package_month} 历史任务中通过门禁的45/45标准化月报数据包，"
                "跳过卡片重复读取。"
            )
            return payload
        return None

    def package_preflight(self, cached: dict, report_month: str) -> dict:
        """Validate a durable data checkpoint without requiring a live browser."""
        if not self.ready_package_for_month(cached, report_month):
            raise ValueError("数据包月份、来源或卡片完整性未通过校验")
        return {
            "page_ready": True,  # Legacy workflow flag: inputs ready, not a live login claim.
            "generation_ready": True, "connector_ready": False,
            "connected": False, "browser_required": False,
            "auth_session_state": "not_checked",
            "code": "data_source_package_reused", "report_month": report_month,
            "snapshot_path": cached.get("snapshot_path", ""),
            "data_package_path": cached.get("snapshot_path", ""),
            "snapshot_reused": True, "collection_mode": "reuse",
            "cards_reused": len(_page_card_codes()), "cards_to_collect": 0,
            "cards_collected": 0, "mapping_cards_expected": len(_page_card_codes()),
            "mapping_cards_matched": len(_page_card_codes()), "mapping_coverage_pct": 100.0,
            "month_confirmation": {"status": "explicit_validated_package", "report_month": report_month},
            "reuse_decision": {"reason": "validated_package_without_browser",
                               "message": "同月完整数据包已验收，直接继续研究、主旨句和PPT更新，无需浏览器登录。"},
            "message": f"已校验并复用 {report_month} 的45/45张卡片；无需月报专用浏览器。",
        }

    async def _refresh_cached_delays(self, cached: dict, status: dict) -> dict:
        """Recheck only late/unfinished month grids, not all 45 accepted cards."""
        if self.backend != 'direct' or self._direct_page is None:
            return cached
        month = str(cached.get('report_month', ''))
        if status.get('report_month') != month:
            return cached  # Preserve explicitly requested historical packages.
        cards = {c['code']:dict(c) for c in cached['cards']}
        diagnostics = self._card_diagnostics({k:c['text'] for k,c in cards.items()}, month)
        wanted = [k for k,c in cards.items() if diagnostics[k]['status']=='delayed_allowed'
                  or (k in MONTHLY_PERIOD_GRID_CODES and not c.get('grid_snapshot',{}).get('complete'))]
        if not wanted:
            return cached
        from scripts.capture_monthly_ppt_grids import capture
        page = await self._ensure_direct_connected()
        deadline = time.monotonic()+60
        refreshed, errors = [], []
        for code in wanted:
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                errors.append('滞后卡片复核达到60秒上限，保留已验收历史值并记录未核实项')
                break
            try:
                grid = await asyncio.wait_for(capture(page, code, month), timeout=min(30,remaining))
                flat = '\n'.join(cell['text'] for cell in grid['headers']+grid['cells'] if cell['text'])
                cards[code]['text'] += '\n---视图分段---\n'+code+'：完整月份行复核\n'+flat
                cards[code]['grid_snapshot'] = grid
                refreshed.append(code)
            except Exception as exc:
                errors.append(f'{code}本次月份复核未完成：{type(exc).__name__}')
        result = dict(cached)
        result['freshness_recheck'] = {'cards':refreshed, 'warnings':errors, 'verified_at':_now().isoformat()}
        if refreshed:
            diagnostics = self._card_diagnostics({k:c['text'] for k,c in cards.items()}, month)
            result.update(cards=list(cards.values()), card_validation=diagnostics,
                          delayed_cards=[k for k,d in diagnostics.items() if d['status']=='delayed_allowed'],
                          captured_at=_now().isoformat(), code='data_package_ready_cached_rechecked')
            self._save_data_package(result, '')
        return result

    async def read_all_cards(self, report_month: str = "", *, force_refresh: bool = False) -> dict[str, Any]:
        """Collect all dashboard cards into one traceable standardized package.

        This uses a fixed, read-only DOM extractor owned by the application.
        Raw ``browser_evaluate`` is never exposed to the business agent.
        """

        cached = self._load_recent_ready_package(report_month) if report_month and not force_refresh else None
        if cached is not None:
            self._last_result = dict(cached)
            return cached

        # Reuse the page opened by the validation request when possible.  A
        # fresh application process starts at a blank page, so only then do we
        # navigate to the fixed source URL.  This avoids reloading the large
        # dashboard twice for one user action.
        try:
            status = await self._quick_page_status()
        except Exception:
            status = {"page_ready": False}
        if not status.get("page_ready"):
            status = await self.preflight(open_page=True, report_month=report_month, force_refresh=force_refresh)
        if not status.get("page_ready"):
            return status

        # Explicit historical requests may reuse a validated package even if
        # the live dashboard has since been partly refreshed to a newer month.
        cached = self._load_recent_ready_package(report_month) if report_month and not force_refresh else None
        if cached is not None:
            cached = await self._refresh_cached_delays(cached, status)
            self._last_result = dict(cached)
            return cached
        status = await self._confirm_page_month(status, report_month)
        if not status.get("page_ready") or not status.get("report_month"):
            return status
        report_month = str(status["report_month"])
        cached = self._load_recent_ready_package(report_month) if not force_refresh else None
        if cached is not None:
            cached = await self._refresh_cached_delays(cached, status)
            self._last_result = dict(cached)
            return cached
        expected = _page_card_codes()
        reused_cards = self._partial_package_cards(report_month) if not force_refresh else {}
        pending_codes = [code for code in expected if code not in reused_cards]
        wanted_json = json.dumps(pending_codes, ensure_ascii=False)
        all_codes_json = json.dumps(expected, ensure_ascii=False)
        alias_to_canonical = {
            alias: canonical
            for canonical, aliases in SOURCE_CARD_CODE_ALIASES.items()
            for alias in aliases
        }
        aliases_json = json.dumps(alias_to_canonical, ensure_ascii=False)
        # Raw f-string is required here: JavaScript regular expressions such
        # as /\n/ and /\d/ must reach Playwright unchanged.  A normal Python
        # f-string converted /\n/ into an actual line break and made the whole
        # extractor fail before it could read any card.
        extractor = rf"""async () => {{
  const wanted = new Set({wanted_json});
  const aliases = new Map(Object.entries({aliases_json}));
  const accepted = new Set([...{all_codes_json}, ...aliases.keys()]);
  const canonical = code => aliases.get(code) || code;
  const codeRe = /P\d+(?:[.-]\d+)*(?:[A-Z])?/g;
  const records = new Map();
  const cardRoots = new Map();
  const clean = value => String(value || '').replace(/\u00a0/g, ' ').trim();
  const addRecord = (code, value) => {{
    const text = clean(value);
    if (!text) return;
    const textCodes = [...new Set((text.match(codeRe) || []).filter(item => accepted.has(item)).map(canonical))];
    if (textCodes.length !== 1 || textCodes[0] !== code) return;
    const views = records.get(code) || [];
    if (!views.includes(text) && views.length < 24) views.push(text);
    records.set(code, views);
  }};
  const rootFor = (start, code) => {{
    let node = start;
    let best = start;
    for (let depth = 0; depth < 9 && node.parentElement; depth += 1) {{
      const parent = node.parentElement;
      const text = clean(parent.innerText);
      const codes = [...new Set((text.match(codeRe) || []).filter(item => accepted.has(item)).map(canonical))];
      if (codes.length !== 1 || codes[0] !== code || text.length > 50000) break;
      best = parent;
      node = parent;
    }}
    return best;
  }};
  const collect = () => {{
    for (const el of document.querySelectorAll('div,span,h1,h2,h3,h4,h5,p')) {{
      const ownText = clean(el.innerText);
      if (!ownText || ownText.length > 50000) continue;
      const ownCodes = [...new Set((ownText.match(codeRe) || []).filter(item => accepted.has(item)).map(canonical))];
      if (ownCodes.length !== 1) continue;
      const firstLine = ownText.split(/\n/)[0];
      const match = firstLine.match(/^\s*(P\d+(?:[.-]\d+)*(?:[A-Z])?)\s*[:：]/);
      if (!match || !accepted.has(match[1])) continue;
      const code = canonical(match[1]);
      if (!wanted.has(code)) continue;
      const root = rootFor(el, code);
      cardRoots.set(code, root);
      addRecord(code, root.innerText);
    }}
  }};
  collect();
  const candidates = [document.scrollingElement, ...document.querySelectorAll('*')]
    .filter(Boolean)
    .filter((el, index, array) => array.indexOf(el) === index)
    .filter(el => (
      (el.scrollHeight > el.clientHeight + 300 && el.clientHeight > 180) ||
      (el.scrollWidth > el.clientWidth + 200 && el.clientWidth > 300)
    ))
    .sort((a, b) => (
      (b.scrollHeight - b.clientHeight) + (b.scrollWidth - b.clientWidth) -
      (a.scrollHeight - a.clientHeight) - (a.scrollWidth - a.clientWidth)
    ))
    // Only the largest root is the dashboard canvas. Sampling every nested
    // scroller here repeats the same DOM scan; card scrollers are handled below.
    .slice(0, 1);
  const scrollEvidence = [];
  for (const root of candidates) {{
    const startTop = root.scrollTop;
    const startLeft = root.scrollLeft;
    const yMax = Math.max(0, root.scrollHeight - root.clientHeight);
    const xMax = Math.max(0, root.scrollWidth - root.clientWidth);
    let iterations = 0;
    const ys = [...new Set(Array.from({{length: 13}}, (_, i) => Math.floor(yMax * i / 12)))];
    const xs = [...new Set([0, xMax])];
    for (const x of xs) {{
      root.scrollLeft = x;
      for (const y of ys) {{
        root.scrollTop = y;
        await new Promise(resolve => setTimeout(resolve, 120));
        collect();
        iterations += 1;
      }}
    }}
    root.scrollTop = startTop;
    root.scrollLeft = startLeft;
    scrollEvidence.push({{
      tag: root.tagName,
      className: clean(root.className).slice(0, 160),
      clientHeight: root.clientHeight,
      scrollHeight: root.scrollHeight,
      clientWidth: root.clientWidth,
      scrollWidth: root.scrollWidth,
      iterations
    }});
  }}
  for (const code of wanted) {{
    let card = cardRoots.get(code) || null;
    if (!card || !card.isConnected) {{
      card = null;
      for (const el of document.querySelectorAll('div,span,h1,h2,h3,h4,h5,p')) {{
        const firstLine = clean(el.innerText).split(/\n/)[0];
        const match = firstLine.match(/^\s*(P\d+(?:[.-]\d+)*(?:[A-Z])?)\s*[:：]/);
        if (match && canonical(match[1]) === code) {{
          card = rootFor(el, code);
          cardRoots.set(code, card);
          break;
        }}
      }}
    }}
    if (!card) continue;
    card.scrollIntoView({{block: 'center', inline: 'center'}});
    await new Promise(resolve => setTimeout(resolve, 160));
    addRecord(code, card.innerText);
    const innerScrollers = [...card.querySelectorAll('*')]
      .filter(el => (
        (el.scrollHeight > el.clientHeight + 20 && el.clientHeight > 60) ||
        (el.scrollWidth > el.clientWidth + 20 && el.clientWidth > 120)
      ))
      .sort((a, b) => (
        (b.scrollHeight - b.clientHeight) + (b.scrollWidth - b.clientWidth) -
        (a.scrollHeight - a.clientHeight) - (a.scrollWidth - a.clientWidth)
      ))
      .slice(0, 3);
    for (const scroller of innerScrollers) {{
      const startTop = scroller.scrollTop;
      const startLeft = scroller.scrollLeft;
      const yMax = Math.max(0, scroller.scrollHeight - scroller.clientHeight);
      const xMax = Math.max(0, scroller.scrollWidth - scroller.clientWidth);
      const ys = [...new Set([0, Math.floor(yMax / 2), yMax])];
      const xs = [...new Set([0, xMax])];
      for (const x of xs) {{
        for (const y of ys) {{
          scroller.scrollLeft = x;
          scroller.scrollTop = y;
          await new Promise(resolve => setTimeout(resolve, 80));
          addRecord(code, card.innerText);
        }}
      }}
      scroller.scrollTop = startTop;
      scroller.scrollLeft = startLeft;
    }}
  }}
  for (const code of wanted) {{
    const current = (records.get(code) || []).join('\n---视图分段---\n');
    if (current.length >= 40 && /\d/.test(current)) continue;
    for (const el of document.querySelectorAll('div,span,h1,h2,h3,h4,h5,p')) {{
      const firstLine = clean(el.innerText).split(/\n/)[0];
      const match = firstLine.match(/^\s*(P\d+(?:[.-]\d+)*(?:[A-Z])?)\s*[:：]/);
      if (!match || canonical(match[1]) !== code) continue;
      el.scrollIntoView({{block: 'center', inline: 'center'}});
      await new Promise(resolve => setTimeout(resolve, 300));
      collect();
      break;
    }}
  }}
  collect();
  return {{
    pageTitle: document.title,
    url: location.href,
    cards: [...records.entries()].map(([code, views]) => ({{code, text: views.join('\n---视图分段---\n')}})),
    scrollEvidence
  }};
}}"""
        raw = await self._call("browser_evaluate", function=extractor)
        payload = self._parse_evaluate_payload(raw)
        cards = payload.get("cards", []) if isinstance(payload, dict) else []
        card_map = {
            str(item.get("code", "")): str(item.get("text", ""))
            for item in cards
            if isinstance(item, dict) and str(item.get("code", "")) in pending_codes
        }
        card_map = {**reused_cards, **card_map}
        grid_cards = {}
        if self.backend == 'direct' and self._direct_page is not None:
            # Ranking/province grids need cell boundaries, not merely a title
            # and four visible rows. Capture them before declaring 45/45 ready.
            from scripts.capture_monthly_ppt_grids import capture
            page = await self._ensure_direct_connected()
            cached_grids = {}
            if not force_refresh:
                for path in sorted(SNAPSHOT_DIR.glob('data-source-package-*.json'),reverse=True):
                    try:
                        checkpoint=json.loads(path.read_text(encoding='utf-8'))
                    except (OSError,ValueError):continue
                    if checkpoint.get('report_month')!=report_month or checkpoint.get('source_url')!=self.source_url:continue
                    for card in checkpoint.get('cards',[]):
                        grid=card.get('grid_snapshot',{})
                        if grid.get('complete') and grid.get('month')==report_month and grid.get('cells'):
                            cached_grids.setdefault(card.get('code'),grid)
            for code in (*MONTHLY_PERIOD_GRID_CODES, 'P2-8.1', 'P2-3.3A', 'P2-3.3B', 'P2-4.3A', 'P2-4.3B',
                         'P2-5.3A', 'P2-5.3B', 'P2-14.1', 'P2-14.2',
                         'P2-10.1', 'P2-10.2', 'P2-13.1', 'P2-13.2'):
                grid = cached_grids.get(code)
                if grid is None:
                    grid = await asyncio.wait_for(capture(page, code, report_month), timeout=120)
                flat = '\n'.join(cell['text'] for cell in grid['headers'] + grid['cells'] if cell['text'])
                grid_cards[code] = grid
                card_map[code] = card_map.get(code, '') + '\n---视图分段---\n' + code + '：逐单元格采集\n' + flat
                checkpoint_cards = [{'code': key, 'text': value,
                                     **({'grid_snapshot': grid_cards[key]} if key in grid_cards else {})}
                                    for key, value in card_map.items()]
                self._save_data_package({'report_month':report_month,'source_url':self.source_url,
                    'cards':checkpoint_cards,'cards_expected':len(expected),'cards_usable':0,
                    'generation_ready':False,'month_confirmation':status.get('month_confirmation',{}),
                    'message':f'逐卡片检查点：{code}单元格采集完成。'}, '')
        captured = [code for code in expected if code in card_map]
        content_usable = [
            code
            for code in captured
            if len(card_map[code]) >= 40 and re.search(r"\d", card_map[code])
        ]
        missing = [code for code in expected if code not in captured]

        # The dashboard uses virtualized grids.  A DOM-only pass can see the
        # card and its first rows while never materializing the current-period
        # rows.  On the default direct Playwright backend, finish incomplete
        # cards with trusted wheel events over each card's own scrollable
        # containers.  This keeps the complete 45-card pass deterministic
        # without weakening the freshness gate.
        native_scroll_evidence: list[dict[str, Any]] = []
        if self.backend == "direct" and report_month:
            retry_codes = [
                code
                for code in content_usable
                if code not in DASHBOARD_CONTEXT_PERIOD_CARD_CODES
                and not _card_has_current_period(code, card_map[code], report_month)
            ]
            if retry_codes:
                recovered, native_scroll_evidence = await self._recapture_cards_with_native_scroll(
                    retry_codes,
                    report_month,
                )
                for code, extra_text in recovered.items():
                    if not extra_text:
                        continue
                    existing = card_map.get(code, "")
                    segments = [item for item in (existing, extra_text) if item]
                    card_map[code] = "\n---视图分段---\n".join(dict.fromkeys(segments))

                captured = [code for code in expected if code in card_map]
                content_usable = [
                    code
                    for code in captured
                    if len(card_map[code]) >= 40 and re.search(r"\d", card_map[code])
                ]
                missing = [code for code in expected if code not in captured]
        diagnostics = self._card_diagnostics(
            card_map, report_month,
            context_verified=status.get("month_confirmation", {}).get("context_period_verified", True),
            reused_codes=set(reused_cards))
        usable = [code for code in content_usable if diagnostics[code]["status"] in {"valid", "delayed_allowed"}]
        unusable = [code for code in captured if code not in usable]
        stale = [
            code
            for code in usable
            if diagnostics[code]["status"] != "delayed_allowed" and "未更新" in card_map[code] and (not report_month or report_month not in card_map[code])
        ]
        label_warnings = [
            code
            for code in usable
            if "未更新" in card_map[code] and report_month and report_month in card_map[code]
        ]
        result = {
            "installed": True,
            "connected": True,
            "page_ready": True,
            "generation_ready": bool(len(usable) == len(expected) and not stale),
            "code": "data_package_ready" if len(usable) == len(expected) and not stale else "data_package_incomplete",
            "message": (
                "已生成完整标准化月报数据包。"
                if len(usable) == len(expected) and not stale
                else "标准化月报数据包尚不完整，已停止进入PPT更新阶段。"
            ),
            "report_month": report_month,
            "collection_mode": "force_refresh" if force_refresh else "partial_collect" if reused_cards else "collect",
            "cards_reused": len(reused_cards),
            "cards_collected": sum(code in card_map for code in pending_codes),
            "cards_to_collect": len(pending_codes),
            "card_validation": diagnostics,
            "month_confirmation": status.get("month_confirmation", {}),
            "cards_expected": len(expected),
            "cards_captured": len(captured),
            "cards_usable": len(usable),
            "missing_cards": missing,
            "unusable_cards": unusable,
            "stale_cards": stale,
            "delayed_cards": [code for code in usable if diagnostics[code]["status"] == "delayed_allowed"],
            "label_warnings": label_warnings,
            "cards": [{"code": code, "text": card_map[code],
                       **({'grid_snapshot': grid_cards[code]} if code in grid_cards else {})}
                      for code in expected if code in card_map],
            "scroll_evidence": (
                (payload.get("scrollEvidence", []) if isinstance(payload, dict) else [])
                + native_scroll_evidence
            ),
            "captured_at": _now().isoformat(timespec="seconds"),
        }
        self._save_data_package(result, raw)
        return result

    async def _recapture_cards_with_native_scroll(
        self,
        card_codes: list[str],
        report_month: str,
        *,
        period_probe: bool = False,
    ) -> tuple[dict[str, str], list[dict[str, Any]]]:
        """Materialize virtual-grid rows using Playwright wheel input.

        Direct ``scrollTop`` assignment is insufficient for several grids on
        the source page: their row renderer listens to real wheel/scroll input
        and updates asynchronously.  This routine remains read-only, moves
        only the dedicated report browser, and records per-card coverage
        evidence for audit and troubleshooting.
        """

        page = await self._ensure_direct_connected()
        expected = _page_card_codes()
        alias_to_canonical = {
            alias: canonical
            for canonical, aliases in SOURCE_CARD_CODE_ALIASES.items()
            for alias in aliases
        }
        recovered: dict[str, str] = {}
        evidence: list[dict[str, Any]] = []

        for code in card_codes:
            source_codes = [code, *SOURCE_CARD_CODE_ALIASES.get(code, ())]
            title_pattern = re.compile(
                rf"^\s*(?:{'|'.join(re.escape(item) for item in source_codes)})\s*[:：]",
            )
            title = page.get_by_text(title_pattern, exact=False).first
            if await title.count() == 0:
                evidence.append({
                    "card_code": code,
                    "strategy": "native_wheel",
                    "status": "title_not_found",
                    "segments": 0,
                })
                continue

            try:
                await title.scroll_into_view_if_needed(timeout=15_000)
                await page.wait_for_timeout(250)
                handle = await title.evaluate_handle(
                    """(start, cfg) => {
                      const clean = value => String(value || '').replace(/\u00a0/g, ' ').trim();
                      const aliases = new Map(Object.entries(cfg.aliases));
                      const accepted = new Set([...cfg.expected, ...aliases.keys()]);
                      const canonical = value => aliases.get(value) || value;
                      const codeRe = /P\d+(?:[.-]\d+)*(?:[A-Z])?/g;
                      let node = start;
                      let best = start;
                      for (let depth = 0; depth < 10 && node.parentElement; depth += 1) {
                        const parent = node.parentElement;
                        const text = clean(parent.innerText);
                        const codes = [...new Set((text.match(codeRe) || [])
                          .filter(item => accepted.has(item)).map(canonical))];
                        if (codes.length !== 1 || codes[0] !== cfg.code || text.length > 50000) break;
                        best = parent;
                        node = parent;
                      }
                      return best;
                    }""",
                    {"code": code, "expected": expected, "aliases": alias_to_canonical},
                )
                root = handle.as_element()
                if root is None:
                    raise RuntimeError("card root is not an element")

                marker_prefix = "monthly-scroll-" + re.sub(r"[^A-Za-z0-9]", "-", code)
                scrollables = await root.evaluate(
                    """(root, prefix) => {
                      const nodes = [root, ...root.querySelectorAll('*')]
                        .filter(el => (
                          (el.scrollHeight > el.clientHeight + 8 && el.clientHeight > 38) ||
                          (el.scrollWidth > el.clientWidth + 8 && el.clientWidth > 80)
                        ))
                        .sort((a, b) => (
                          (b.scrollHeight - b.clientHeight) + (b.scrollWidth - b.clientWidth) -
                          (a.scrollHeight - a.clientHeight) - (a.scrollWidth - a.clientWidth)
                        ))
                        .slice(0, 6);
                      return nodes.map((el, index) => {
                        const marker = `${prefix}-${index}`;
                        el.setAttribute('data-monthly-scroll-probe', marker);
                        return {
                          marker,
                          clientHeight: el.clientHeight,
                          scrollHeight: el.scrollHeight,
                          clientWidth: el.clientWidth,
                          scrollWidth: el.scrollWidth,
                          className: String(el.className || '').slice(0, 160)
                        };
                      });
                    }""",
                    marker_prefix,
                )

                views: list[str] = []

                async def record_view() -> None:
                    text = (await root.inner_text()).strip()
                    if text and text not in views:
                        views.append(text)

                await record_view()
                scroll_steps = 0
                for info in scrollables:
                    marker = str(info.get("marker", ""))
                    if not marker:
                        continue
                    locator = page.locator(f'[data-monthly-scroll-probe="{marker}"]').first
                    if await locator.count() == 0:
                        continue
                    if period_probe:
                        # The two anchors are date-ordered monthly series.
                        # Inspect both ends, not all historical windows. Wheel
                        # input triggers virtual rendering; bounded hover must
                        # not consume the entire month-confirmation timeout.
                        for bottom in (False, True):
                            await locator.evaluate(
                                "(el, bottom) => { el.scrollTo({top: bottom ? el.scrollHeight : 0, left: 0, behavior: 'instant'}); el.dispatchEvent(new Event('scroll', {bubbles:true})); }", bottom)
                            await page.wait_for_timeout(250)
                            try:
                                await locator.hover(timeout=1000)
                                await page.mouse.wheel(0, int(info.get("scrollHeight", 1000)) * (1 if bottom else -1))
                                await page.wait_for_timeout(200)
                            except Exception:
                                pass
                            await record_view()
                            scroll_steps += 1
                        continue
                    await locator.evaluate(
                        """el => {
                          el.scrollTo({top: 0, left: 0, behavior: 'instant'});
                          el.dispatchEvent(new Event('scroll', {bubbles: true}));
                        }""",
                    )
                    await page.wait_for_timeout(220)
                    await record_view()

                    # Walk the vertical virtual rows. At every row window also
                    # traverse horizontal virtual columns before moving down.
                    vertical_guard = 0
                    while vertical_guard < 24:
                        vertical_guard += 1
                        horizontal_guard = 0
                        while not period_probe and horizontal_guard < 16:
                            horizontal_guard += 1
                            before = await locator.evaluate(
                                "el => ({top: el.scrollTop, left: el.scrollLeft, "
                                "maxTop: Math.max(0, el.scrollHeight - el.clientHeight), "
                                "maxLeft: Math.max(0, el.scrollWidth - el.clientWidth), "
                                "clientHeight: el.clientHeight, clientWidth: el.clientWidth})",
                            )
                            if float(before.get("maxLeft", 0) or 0) <= float(before.get("left", 0) or 0) + 1:
                                break
                            await locator.hover(timeout=10_000)
                            await page.mouse.wheel(max(160, int(before.get("clientWidth", 0) * 0.8)), 0)
                            await page.wait_for_timeout(180)
                            after_left = float(await locator.evaluate("el => el.scrollLeft") or 0)
                            if after_left <= float(before.get("left", 0) or 0) + 1:
                                await locator.evaluate(
                                    """(el, amount) => {
                                      el.scrollBy({left: amount, top: 0, behavior: 'instant'});
                                      el.dispatchEvent(new Event('scroll', {bubbles: true}));
                                    }""",
                                    max(160, int(before.get("clientWidth", 0) * 0.8)),
                                )
                                await page.wait_for_timeout(180)
                                after_left = float(await locator.evaluate("el => el.scrollLeft") or 0)
                            await record_view()
                            scroll_steps += 1
                            if after_left <= float(before.get("left", 0) or 0) + 1:
                                break

                        await locator.evaluate(
                            """el => {
                              el.scrollTo({left: 0, top: el.scrollTop, behavior: 'instant'});
                              el.dispatchEvent(new Event('scroll', {bubbles: true}));
                            }""",
                        )
                        await page.wait_for_timeout(120)
                        before_y = await locator.evaluate(
                            "el => ({top: el.scrollTop, maxTop: Math.max(0, el.scrollHeight - el.clientHeight), "
                            "clientHeight: el.clientHeight})",
                        )
                        if float(before_y.get("maxTop", 0) or 0) <= float(before_y.get("top", 0) or 0) + 1:
                            break
                        await locator.hover(timeout=10_000)
                        amount_y = max(120, int(before_y.get("clientHeight", 0) * 0.8))
                        await page.mouse.wheel(0, amount_y)
                        await page.wait_for_timeout(220)
                        after_top = float(await locator.evaluate("el => el.scrollTop") or 0)
                        if after_top <= float(before_y.get("top", 0) or 0) + 1:
                            await locator.evaluate(
                                """(el, amount) => {
                                  el.scrollBy({left: 0, top: amount, behavior: 'instant'});
                                  el.dispatchEvent(new Event('scroll', {bubbles: true}));
                                }""",
                                amount_y,
                            )
                            await page.wait_for_timeout(220)
                            after_top = float(await locator.evaluate("el => el.scrollTop") or 0)
                        await record_view()
                        scroll_steps += 1
                        if after_top <= float(before_y.get("top", 0) or 0) + 1:
                            break

                merged = "\n---视图分段---\n".join(views)
                recovered[code] = merged
                evidence.append({
                    "card_code": code,
                    "strategy": "native_wheel_then_scroll_event_fallback",
                    "status": "month_probe_complete" if period_probe else "current_period_found" if _card_has_current_period(code, merged, report_month) else "current_period_not_found",
                    "segments": len(views),
                    "scroll_steps": scroll_steps,
                    "scrollers": scrollables,
                })
            except Exception as exc:
                evidence.append({
                    "card_code": code,
                    "strategy": "native_wheel",
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                    "segments": 0,
                })

        return recovered, evidence

    @staticmethod
    def _parse_evaluate_payload(raw: str) -> dict[str, Any]:
        """Parse the JSON object returned inside Playwright MCP result text."""

        if isinstance(raw, dict):
            return raw

        start = raw.find("{")
        if start < 0:
            return {}
        try:
            # MCP appends a ``Ran Playwright code`` block after the JSON
            # result.  That block contains many additional braces, therefore
            # slicing through the last ``}`` makes otherwise valid JSON fail.
            # ``raw_decode`` consumes exactly the first JSON value and safely
            # ignores the audit text that follows it.
            value, _ = json.JSONDecoder().raw_decode(raw[start:])
            if isinstance(value, str):
                value = json.loads(value)
            return value if isinstance(value, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def _save_data_package(self, result: dict[str, Any], raw: str) -> None:
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = _now().strftime("%Y%m%d-%H%M%S")
        path = SNAPSHOT_DIR / f"data-source-package-{stamp}.json"
        result["source_url"] = self.source_url
        result["snapshot_path"] = str(path.resolve())
        payload = dict(result)
        payload["raw_evaluate_result"] = raw
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    async def preflight(self, *, open_page: bool = True, report_month: str = "", force_refresh: bool = False) -> dict[str, Any]:
        """Perform a bounded login/page check without expanding all 45 grids."""

        cached = self._load_recent_ready_package(report_month) if report_month and not force_refresh else None
        if cached is not None:
            result = self.package_preflight(cached, report_month)
            self._last_result = dict(result)
            return result

        try:
            await self.ensure_connected()
            result = await self._quick_page_status()
            if open_page and not result.get("page_ready") and not result.get("session_invalidated"):
                await self._call("browser_navigate", url=self.source_url)
                await self._call("browser_resize", width=1920, height=1080)
                # Do not request a full accessibility snapshot here. Expanding
                # every virtualized table can take minutes and belongs only to
                # the actual capture stage, never to the login preflight.
                result = {"page_ready": False}
                for wait_seconds in (2, 3, 5):
                    await self._call("browser_wait_for", time=wait_seconds)
                    result = await self._quick_page_status()
                    if result.get("page_ready") or result.get("code") == "data_source_login_required":
                        break
            cached = self._load_recent_ready_package(report_month) if report_month and result.get("page_ready") and not force_refresh else None
            if cached is not None:
                cached = await self._refresh_cached_delays(cached, result)
                result = {**result, "report_month": report_month,
                          "month_confirmation": {"status": "explicit_validated_package", "report_month": report_month}}
            else:
                result = await self._confirm_page_month(result, report_month)
            month_confirmation = result.get("month_confirmation", {})
            live_report_month = str(result.get("report_month", ""))
            page_text = str(result.pop("page_text", ""))
            current_url = str(result.get("current_url", ""))
            page_title = str(result.get("page_title", ""))
            auth_session_state = str(result.get("auth_session_state", ""))
            assessed = self._assess_snapshot(page_text)
            assessed.update({
                "connected": True,
                "page_ready": bool(result.get("page_ready")),
                "generation_ready": False,
                "connector_ready": bool(result.get("page_ready")),
                "code": result.get("code", assessed.get("code")),
                "message": result.get("message", assessed.get("message")),
                "report_month": live_report_month,
                "month_confirmation": month_confirmation,
                "current_url": current_url,
                "page_title": page_title,
                "auth_session_state": auth_session_state,
                "input_gate": "待登录" if auth_session_state == "login_required" else "阻断" if not result.get("page_ready") else "等待数据校验",
            })
            result = assessed
            if result.get("page_ready"):
                self._record_verified_session(
                    url=current_url or self.source_url,
                    report_month=live_report_month,
                )
            session = self._load_session_metadata()
            result.update({
                "auth_session_owner": session.get("windows_user", ""),
                "auth_session_last_verified_at": session.get("verified_at", ""),
                "auth_session_last_verified_url": session.get("verified_url", ""),
            })
            cached = cached or (self._load_recent_ready_package(live_report_month) if result.get("page_ready") and not force_refresh else None)
            partial = self._partial_package_cards(live_report_month) if live_report_month and not cached and not force_refresh else {}
            mode = "reuse" if cached else "force_refresh" if force_refresh else "partial_collect" if partial else "collect"
            reason = "同月完整数据包已通过校验，跳过采集。" if cached else "用户明确要求刷新。" if force_refresh else f"同月已保存 {len(partial)} 张可独立确认月份的卡片，只补其余项。" if partial else "未找到该月份、该数据源、当前映射的完整可复用数据包。"
            if not result.get("page_ready"):
                mode = "awaiting_month" if str(result.get("code", "")).startswith("report_month_") else "waiting_source"
                reason = str(result.get("message", "前置条件未满足，尚未采集。"))
            result.update(collection_mode=mode, cards_reused=45 if cached else len(partial),
                          cards_to_collect=0 if cached or not result.get("page_ready") else 45-len(partial),
                          reuse_decision={"reason": "same_report_month_verified" if cached else "force_refresh" if force_refresh else "partial_package" if partial else "no_valid_package_for_month", "message": reason})
            if cached is not None:
                result.update({
                    "generation_ready": True,
                    "connector_ready": True,
                    "input_gate": "通过（同月份历史数据包）",
                    "code": "data_source_package_reused",
                    "message": (
                        f"报告目标月份为 {live_report_month}；已找到同月份45/45历史数据包，"
                        "后续将从数据采集检查点继续。"
                    ),
                    "mapping_cards_expected": int(cached.get("cards_expected", 45)),
                    "mapping_cards_matched": int(cached.get("cards_usable", 45)),
                    "mapping_coverage_pct": 100.0,
                    "snapshot_path": cached.get("snapshot_path", ""),
                    "data_package_path": cached.get("snapshot_path", ""),
                    "snapshot_reused": True,
                    "captured_at": cached.get("captured_at", ""),
                    "matched_cards": _page_card_codes(),
                    "missing_cards": [],
                    "cards_collected": 0,
                })
            self._save_snapshot(page_text, result)
            self._last_result = result
            return dict(result)
        except Exception as exc:
            # A failed read is not authorization to tear down the user's
            # authenticated browser or its legacy driver.
            owner_mismatch = isinstance(exc, MonthlyReportSessionOwnerMismatch)
            reconnect_required = isinstance(exc, MonthlyReportBrowserReconnectionRequired)
            result = {
                "installed": PLAYWRIGHT_MCP_CLI.is_file(),
                "connected": bool(
                    (self._client and self._client.is_connected)
                    or (self._direct_page and not self._direct_page.is_closed())
                ),
                "page_ready": False,
                "generation_ready": False,
                "input_gate": "阻断",
                "code": (
                    "data_source_session_owner_mismatch"
                    if owner_mismatch
                    else "data_source_browser_reconnect_required"
                    if reconnect_required
                    else "data_source_connection_failed"
                ),
                "message": (
                    str(exc)
                    if owner_mismatch or reconnect_required
                    else f"数据源读取连接失败：{type(exc).__name__}: {exc}"
                ),
                "last_error": f"{type(exc).__name__}: {exc}",
            }
            self._last_result = result
            return dict(result)

    def _assess_snapshot(self, snapshot: str) -> dict[str, Any]:
        expected = _page_card_codes()
        matched = [
            code
            for code in expected
            if code in snapshot
            or any(alias in snapshot for alias in SOURCE_CARD_CODE_ALIASES.get(code, ()))
        ]
        missing = [code for code in expected if code not in matched]
        lowered = snapshot.lower()
        # Do not use the generic word "登录" alone: authenticated data pages
        # may contain it in navigation/help text.  Require explicit form cues.
        login_markers = ["用户名", "密码", "sign in", "log in"]
        page_markers = ["P1.1-1", "P2-3.1", "日期组合", "整体市场销量"]
        login_required = any(marker.lower() in lowered for marker in login_markers)
        page_ready = any(marker.lower() in lowered for marker in page_markers) and not login_required
        coverage = round(len(matched) / len(expected) * 100, 2) if expected else 0.0

        if login_required:
            code = "data_source_login_required"
            message = "已打开月报专用浏览器。请在该浏览器完成登录并进入月报数据源页面，然后返回本页面再次开始分析。"
        elif not page_ready:
            code = "data_source_page_not_ready"
            message = (
                "数据源页面框架已打开，但卡片尚未完成加载。"
                "请保持页面打开，稍后重新检查；系统不会把该状态误判为需要重新登录。"
            )
        elif missing:
            code = "data_source_connector_ready_with_snapshot_warning"
            message = (
                f"数据源页面已连接；当前预检快照识别到 {len(matched)}/{len(expected)} 个页面卡片。"
                "长页面的一次可访问性快照可能不包含全部卡片，因此该覆盖率仅作采集提示，不再阻断生成。"
                "后续仍须按映射逐卡片读取和校验，未读到的数值不得沿用或补造。"
            )
        else:
            code = "data_source_connector_ready"
            message = (
                "数据源页面和全部页面卡片已经识别，浏览器连接验证完成。"
                "后续将按映射逐卡片读取和校验数据。"
            )

        return {
            "installed": True,
            "connected": True,
            "page_ready": page_ready,
            "generation_ready": bool(page_ready),
            "connector_ready": bool(page_ready),
            "input_gate": ("通过（快照覆盖提示）" if missing else "通过") if page_ready else "阻断",
            "code": code,
            "message": message,
            "mapping_cards_expected": len(expected),
            "mapping_cards_matched": len(matched),
            "mapping_coverage_pct": coverage,
            "matched_cards": matched,
            "missing_cards": missing,
            "captured_at": _now().isoformat(timespec="seconds"),
        }

    def _save_snapshot(self, snapshot: str, result: dict[str, Any]) -> None:
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = _now().strftime("%Y%m%d-%H%M%S")
        path = SNAPSHOT_DIR / f"data-source-preflight-{stamp}.json"
        payload = {
            "metadata": result,
            "source_url": self.source_url,
            "snapshot_type": "playwright_accessibility_snapshot",
            "snapshot": snapshot,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        result["preflight_snapshot_path"] = str(path)
        if not result.get("snapshot_reused"):
            result["snapshot_path"] = str(path)

    async def close(self, *, close_browser: bool = False) -> None:
        """Release a CDP connection; closing a live browser must be explicit."""

        async with self._lock:
            if not close_browser and (
                self._client is not None
                or (self._direct_context is not None and self._direct_browser is None)
            ):
                # Stopping an owned Playwright/MCP driver can also stop Chrome.
                # Preserve that driver together with the authenticated window.
                self._last_result["browser_session_preserved"] = True
                return
            if self._client is not None:
                await self._client.close(ignore_errors=True)
                self._client = None
            if self._direct_context is not None:
                if close_browser:
                    await self._direct_context.close()
                self._direct_context = None
                self._direct_page = None
                self._direct_browser = None
            if self._direct_playwright is not None:
                await self._direct_playwright.stop()
                self._direct_playwright = None
            self._last_result["connected"] = False


MONTHLY_REPORT_BROWSER = MonthlyReportBrowserConnector()


class _ReadOnlyMonthlyReportTool(ToolBase):
    is_concurrency_safe = False
    is_read_only = True

    async def check_permissions(
        self,
        tool_input: dict[str, Any],
        context: PermissionContext,
    ) -> PermissionDecision:
        return PermissionDecision(
            behavior=PermissionBehavior.ALLOW,
            message=f"{self.name} 仅读取月报专用浏览器中的已呈现内容。",
        )


class MonthlyReportSourceStatusTool(_ReadOnlyMonthlyReportTool):
    name = "monthly_report_source_status"
    description = "检查乘用车月报数据源连接、登录状态和映射卡片覆盖率，不修改页面。"
    input_schema = {"type": "object", "properties": {}}

    async def call(self) -> ToolChunk:
        result = await MONTHLY_REPORT_BROWSER.preflight(open_page=False)
        from tools.custom_tools import record_tool_call

        record_tool_call(self.name, "success", f"code={result.get('code', '')}")
        return ToolChunk(content=[TextBlock(text=json.dumps(result, ensure_ascii=False, indent=2))])


class MonthlyReportReadCardTool(_ReadOnlyMonthlyReportTool):
    name = "monthly_report_read_card"
    description = "按固定映射中的卡片编号读取月报数据源卡片内容；不允许任意网址或页面写操作。"
    input_schema = {
        "type": "object",
        "properties": {
            "card_code": {
                "type": "string",
                "description": "映射表中的卡片编号，例如 P1.1-1 或 P2-3.1。",
            },
        },
        "required": ["card_code"],
    }

    async def call(self, card_code: str) -> ToolChunk:
        result = await MONTHLY_REPORT_BROWSER.read_card(card_code)
        from tools.custom_tools import record_tool_call

        record_tool_call(self.name, "success", f"card_code={card_code}")
        return ToolChunk(content=[TextBlock(text=json.dumps(result, ensure_ascii=False, indent=2))])


class MonthlyReportReadAllCardsTool(_ReadOnlyMonthlyReportTool):
    name = "monthly_report_read_all_cards"
    description = "读取并标准化乘用车月报数据源中的全部45张卡片，保存可追溯快照；不修改页面。"
    input_schema = {"type": "object", "properties": {}}

    async def call(self) -> ToolChunk:
        result = await MONTHLY_REPORT_BROWSER.read_all_cards()
        from tools.custom_tools import record_tool_call

        record_tool_call(
            self.name,
            "success" if result.get("generation_ready") else "blocked",
            f"usable={result.get('cards_usable', 0)}/{result.get('cards_expected', 45)}",
        )
        return ToolChunk(content=[TextBlock(text=json.dumps(result, ensure_ascii=False, indent=2))])


def build_monthly_report_browser_tools() -> list[ToolBase]:
    return [
        MonthlyReportSourceStatusTool(),
        MonthlyReportReadCardTool(),
        MonthlyReportReadAllCardsTool(),
    ]
