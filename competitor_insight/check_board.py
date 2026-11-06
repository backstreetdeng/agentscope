"""竞品洞察任务制只读一致性检查（三方校验 + 协议约束 + 任务级隔离）。

用途：校验「任务总表 tasks/tasks.md ↔ 全局看板 BOARD.md ↔ 各 TASK.md 状态块」
逐项一致，并核对证据目录，防止看板漂移、"各自为战"和"只写已验证、没有证据路径"。
只读，不修改任何文件，不访问网络和服务。

运行（项目根目录）：
    ../Scripts/python.exe -B competitor_insight/check_board.py
    ../Scripts/python.exe -B competitor_insight/check_board.py --freeze BCI-005   # 建立冻结基线

检查项
1. tasks/tasks.md、BOARD.md、HANDOFF.md、tasks/ 结构存在；
2. 每个 tasks/BCI-NNN/TASK.md 有可解析状态块，必填字段齐全；
3. 阶段与 blocked 取值合法、updated 为 YYYY-MM-DD、task_id 与目录名一致；
4. blocked=yes 时 blocker 非空，且必须出现在 BOARD 的 BLOCKED 栏；
5. evidence 目录在磁盘存在并含 manifest.json（值为 none 时跳过）；
6. 三维一致：tasks.md、BOARD 对应阶段栏、TASK.md 的
   标题/阶段/负责人/更新时间/下一步逐字一致；
7. 编号双向一致：三处出现且仅出现在已登记任务中；
8. 任务只出现在与其 stage 对应的 BOARD 分栏，不重复出现；
9. 协议契约：config/bci_protocol.json 每条约束的 reader 符号必须存在、
   verify 命令必须真执行且返回 0；禁止 echo ok / exit 0 这类敷衍命令；
10. 任务级隔离：状态块声明 frozen_paths 时，冻结文件不得被改动
    （Git 已跟踪文件比工作区差异，未跟踪文件比 sha256 基线）；
11. 端口占用：声明 port 的非终态任务之间不得重复占用同一端口。

兼容策略：owner 为必填；port 与 frozen_paths 为可选字段。
存量 TASK.md 未写这两项时按「未声明 = 不限制」处理，不判 FAIL。

输出统一带三态与计数（第 5 条）：
    status: success | partial | failed
    counts: 应查 N / 实查 M / 命中 K
partial 表示有检查因前置条件缺失未执行，会单列未覆盖原因，不得当作 0 命中。

退出码：0 通过；1 有不合格项；2 结构缺失（目录或索引文件不存在）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
TASKS_DIR = ROOT / "tasks"
TASKS_INDEX = TASKS_DIR / "tasks.md"
BOARD = ROOT / "BOARD.md"
HANDOFF = ROOT / "HANDOFF.md"
PROTOCOL = ROOT / "config" / "bci_protocol.json"

STAGES = {
    "CREATED": "创建",
    "EXECUTING": "执行中",
    "DEV_DONE": "开发完成（待验证）",
    "QA": "质量验证",
    "TESTED": "测试通过（待上线）",
    "LIVE": "已上线",
}
ACTIVE_STAGES = ("CREATED", "EXECUTING", "QA")
REQUIRED = ("task_id", "title", "stage", "owner", "updated", "blocked", "next", "evidence")
OPTIONAL = ("port", "frozen_paths")
PROTOCOL_REQUIRED = ("id", "statement", "reader", "verify")
FAKE_VERIFY_RE = re.compile(r"(echo\s+ok\b|\bexit\s+0\b|(-c\s+[\"']?pass\b))", re.I)
TASK_ID_RE = re.compile(r"^BCI-\d{3}$")
TASK_ID_IN_TEXT_RE = re.compile(r"BCI-\d{3}")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FENCE_RE = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.S)
SEPARATOR_RE = re.compile(r"^[\s:\-|]+$")


class Tally:
    """统一记录检查数量与结论，保证输出带三态和计数。"""

    def __init__(self) -> None:
        self.planned = 0
        self.run = 0
        self.findings: list[str] = []
        self.skipped: list[str] = []

    def check(self, cond: bool, message: str) -> bool:
        self.planned += 1
        self.run += 1
        if not cond:
            self.findings.append(message)
        return cond

    def skip(self, reason: str) -> None:
        self.planned += 1
        self.skipped.append(reason)

    @property
    def status(self) -> str:
        if self.findings:
            return "failed"
        if self.skipped:
            return "partial"
        return "success"


def parse_state(text: str) -> dict[str, str]:
    """取首个含 task_id 的代码块，按 key: value 解析为状态字典。"""
    for block in FENCE_RE.findall(text):
        if "task_id:" not in block:
            continue
        state: dict[str, str] = {}
        for line in block.splitlines():
            if ":" not in line or line.lstrip().startswith("#"):
                continue
            key, _, value = line.partition(":")
            state[key.strip()] = value.strip()
        return state
    return {}


def split_row(line: str) -> list[str] | None:
    """把一个 Markdown 表格行拆成单元格；不是数据行时返回 None。"""
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    if not cells or SEPARATOR_RE.match("|".join(cells)):
        return None
    return cells


def index_rows(text: str) -> list[dict[str, str]]:
    """解析 tasks/tasks.md 总表。"""
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        cells = split_row(line)
        if not cells or len(cells) < 6:
            continue
        match = TASK_ID_IN_TEXT_RE.search(cells[0])
        if not match:
            continue
        rows.append({
            "task_id": match.group(0),
            "title": cells[1],
            "stage": cells[2],
            "owner": cells[3],
            "updated": cells[4],
            "next": cells[5],
        })
    return rows


def board_sections(text: str) -> dict[str, list[list[str]]]:
    """只解析「分阶段看板」一节，返回 {阶段代码: [表格行单元格, ...]}。"""
    if "## 分阶段看板" not in text:
        return {}
    body = text.split("## 分阶段看板", 1)[1]
    body = re.split(r"\n## ", body, 1)[0]
    sections: dict[str, list[list[str]]] = {}
    current: str | None = None
    for line in body.splitlines():
        heading = re.match(r"^###\s.*?[（(]([A-Z_]+)[)）]\s*$", line.strip())
        if heading:
            current = heading.group(1)
            sections.setdefault(current, [])
            continue
        if not current:
            continue
        cells = split_row(line)
        if cells and len(cells) >= 5 and TASK_ID_IN_TEXT_RE.search(cells[0]):
            sections[current].append(cells)
    return sections


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(*args: str) -> tuple[int, str]:
    try:
        result = subprocess.run(
            ["git", *args], cwd=PROJECT, capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, str(exc)
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def parse_frozen_paths(raw: str) -> list[str]:
    """把 frozen_paths 解析为路径列表；none/空 表示不限制（兼容存量任务）。"""
    value = (raw or "").strip()
    if not value or value.lower() in ("none", "无", "-"):
        return []
    return [item.strip() for item in re.split(r"[,，;；]", value) if item.strip()]


def normalize_reader(reader: str) -> tuple[str, str] | None:
    """把 'path:symbol' 拆成 (path, symbol)；Windows 盘符不算分隔符。"""
    value = reader.strip()
    if not value:
        return None
    if re.match(r"^[A-Za-z]:[\\/]", value):
        return None
    if ":" not in value:
        return None
    path, _, symbol = value.rpartition(":")
    if not path.strip() or not symbol.strip():
        return None
    return path.strip(), symbol.strip()


def run_verify(command: object) -> tuple[bool, str]:
    """执行 verify 命令；返回 (是否通过, 摘要)。命令中的 {python} 替换为当前解释器。"""
    if isinstance(command, str):
        argv = shlex.split(command, posix=False)
    elif isinstance(command, list):
        argv = [str(item) for item in command]
    else:
        return False, "verify 必须是字符串或数组"
    if not argv:
        return False, "verify 为空"
    argv = [sys.executable if item == "{python}" else item for item in argv]
    if any("check_board.py" in item for item in argv):
        return False, "verify 不允许调用 check_board.py 自身（会递归）"
    if FAKE_VERIFY_RE.search(command if isinstance(command, str) else " ".join(argv)):
        return False, "verify 含敷衍项（echo ok / exit 0 / -c pass），必须真断言"
    try:
        result = subprocess.run(
            argv, cwd=PROJECT, capture_output=True, text=True, timeout=180,
            encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        return False, "verify 超时（180s）"
    except OSError as exc:
        return False, f"verify 无法执行：{exc}"
    if result.returncode == 0:
        return True, ""
    detail = ((result.stdout or "") + (result.stderr or "")).strip().splitlines()
    tail = " / ".join(detail[-3:]) if detail else "无输出"
    return False, f"verify 退出码 {result.returncode}：{tail}"


def check_protocol(t: Tally) -> None:
    """第 1 条：协议契约的 reader 与 verify 都必须成立。"""
    if not PROTOCOL.is_file():
        t.check(False, f"缺少协议文件 {PROTOCOL.relative_to(PROJECT)}（机制未启用）")
        return
    try:
        data = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        t.check(False, f"协议文件不是合法 JSON：{exc}")
        return
    t.check(isinstance(data.get("version"), int), "协议文件缺少整数 version")
    constraints = data.get("constraints")
    if not t.check(isinstance(constraints, list) and bool(constraints), "协议文件缺少非空 constraints"):
        return

    seen: set[str] = set()
    for item in constraints:
        if not isinstance(item, dict):
            t.check(False, "constraints 中存在非对象条目")
            continue
        cid = str(item.get("id", "")).strip() or "?"
        missing = [key for key in PROTOCOL_REQUIRED if not str(item.get(key) or "").strip()]
        if not t.check(not missing, f"约束 {cid} 缺少字段 {', '.join(missing)}"):
            continue
        t.check(cid not in seen, f"约束 id 重复：{cid}")
        seen.add(cid)

        parsed = normalize_reader(str(item["reader"]))
        if not t.check(parsed is not None, f"约束 {cid} 的 reader 不是 path:symbol 形式：{item['reader']}"):
            continue
        reader_path, symbol = parsed
        target = PROJECT / reader_path
        if not t.check(target.is_file(), f"约束 {cid} 的 reader 文件不存在：{reader_path}"):
            continue
        source = target.read_text(encoding="utf-8", errors="replace")
        t.check(re.search(rf"\b{re.escape(symbol)}\b", source) is not None,
                f"约束 {cid} 的 reader 符号 {symbol} 在 {reader_path} 中不存在（文档有开关、代码无读者）")

        passed, detail = run_verify(item["verify"])
        t.check(passed, f"约束 {cid} 的 verify 未通过：{detail}")


def freeze_baselines(task_ids: list[str]) -> int:
    """为声明了 frozen_paths 的任务写入 sha256 基线。"""
    written = 0
    for task_id in task_ids:
        task_file = TASKS_DIR / task_id / "TASK.md"
        if not task_file.is_file():
            print(f"FAIL: 找不到 {task_id}/TASK.md")
            return 1
        state = parse_state(task_file.read_text(encoding="utf-8"))
        paths = parse_frozen_paths(state.get("frozen_paths", ""))
        if not paths:
            print(f"{task_id}: 未声明 frozen_paths，无需冻结")
            continue
        lines = []
        for rel in paths:
            target = PROJECT / rel
            if not target.is_file():
                print(f"FAIL: {task_id} 冻结路径不存在 -> {rel}")
                return 1
            lines.append(f"{sha256_of(target)}\t{rel}")
        (TASKS_DIR / task_id / "frozen.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
        written += 1
        print(f"{task_id}: 已写入 {len(lines)} 条冻结基线 -> tasks/{task_id}/frozen.sha256")
    print(f"status: success\ncounts: 应查 {len(task_ids)} / 实查 {len(task_ids)} / 命中 0")
    return 0


def check_frozen(t: Tally, task_id: str, task_dir: Path, raw: str) -> None:
    """第 6 条：冻结路径不得被改动；未声明按不限制处理。"""
    paths = parse_frozen_paths(raw)
    if not paths:
        return
    git_ok, _ = git("rev-parse", "--is-inside-work-tree")
    if git_ok != 0:
        t.skip(f"{task_id}: git 不可用，跳过 frozen_paths 的 Git 侧比对")
    baseline_file = task_dir / "frozen.sha256"
    baseline: dict[str, str] = {}
    if baseline_file.is_file():
        for line in baseline_file.read_text(encoding="utf-8").splitlines():
            if "\t" in line:
                digest, rel = line.split("\t", 1)
                baseline[rel.strip()] = digest.strip()
    for rel in paths:
        target = PROJECT / rel
        if not t.check(target.is_file(), f"{task_id}: 冻结路径不存在 -> {rel}"):
            continue
        tracked = git_ok == 0 and git("ls-files", "--error-unmatch", rel)[0] == 0
        if tracked:
            changed = git("status", "--porcelain", "--", rel)[1].strip()
            t.check(not changed, f"{task_id}: 冻结文件被改动（Git）-> {rel}")
        elif not t.check(baseline_file.is_file(),
                         f"{task_id}: 冻结路径未纳入 Git 且缺少基线，先运行 --freeze {task_id}"):
            continue
        elif not t.check(rel in baseline, f"{task_id}: 基线中缺少 {rel}，重新运行 --freeze {task_id}"):
            continue
        else:
            t.check(sha256_of(target) == baseline[rel], f"{task_id}: 冻结文件被改动（sha256）-> {rel}")


def check_port(t: Tally, task_id: str, state: dict[str, str]) -> None:
    """第 6 条：port 为可选字段；声明后必须是整数。"""
    raw = (state.get("port") or "").strip()
    if not raw or raw.lower() in ("none", "无", "-"):
        return
    t.check(raw.isdigit(), f"{task_id}: port 必须是整数或 none，当前 {raw!r}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="竞品洞察任务制一致性检查")
    parser.add_argument("--freeze", action="append", default=[], metavar="TASK_ID",
                        help="为声明 frozen_paths 的任务写入 sha256 基线")
    args = parser.parse_args(argv)

    if args.freeze:
        return freeze_baselines(args.freeze)

    t = Tally()

    # —— 1. 结构 ——
    t.check(TASKS_DIR.is_dir(), "缺少 tasks/ 目录")
    t.check(TASKS_INDEX.is_file(), "缺少 tasks/tasks.md")
    t.check(BOARD.is_file(), "缺少 BOARD.md")
    t.check(HANDOFF.is_file(), "缺少 HANDOFF.md")
    if t.findings:
        print("status: failed\ncounts: 应查 4 / 实查 4 / 命中 %d" % len(t.findings))
        print("FAIL:")
        for item in t.findings:
            print("  - " + item)
        return 2

    board_text = BOARD.read_text(encoding="utf-8")
    sections = board_sections(board_text)
    handoff_text = HANDOFF.read_text(encoding="utf-8")
    index_text = TASKS_INDEX.read_text(encoding="utf-8")

    # —— 2. 各 TASK.md 状态块 ——
    states: dict[str, dict[str, str]] = {}
    task_dirs: dict[str, Path] = {}
    for task_dir in sorted(p for p in TASKS_DIR.iterdir() if p.is_dir()):
        if task_dir.name.startswith("_"):
            continue
        task_file = task_dir / "TASK.md"
        if not t.check(task_file.is_file(), f"{task_dir.name}: 缺少 TASK.md"):
            continue
        if not TASK_ID_RE.match(task_dir.name):
            t.check(False, f"{task_dir.name}: 目录名不符合 BCI-NNN")
        state = parse_state(task_file.read_text(encoding="utf-8"))
        if not t.check(bool(state), f"{task_dir.name}: 未找到状态块（首个含 task_id 的代码块）"):
            continue
        states[task_dir.name] = state
        task_dirs[task_dir.name] = task_dir

        missing = [key for key in REQUIRED if not state.get(key)]
        if not t.check(not missing, f"{task_dir.name}: 状态块缺少字段 {', '.join(missing)}"):
            continue
        t.check(state["task_id"] == task_dir.name,
                f"{task_dir.name}: task_id={state['task_id']} 与目录名不一致")
        t.check(state["stage"] in STAGES,
                f"{task_dir.name}: 非法 stage={state['stage']}，允许 {', '.join(STAGES)}")
        t.check(state["blocked"].lower() in ("yes", "no"),
                f"{task_dir.name}: blocked 只能为 yes/no，当前 {state['blocked']}")
        t.check(bool(DATE_RE.match(state["updated"])),
                f"{task_dir.name}: updated 需为 YYYY-MM-DD，当前 {state['updated']}")
        blocked = state["blocked"].lower() == "yes"
        if blocked:
            t.check(bool(state.get("blocker")), f"{task_dir.name}: blocked=yes 但缺少 blocker 字段")

        evidence = state["evidence"]
        if evidence.lower() != "none":
            target = (PROJECT / evidence.rstrip("/")) if not Path(evidence).is_absolute() else Path(evidence)
            if t.check(target.is_dir(), f"{task_dir.name}: evidence 目录不存在 -> {evidence}"):
                t.check((target / "manifest.json").is_file(),
                        f"{task_dir.name}: evidence 目录缺少 manifest.json -> {evidence}")

        check_port(t, task_dir.name, state)
        check_frozen(t, task_dir.name, task_dir, state.get("frozen_paths", ""))

    # —— 3. tasks/tasks.md 总表 ——
    index_rows_list = index_rows(index_text)
    t.check(bool(index_rows_list), "tasks.md 未解析到任何任务行")
    index_map: dict[str, dict[str, str]] = {}
    for row in index_rows_list:
        t.check(row["task_id"] not in index_map, f"tasks.md: {row['task_id']} 出现多行，只允许一行")
        index_map[row["task_id"]] = row

    # —— 4. BOARD 分阶段看板 ——
    board_map: dict[str, tuple[str, list[str]]] = {}
    for stage, rows in sections.items():
        for cells in rows:
            task_id = TASK_ID_IN_TEXT_RE.search(cells[0]).group(0)
            t.check(task_id not in board_map, f"BOARD: {task_id} 在分阶段看板出现多次")
            board_map[task_id] = (stage, cells)

    for stage in STAGES:
        t.check(stage in sections, f"BOARD 分阶段看板缺少 {stage} 栏")

    def compare(task_id: str, field: str, expected: str, actual: str, where: str) -> None:
        t.check(expected == actual,
                f"{task_id}: {where} 的 {field} 与 TASK.md 不一致（TASK={expected!r} / {where}={actual!r}）")

    for task_id, state in states.items():
        if state.get("stage") not in STAGES or not state.get("title"):
            continue
        row = index_map.get(task_id)
        if not t.check(row is not None, f"{task_id}: tasks.md 总表缺少该任务"):
            pass
        else:
            compare(task_id, "标题", state["title"], row["title"], "tasks.md")
            compare(task_id, "阶段", state["stage"], row["stage"], "tasks.md")
            compare(task_id, "负责人", state["owner"], row["owner"], "tasks.md")
            compare(task_id, "更新时间", state["updated"], row["updated"], "tasks.md")
            compare(task_id, "下一步", state["next"], row["next"], "tasks.md")

        entry = board_map.get(task_id)
        if not t.check(entry is not None, f"{task_id}: BOARD.md 分阶段看板缺少该任务"):
            continue
        board_stage, cells = entry
        t.check(board_stage == state["stage"],
                f"{task_id}: BOARD 放在 {board_stage} 栏，但 TASK.md stage={state['stage']}")
        if len(cells) >= 5:
            compare(task_id, "标题", state["title"], cells[1], "BOARD")
            compare(task_id, "负责人", state["owner"], cells[2], "BOARD")
            compare(task_id, "下一步", state["next"], cells[3], "BOARD")
            compare(task_id, "更新时间", state["updated"], cells[4], "BOARD")
        blocked = state["blocked"].lower() == "yes"
        in_blocked = any(
            TASK_ID_IN_TEXT_RE.search(c[0]) and TASK_ID_IN_TEXT_RE.search(c[0]).group(0) == task_id
            for c in sections.get("BLOCKED", [])
        )
        t.check(not (blocked and not in_blocked), f"{task_id}: 已标记阻塞但未出现在 BLOCKED 栏")
        t.check(not ((not blocked) and in_blocked), f"{task_id}: blocked=no 但仍留在 BLOCKED 栏")

    index_ids = set(index_map)
    board_ids = set(board_map)
    for extra in sorted(index_ids - set(states)):
        t.check(False, f"tasks.md 引用了不存在的任务：{extra}")
    for extra in sorted(board_ids - set(states)):
        t.check(False, f"BOARD 引用了不存在的任务：{extra}")
    for absent in sorted(set(states) - index_ids):
        t.check(False, f"{absent}: 未出现在 tasks/tasks.md")
    for absent in sorted(set(states) - board_ids):
        t.check(False, f"{absent}: 未出现在 BOARD.md 分阶段看板")

    handoff_ids = set(TASK_ID_IN_TEXT_RE.findall(handoff_text))
    for extra in sorted(handoff_ids - set(states)):
        t.check(False, f"HANDOFF 引用了不存在的任务：{extra}")

    # —— 5. 端口占用（非终态任务之间） ——
    ports: dict[str, str] = {}
    for task_id, state in states.items():
        raw = (state.get("port") or "").strip()
        if state.get("stage") not in ACTIVE_STAGES or not raw or raw.lower() == "none":
            continue
        if raw in ports:
            t.check(False, f"{task_id}: 端口 {raw} 已被 {ports[raw]} 占用（两者均未终态）")
        ports[raw] = task_id

    # —— 6. 协议契约 + verify ——
    check_protocol(t)

    # —— 输出 ——
    print(f"任务数: {len(states)}；tasks.md 行: {len(index_rows_list)}；BOARD 分栏: {', '.join(sorted(sections))}")
    for task_id, state in states.items():
        flag = " [BLOCKED]" if state["blocked"].lower() == "yes" else ""
        print(f"  {task_id}  {state['stage']:<9}{flag}  {state['title']}  (owner={state['owner']}, next={state['next'][:40]})")
    print(f"status: {t.status}")
    print(f"counts: 应查 {t.planned} / 实查 {t.run} / 命中 {len(t.findings)}")
    if t.skipped:
        print("未覆盖（不代表 0 命中）:")
        for item in t.skipped:
            print("  - " + item)
    if t.findings:
        print("\nFAIL:")
        for item in t.findings:
            print("  - " + item)
        return 1
    print("\nPASS: tasks.md、BOARD.md、各 TASK.md 三方一致；协议约束的 reader/verify 均成立；冻结路径与端口无冲突。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
