#!/usr/bin/env python3
"""Destructive-but-isolated smoke test for the monthly browser lifecycle.

The default mode creates a random temporary Chrome profile and asks a worker
process to attach through ``MonthlyReportBrowserConnector``.  The worker puts
a random marker in a data URL and is then terminated to simulate the web
service exiting.  A fresh worker must attach to the same detached Chrome and
observe the marker.

This script never uses the production profile or the production CDP port.  At
the end it sends CDP ``Browser.close`` only after the test profile, Chrome PID,
listener PID, runtime metadata, and browser command line have all been checked.
If any identity check is ambiguous, cleanup fails closed and leaves the random
test profile in place for manual inspection.

The ``--worker`` modes are implementation details used by the parent process;
running the script without arguments executes the complete check.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import queue
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, TextIO
from unittest.mock import patch
from urllib.parse import quote


SCRIPT_PATH = Path(__file__).resolve()
PROJECT_DIR = SCRIPT_PATH.parents[1]
PRODUCTION_PROFILE_DIR = PROJECT_DIR / "runtime" / "monthly-report-browser-profile"
PRODUCTION_CDP_PORT = 9231
TEST_ROOT_PREFIX = "monthly-browser-lifecycle-"
MARKER_ELEMENT_ID = "monthly-browser-lifecycle-marker"
WORKER_READY_TIMEOUT_SECONDS = 60.0
WORKER_EXIT_TIMEOUT_SECONDS = 30.0


def emit(event: str, *, status: str = "ok", **details: Any) -> None:
    """Write one machine-readable log record and flush it immediately."""

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "event": event,
        "status": status,
        "process_pid": os.getpid(),
        **details,
    }
    print(json.dumps(payload, ensure_ascii=False, default=str), flush=True)


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left.resolve())) == os.path.normcase(str(right.resolve()))


def _is_below(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


@dataclass(frozen=True)
class IsolatedPaths:
    root: Path
    profile: Path
    runtime: Path
    session: Path
    mcp_output: Path
    mcp_local_app_data: Path

    @classmethod
    def from_root(cls, root: Path) -> "IsolatedPaths":
        resolved = root.resolve()
        return cls(
            root=resolved,
            profile=resolved / "profile",
            runtime=resolved / "browser-runtime.json",
            session=resolved / "session.json",
            mcp_output=resolved / "mcp-output",
            mcp_local_app_data=resolved / "mcp-localappdata",
        )


def _validate_isolated_paths(paths: IsolatedPaths) -> None:
    temp_root = Path(tempfile.gettempdir()).resolve()
    if not paths.root.name.startswith(TEST_ROOT_PREFIX) or not _is_below(paths.root, temp_root):
        raise RuntimeError(
            f"Refusing lifecycle test outside a random temporary root: {paths.root}"
        )
    expected = IsolatedPaths.from_root(paths.root)
    for name in (
        "profile",
        "runtime",
        "session",
        "mcp_output",
        "mcp_local_app_data",
    ):
        if not _same_path(getattr(paths, name), getattr(expected, name)):
            raise RuntimeError(f"Unexpected isolated {name} path: {getattr(paths, name)}")
    if _same_path(paths.profile, PRODUCTION_PROFILE_DIR):
        raise RuntimeError("Refusing to use the production monthly-report Chrome profile.")
    if not _is_below(paths.profile, paths.root):
        raise RuntimeError("The test profile must be inside the random test root.")


def _load_browser_module() -> Any:
    project = str(PROJECT_DIR)
    if project not in sys.path:
        sys.path.insert(0, project)
    from tools import monthly_report_browser

    return monthly_report_browser


@contextlib.contextmanager
def _patched_browser_paths(module: Any, paths: IsolatedPaths) -> Iterator[None]:
    """Patch every browser-owned path into the random test directory."""

    with patch.multiple(
        module,
        PROFILE_DIR=paths.profile,
        BROWSER_RUNTIME_FILE=paths.runtime,
        SESSION_METADATA_FILE=paths.session,
        MCP_OUTPUT_DIR=paths.mcp_output,
        MCP_LOCAL_APP_DATA=paths.mcp_local_app_data,
    ):
        yield


def _validate_port(port: int) -> None:
    if port == PRODUCTION_CDP_PORT:
        raise RuntimeError("Port 9231 is reserved for the real monthly-report browser.")
    if not 1024 <= port <= 65535:
        raise RuntimeError(f"Invalid test CDP port: {port}")


def _allocate_dynamic_loopback_port() -> int:
    """Ask Windows for an unused ephemeral loopback port, explicitly excluding 9231."""

    for _ in range(20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            port = int(listener.getsockname()[1])
        if port != PRODUCTION_CDP_PORT:
            return port
    raise RuntimeError("Could not allocate a non-9231 dynamic loopback port.")


def _marker_url(marker: str) -> str:
    html = (
        "<!doctype html><meta charset=utf-8>"
        f"<title>{marker}</title>"
        f'<main id="{MARKER_ELEMENT_ID}">{marker}</main>'
    )
    return "data:text/html;charset=utf-8," + quote(html, safe="")


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise RuntimeError(f"Could not read JSON object from {path}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected a JSON object in {path}")
    return value


def _validate_runtime_metadata(
    paths: IsolatedPaths,
    port: int,
    *,
    expected_pid: int | None = None,
) -> dict[str, Any]:
    metadata = _read_json_object(paths.runtime)
    if metadata.get("mode") != "detached_cdp":
        raise RuntimeError(f"Unexpected browser runtime mode: {metadata.get('mode')!r}")
    if not _same_path(Path(str(metadata.get("profile_path", ""))), paths.profile):
        raise RuntimeError("Runtime metadata does not identify the random test profile.")
    if int(metadata.get("cdp_port", 0)) != port:
        raise RuntimeError("Runtime metadata does not identify the random test CDP port.")
    pid = int(metadata.get("pid", 0))
    if pid <= 0:
        raise RuntimeError("Runtime metadata has no valid Chrome PID.")
    if expected_pid is not None and pid != expected_pid:
        raise RuntimeError(
            f"Runtime Chrome PID changed: expected {expected_pid}, observed {pid}."
        )
    if metadata.get("contains_credentials") is not False:
        raise RuntimeError("Runtime metadata is not explicitly marked credential-free.")
    return metadata


def _validate_runtime_process_identity(
    metadata: dict[str, Any],
    identity: dict[str, Any],
) -> None:
    if str(metadata.get("windows_user", "")).casefold() != str(
        identity.get("owner", "")
    ).casefold():
        raise RuntimeError("Runtime Windows user does not match the test Chrome owner.")
    if str(metadata.get("windows_sid", "")) != str(identity.get("owner_sid", "")):
        raise RuntimeError("Runtime Windows SID does not match the test Chrome owner SID.")
    executable = Path(str(identity.get("executable", "")))
    if executable.name.casefold() != "chrome.exe" or not executable.is_file():
        raise RuntimeError("The exact-profile test process is not installed Google Chrome.")


async def _verified_identity(
    module: Any,
    paths: IsolatedPaths,
    port: int,
    *,
    expected_pid: int | None = None,
) -> dict[str, Any]:
    """Cross-check runtime metadata against the exact-profile OS process query."""

    metadata = _validate_runtime_metadata(paths, port, expected_pid=expected_pid)
    processes = await asyncio.to_thread(module._dedicated_chrome_processes)
    if len(processes) != 1:
        raise RuntimeError(
            f"Expected exactly one Chrome for the random test profile; found {len(processes)}."
        )
    identity = dict(processes[0])
    pid = int(identity.get("pid", 0))
    if pid != int(metadata["pid"]):
        raise RuntimeError("Runtime PID does not match the exact-profile Chrome PID.")
    if int(identity.get("cdp_port", 0)) != port:
        raise RuntimeError("Exact-profile Chrome is not using the random test CDP port.")
    if int(identity.get("listener_pid", 0)) != pid:
        raise RuntimeError("The test CDP listener PID does not match the test Chrome PID.")
    _validate_runtime_process_identity(metadata, identity)
    return identity


def _configure_worker_environment(port: int, marker_url: str) -> None:
    os.environ["MONTHLY_REPORT_BROWSER_BACKEND"] = "direct"
    os.environ["MONTHLY_REPORT_BROWSER_CDP_PORT"] = str(port)
    os.environ["MONTHLY_REPORT_BROWSER_HEADLESS"] = "1"
    os.environ["MONTHLY_REPORT_BROWSER_PROXY"] = "direct"
    os.environ["MONTHLY_REPORT_SOURCE_URL"] = marker_url


async def _worker_async(args: argparse.Namespace) -> int:
    if os.name != "nt":
        raise RuntimeError("This lifecycle check is intentionally Windows-only.")
    if not args.test_root or not args.marker or args.port is None:
        raise RuntimeError("Worker mode requires --test-root, --port, and --marker.")
    if args.worker == "reattach" and not args.expected_browser_pid:
        raise RuntimeError("The reattach worker requires --expected-browser-pid.")
    if len(args.marker) < 16 or not all(ch.isalnum() or ch in "-_" for ch in args.marker):
        raise RuntimeError("The lifecycle marker is not a valid random test token.")

    paths = IsolatedPaths.from_root(args.test_root)
    _validate_isolated_paths(paths)
    _validate_port(args.port)
    marker_url = _marker_url(args.marker)
    _configure_worker_environment(args.port, marker_url)
    module = _load_browser_module()
    if _same_path(Path(module.PROFILE_DIR), paths.profile):
        raise RuntimeError("The imported module unexpectedly points at the test profile before patching.")
    if not _same_path(Path(module.PROFILE_DIR), PRODUCTION_PROFILE_DIR):
        raise RuntimeError("The imported module has an unexpected production profile path.")

    connector: Any | None = None
    with _patched_browser_paths(module, paths):
        try:
            connector = module.MonthlyReportBrowserConnector()
            emit(
                "worker_connecting",
                worker_mode=args.worker,
                test_root=str(paths.root),
                profile_dir=str(paths.profile),
                cdp_port=args.port,
            )
            page = await connector.ensure_connected()

            if args.worker == "seed":
                await page.goto(marker_url, wait_until="load")
                observed = await page.locator(f"#{MARKER_ELEMENT_ID}").text_content()
                if observed != args.marker:
                    raise RuntimeError(
                        f"Could not write the lifecycle marker: observed {observed!r}."
                    )
            else:
                observed = await page.locator(f"#{MARKER_ELEMENT_ID}").text_content(
                    timeout=10_000
                )
                if observed != args.marker:
                    raise RuntimeError(
                        f"Lifecycle marker was not preserved: observed {observed!r}."
                    )

            identity = await _verified_identity(
                module,
                paths,
                args.port,
                expected_pid=args.expected_browser_pid,
            )
            browser_pid = int(identity["pid"])
            if args.worker == "seed":
                emit(
                    "worker_ready",
                    worker_mode=args.worker,
                    marker=args.marker,
                    marker_url=page.url,
                    browser_pid=browser_pid,
                    listener_pid=int(identity["listener_pid"]),
                    profile_dir=str(paths.profile),
                    runtime_file=str(paths.runtime),
                    session_file=str(paths.session),
                    cdp_port=args.port,
                )
                emit(
                    "worker_waiting_for_parent_termination",
                    worker_mode=args.worker,
                    browser_pid=browser_pid,
                )
                await asyncio.Event().wait()
            else:
                emit(
                    "worker_verified",
                    worker_mode=args.worker,
                    marker=args.marker,
                    marker_url=page.url,
                    browser_pid=browser_pid,
                    listener_pid=int(identity["listener_pid"]),
                    profile_dir=str(paths.profile),
                    cdp_port=args.port,
                )
                await connector.close(close_browser=False)
                connector = None
                emit("worker_detached", worker_mode=args.worker, browser_pid=browser_pid)
            return 0
        finally:
            # The seed worker is terminated by the parent, so this only runs on
            # a normal return or an exception.  This releases the CDP client; it
            # never sends Browser.close.
            if connector is not None and args.worker != "seed":
                await connector.close(close_browser=False)


def _worker_main(args: argparse.Namespace) -> int:
    try:
        return asyncio.run(_worker_async(args))
    except BaseException as exc:
        emit(
            "worker_failed",
            status="error",
            worker_mode=args.worker,
            error_type=type(exc).__name__,
            error=str(exc),
            traceback=traceback.format_exc(),
        )
        return 1


@dataclass
class ManagedWorker:
    label: str
    process: subprocess.Popen[str]
    output: "queue.Queue[tuple[str, str | None]]"
    threads: tuple[threading.Thread, threading.Thread]


def _pump_stream(
    stream: TextIO,
    stream_name: str,
    output: "queue.Queue[tuple[str, str | None]]",
) -> None:
    try:
        for line in iter(stream.readline, ""):
            output.put((stream_name, line.rstrip("\r\n")))
    finally:
        output.put((stream_name, None))
        stream.close()


def _worker_command(
    mode: str,
    paths: IsolatedPaths,
    port: int,
    marker: str,
    *,
    expected_browser_pid: int | None = None,
) -> list[str]:
    command = [
        sys.executable,
        str(SCRIPT_PATH),
        "--worker",
        mode,
        "--test-root",
        str(paths.root),
        "--port",
        str(port),
        "--marker",
        marker,
    ]
    if expected_browser_pid is not None:
        command.extend(["--expected-browser-pid", str(expected_browser_pid)])
    return command


def _start_worker(
    label: str,
    mode: str,
    paths: IsolatedPaths,
    port: int,
    marker: str,
    *,
    expected_browser_pid: int | None = None,
) -> ManagedWorker:
    environment = dict(os.environ)
    environment.update(
        {
            "MONTHLY_REPORT_BROWSER_BACKEND": "direct",
            "MONTHLY_REPORT_BROWSER_CDP_PORT": str(port),
            "MONTHLY_REPORT_BROWSER_HEADLESS": "1",
            "MONTHLY_REPORT_BROWSER_PROXY": "direct",
            "MONTHLY_REPORT_SOURCE_URL": _marker_url(marker),
        }
    )
    process = subprocess.Popen(
        _worker_command(
            mode,
            paths,
            port,
            marker,
            expected_browser_pid=expected_browser_pid,
        ),
        cwd=str(PROJECT_DIR),
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if process.stdout is None or process.stderr is None:
        raise RuntimeError("Could not capture worker output.")
    output: "queue.Queue[tuple[str, str | None]]" = queue.Queue()
    stdout_thread = threading.Thread(
        target=_pump_stream,
        args=(process.stdout, "stdout", output),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_pump_stream,
        args=(process.stderr, "stderr", output),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()
    worker = ManagedWorker(label, process, output, (stdout_thread, stderr_thread))
    emit(
        "worker_started",
        worker=label,
        worker_mode=mode,
        worker_pid=process.pid,
        expected_browser_pid=expected_browser_pid,
    )
    return worker


def _relay_worker_line(worker: ManagedWorker, stream_name: str, line: str) -> dict[str, Any] | None:
    if not line:
        return None
    try:
        record = json.loads(line)
    except (ValueError, TypeError):
        emit(
            "worker_stream",
            status="diagnostic" if stream_name == "stdout" else "warning",
            worker=worker.label,
            stream=stream_name,
            line=line,
        )
        return None
    if not isinstance(record, dict):
        emit(
            "worker_stream",
            status="diagnostic",
            worker=worker.label,
            stream=stream_name,
            value=record,
        )
        return None
    emit(
        "worker_event",
        status=str(record.get("status", "ok")),
        worker=worker.label,
        stream=stream_name,
        record=record,
    )
    return record


def _wait_for_worker_event(
    worker: ManagedWorker,
    event: str,
    *,
    timeout: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            stream_name, line = worker.output.get(timeout=0.2)
        except queue.Empty:
            if worker.process.poll() is not None:
                break
            continue
        if line is None:
            continue
        record = _relay_worker_line(worker, stream_name, line)
        if record and record.get("event") == event:
            return record
    exit_code = worker.process.poll()
    raise RuntimeError(
        f"Worker {worker.label!r} did not emit {event!r} within {timeout:.0f}s "
        f"(exit_code={exit_code})."
    )


def _drain_worker_output(worker: ManagedWorker) -> None:
    while True:
        try:
            stream_name, line = worker.output.get_nowait()
        except queue.Empty:
            break
        if line is not None:
            _relay_worker_line(worker, stream_name, line)


def _wait_for_worker_exit(worker: ManagedWorker, *, timeout: float) -> int:
    deadline = time.monotonic() + timeout
    while worker.process.poll() is None and time.monotonic() < deadline:
        _drain_worker_output(worker)
        time.sleep(0.05)
    if worker.process.poll() is None:
        raise RuntimeError(f"Worker {worker.label!r} did not exit within {timeout:.0f}s.")
    for thread in worker.threads:
        thread.join(timeout=1.0)
    _drain_worker_output(worker)
    return int(worker.process.returncode)


def _terminate_worker(worker: ManagedWorker | None) -> None:
    if worker is None or worker.process.poll() is not None:
        if worker is not None:
            _drain_worker_output(worker)
        return
    emit(
        "worker_termination_requested",
        worker=worker.label,
        worker_pid=worker.process.pid,
        scope="worker_process_only",
    )
    worker.process.terminate()
    try:
        worker.process.wait(timeout=10.0)
    except subprocess.TimeoutExpired:
        emit(
            "worker_termination_escalated",
            status="warning",
            worker=worker.label,
            worker_pid=worker.process.pid,
            scope="worker_process_only",
        )
        worker.process.kill()
        worker.process.wait(timeout=10.0)
    for thread in worker.threads:
        thread.join(timeout=1.0)
    _drain_worker_output(worker)
    emit(
        "worker_terminated",
        worker=worker.label,
        worker_pid=worker.process.pid,
        exit_code=worker.process.returncode,
    )


def _validate_identity_fields(identity: dict[str, Any], port: int, expected_pid: int | None) -> int:
    pid = int(identity.get("pid", 0))
    if pid <= 0:
        raise RuntimeError("The exact-profile Chrome query returned no valid PID.")
    if expected_pid is not None and pid != expected_pid:
        raise RuntimeError(
            f"Cleanup PID mismatch: expected {expected_pid}, observed {pid}."
        )
    if int(identity.get("cdp_port", 0)) != port:
        raise RuntimeError("Cleanup candidate is not using the random test CDP port.")
    if int(identity.get("listener_pid", 0)) != pid:
        raise RuntimeError("Cleanup candidate does not own its CDP listener.")
    return pid


async def _close_verified_test_browser(
    paths: IsolatedPaths,
    port: int,
    expected_pid: int | None,
) -> dict[str, Any]:
    """Close only an exact-profile, exact-PID test Chrome via CDP Browser.close."""

    _validate_isolated_paths(paths)
    _validate_port(port)
    module = _load_browser_module()
    with _patched_browser_paths(module, paths):
        processes = await asyncio.to_thread(module._dedicated_chrome_processes)
        if not processes:
            return {"closed": False, "reason": "no_test_browser"}
        if len(processes) != 1:
            raise RuntimeError(
                f"Cleanup refused: found {len(processes)} exact-profile Chrome processes."
            )
        identity = dict(processes[0])
        pid = _validate_identity_fields(identity, port, expected_pid)

        if not paths.runtime.is_file():
            raise RuntimeError(
                "Cleanup refused: the exact-profile Chrome has no verified runtime metadata."
            )
        metadata = _validate_runtime_metadata(paths, port, expected_pid=pid)
        _validate_runtime_process_identity(metadata, identity)

        runtime = await module.async_playwright().start()
        session: Any | None = None
        command_sent = False
        try:
            browser = await runtime.chromium.connect_over_cdp(
                f"http://127.0.0.1:{port}", timeout=20_000
            )
            verifier = module.MonthlyReportBrowserConnector()
            await verifier._verify_cdp_profile(browser)

            # Repeat the OS identity check immediately before the destructive
            # command to guard against a PID/port change between checks.
            current = await asyncio.to_thread(module._dedicated_chrome_processes)
            if len(current) != 1:
                raise RuntimeError("Cleanup identity became ambiguous before Browser.close.")
            current_pid = _validate_identity_fields(dict(current[0]), port, pid)
            if current_pid != pid:
                raise RuntimeError("Cleanup Chrome PID changed before Browser.close.")
            _validate_runtime_process_identity(metadata, dict(current[0]))

            emit(
                "cleanup_identity_verified",
                browser_pid=pid,
                listener_pid=int(current[0]["listener_pid"]),
                profile_dir=str(paths.profile),
                cdp_port=port,
                close_method="CDP Browser.close",
            )
            session = await browser.new_browser_cdp_session()
            command_sent = True
            try:
                await session.send("Browser.close")
            except Exception as exc:
                # A successful Browser.close may tear down the transport before
                # Playwright receives the empty response.  The process check
                # below remains the source of truth.
                emit(
                    "browser_close_transport_ended",
                    status="diagnostic",
                    browser_pid=pid,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
        finally:
            if session is not None and not command_sent:
                with contextlib.suppress(Exception):
                    await session.detach()
            with contextlib.suppress(Exception):
                await runtime.stop()

        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            remaining = await asyncio.to_thread(module._dedicated_chrome_processes)
            if not remaining and not module._port_is_listening(port):
                emit(
                    "test_browser_closed",
                    browser_pid=pid,
                    profile_dir=str(paths.profile),
                    cdp_port=port,
                    close_method="CDP Browser.close",
                )
                return {"closed": True, "browser_pid": pid}
            await asyncio.sleep(0.25)
        raise RuntimeError(
            "CDP Browser.close was sent, but the verified test Chrome or its listener remained."
        )


def _remove_test_root(paths: IsolatedPaths) -> None:
    _validate_isolated_paths(paths)
    if not paths.root.exists():
        return
    last_error: OSError | None = None
    for _ in range(12):
        try:
            shutil.rmtree(paths.root)
            emit("test_root_removed", test_root=str(paths.root))
            return
        except OSError as exc:
            last_error = exc
            time.sleep(0.25)
    raise RuntimeError(f"Could not remove random test root {paths.root}") from last_error


def _validate_parent_record(
    record: dict[str, Any],
    paths: IsolatedPaths,
    port: int,
    marker: str,
    *,
    expected_pid: int | None = None,
) -> int:
    if int(record.get("cdp_port", 0)) != port:
        raise RuntimeError("Worker reported a different CDP port.")
    if record.get("marker") != marker:
        raise RuntimeError("Worker reported a different lifecycle marker.")
    if not _same_path(Path(str(record.get("profile_dir", ""))), paths.profile):
        raise RuntimeError("Worker reported a different browser profile.")
    pid = int(record.get("browser_pid", 0))
    if pid <= 0:
        raise RuntimeError("Worker reported no valid Chrome PID.")
    if int(record.get("listener_pid", 0)) != pid:
        raise RuntimeError("Worker reported a mismatched CDP listener PID.")
    if expected_pid is not None and pid != expected_pid:
        raise RuntimeError(
            f"Reattached to a different Chrome PID: expected {expected_pid}, observed {pid}."
        )
    return pid


def _parent_main() -> int:
    if os.name != "nt":
        raise RuntimeError("This lifecycle check is intentionally Windows-only.")

    port = _allocate_dynamic_loopback_port()
    _validate_port(port)
    paths = IsolatedPaths.from_root(Path(tempfile.mkdtemp(prefix=TEST_ROOT_PREFIX)))
    _validate_isolated_paths(paths)
    marker = secrets.token_urlsafe(24).replace("=", "")
    seed_worker: ManagedWorker | None = None
    reattach_worker: ManagedWorker | None = None
    expected_browser_pid: int | None = None
    primary_failure: tuple[BaseException, str] | None = None
    cleanup_failure: tuple[BaseException, str] | None = None
    browser_cleanup_safe = False

    emit(
        "lifecycle_test_started",
        test_root=str(paths.root),
        profile_dir=str(paths.profile),
        cdp_port=port,
        production_profile_untouched=str(PRODUCTION_PROFILE_DIR.resolve()),
        production_cdp_port_untouched=PRODUCTION_CDP_PORT,
    )
    try:
        seed_worker = _start_worker("seed", "seed", paths, port, marker)
        ready = _wait_for_worker_event(
            seed_worker,
            "worker_ready",
            timeout=WORKER_READY_TIMEOUT_SECONDS,
        )
        expected_browser_pid = _validate_parent_record(ready, paths, port, marker)
        emit(
            "seed_marker_confirmed",
            worker_pid=seed_worker.process.pid,
            browser_pid=expected_browser_pid,
            marker=marker,
        )

        # Terminate only the worker Python process.  Do not use taskkill /T or
        # any process-tree operation: the detached Chrome must survive.
        _terminate_worker(seed_worker)

        reattach_worker = _start_worker(
            "reattach",
            "reattach",
            paths,
            port,
            marker,
            expected_browser_pid=expected_browser_pid,
        )
        verified = _wait_for_worker_event(
            reattach_worker,
            "worker_verified",
            timeout=WORKER_READY_TIMEOUT_SECONDS,
        )
        _validate_parent_record(
            verified,
            paths,
            port,
            marker,
            expected_pid=expected_browser_pid,
        )
        exit_code = _wait_for_worker_exit(
            reattach_worker,
            timeout=WORKER_EXIT_TIMEOUT_SECONDS,
        )
        if exit_code != 0:
            raise RuntimeError(f"Reattach worker exited with code {exit_code}.")
        emit(
            "reattach_marker_confirmed",
            browser_pid=expected_browser_pid,
            marker=marker,
            cdp_port=port,
        )
    except BaseException as exc:
        primary_failure = (exc, traceback.format_exc())
        emit(
            "lifecycle_test_failed",
            status="error",
            error_type=type(exc).__name__,
            error=str(exc),
            traceback=primary_failure[1],
        )
    finally:
        _terminate_worker(seed_worker)
        _terminate_worker(reattach_worker)
        try:
            cleanup = asyncio.run(
                _close_verified_test_browser(paths, port, expected_browser_pid)
            )
            browser_cleanup_safe = bool(cleanup.get("closed")) or cleanup.get("reason") == "no_test_browser"
        except BaseException as exc:
            cleanup_failure = (exc, traceback.format_exc())
            emit(
                "cleanup_failed_closed",
                status="error",
                error_type=type(exc).__name__,
                error=str(exc),
                traceback=cleanup_failure[1],
                test_root_preserved=str(paths.root),
                note="No unverified Chrome process was closed.",
            )

        if browser_cleanup_safe:
            try:
                _remove_test_root(paths)
            except BaseException as exc:
                if cleanup_failure is None:
                    cleanup_failure = (exc, traceback.format_exc())
                emit(
                    "test_root_cleanup_failed",
                    status="error",
                    error_type=type(exc).__name__,
                    error=str(exc),
                    traceback=traceback.format_exc(),
                    test_root_preserved=str(paths.root),
                )
        else:
            emit(
                "test_root_preserved",
                status="warning",
                test_root=str(paths.root),
                reason="browser_identity_or_close_not_verified",
            )

    if primary_failure is not None or cleanup_failure is not None:
        emit(
            "lifecycle_test_complete",
            status="error",
            lifecycle_passed=primary_failure is None,
            cleanup_passed=cleanup_failure is None,
            test_root=str(paths.root),
        )
        return 1

    emit(
        "lifecycle_test_complete",
        lifecycle_passed=True,
        cleanup_passed=True,
        browser_pid=expected_browser_pid,
        cdp_port=port,
        marker=marker,
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--worker",
        choices=("seed", "reattach"),
        help="Internal worker mode used by the parent lifecycle check.",
    )
    parser.add_argument("--test-root", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--port", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--marker", help=argparse.SUPPRESS)
    parser.add_argument("--expected-browser-pid", type=int, help=argparse.SUPPRESS)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        if args.worker:
            return _worker_main(args)
        if any(
            value is not None
            for value in (
                args.test_root,
                args.port,
                args.marker,
                args.expected_browser_pid,
            )
        ):
            raise RuntimeError("Worker-only arguments require --worker.")
        return _parent_main()
    except BaseException as exc:
        emit(
            "fatal_error",
            status="error",
            error_type=type(exc).__name__,
            error=str(exc),
            traceback=traceback.format_exc(),
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
