"""竞品洞察 · 协议约束真断言脚本（BCI-005 第 1 条）。

用途：被 check_board.py 按 config/bci_protocol.json 的 `verify` 调用，对每条约束做
可执行断言。只读，不修改文件、不访问网络、不启动服务。

运行（项目根目录）：
    ../Scripts/python.exe -B competitor_insight/config/verify/verify_constraints.py --check TPL-SOURCE

    --check ID    必选，对应 bci_protocol.json 的约束 id
    --root PATH   可选，项目根目录；默认按本文件位置推算，用于反向验证时指向临时副本

输出约定（对所有调用方一致）：
    status: success | partial | failed
    counts: 应查 N / 实查 M / 命中 K
- failed 表示断言未通过，退出码 1；
- partial 表示有断言因前置条件缺失而未执行，必须打印未覆盖原因，不得当作 0 命中；
- success 退出码 0；用法错误退出码 2。

反向验证方法：复制 competitor_insight/{web,templates} 到临时目录，破坏其中一处，
再用 --root 指向临时目录运行，应返回 failed。不要为验证去改真实业务文件。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

COMMIT_STAGES = ("TESTED", "LIVE")


class Checker:
    def __init__(self, name: str, root: Path) -> None:
        self.name = name
        self.root = root
        self.ci = root / "competitor_insight"
        self.planned = 0
        self.run = 0
        self.failures: list[str] = []
        self.skipped: list[str] = []
        self.notes: list[str] = []

    def expect(self, cond: bool, message: str) -> bool:
        self.planned += 1
        self.run += 1
        if not cond:
            self.failures.append(message)
        # 返回断言结果，调用方才能用 `if not checker.expect(...): continue` 提前终止；
        # 早期版本返回 None 会让该写法恒为真，导致后续断言被静默跳过（恒通过）。
        return bool(cond)

    def skip(self, reason: str) -> None:
        self.planned += 1
        self.skipped.append(reason)

    @property
    def status(self) -> str:
        if self.failures:
            return "failed"
        if self.skipped:
            return "partial"
        return "success"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _function_body(source: str, name: str) -> str:
    """按大括号配对取 `function <name>(...) {...}` 的函数体；找不到返回空串。"""
    marker = f"function {name}"
    index = source.find(marker)
    if index < 0:
        return ""
    start = source.find("{", index)
    if start < 0:
        return ""
    depth = 0
    for pos in range(start, len(source)):
        char = source[pos]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start:pos + 1]
    return ""


def _manifest(checker: Checker) -> dict | None:
    path = checker.ci / "web" / "templates.json"
    checker.expect(path.is_file(), f"缺少模板清单 {path}")
    if not path.is_file():
        return None
    try:
        data = json.loads(_read(path))
    except json.JSONDecodeError as exc:
        checker.expect(False, f"templates.json 不是合法 JSON：{exc}")
        return None
    checker.expect(isinstance(data.get("templates"), list) and bool(data["templates"]),
                   "templates.json 缺少非空 templates 数组")
    return data


def check_tpl_source(checker: Checker) -> None:
    """模板下拉的唯一来源是 web/templates.json，bci.js 不得内联模板 id。"""
    js_path = checker.ci / "web" / "bci.js"
    checker.expect(js_path.is_file(), f"缺少前端脚本 {js_path}")
    if not js_path.is_file():
        return
    source = _read(js_path)
    checker.expect("function loadTemplates" in source, "bci.js 缺少 loadTemplates")
    checker.expect("function templateOptionsFrom" in source, "bci.js 缺少 templateOptionsFrom")
    checker.expect("fetch(group.templatesUrl" in source,
                   "bci.js 未通过 group.templatesUrl 运行时加载清单（疑似写死）")
    manifest = _manifest(checker)
    if not manifest:
        return
    ids = [item.get("id", "") for item in manifest["templates"] if isinstance(item, dict)]
    checker.expect(len(ids) == len(set(ids)), f"templates.json 存在重复 id：{ids}")
    for item in manifest["templates"]:
        if not isinstance(item, dict):
            continue
        status = item.get("status")
        checker.expect(status in ("ready", "pending"), f"模板 {item.get('id')} status 非法：{status!r}")
        if status == "pending":
            checker.expect(bool(str(item.get("reason", "")).strip()),
                           f"pending 模板 {item.get('id')} 缺少 reason")
        if status == "ready":
            checker.expect(bool(item.get("definition")),
                           f"ready 模板 {item.get('id')} 缺少 definition")
        if item.get("id"):
            checker.expect(item["id"] not in source,
                           f"bci.js 内联了模板 id {item['id']}，违反清单唯一来源")


def check_tpl_ready(checker: Checker) -> None:
    """ready 模板的定义文件必须存在、可解析，且 note 声明的维度数与实际一致。"""
    manifest = _manifest(checker)
    if not manifest:
        return
    for item in manifest["templates"]:
        if not isinstance(item, dict) or item.get("status") != "ready":
            continue
        tid = item.get("id", "?")
        definition = str(item.get("definition", ""))
        path = checker.root / definition if definition else None
        checker.expect(bool(path and path.is_file()), f"模板 {tid} 的 definition 不存在：{definition}")
        if not (path and path.is_file()):
            continue
        try:
            template = json.loads(_read(path))
        except json.JSONDecodeError as exc:
            checker.expect(False, f"模板 {tid} 定义不是合法 JSON：{exc}")
            continue
        groups = template.get("groups") or []
        dims = template.get("dimensions") or []
        checker.expect(bool(groups), f"模板 {tid} 缺少 groups")
        checker.expect(bool(dims), f"模板 {tid} 缺少 dimensions")
        group_ids = {g.get("id") for g in groups if isinstance(g, dict)}
        dim_ids = [d.get("id") for d in dims if isinstance(d, dict)]
        checker.expect(len(dim_ids) == len(set(dim_ids)), f"模板 {tid} 维度 id 不唯一")
        dangling = [d.get("id") for d in dims
                    if isinstance(d, dict) and d.get("group") not in group_ids]
        checker.expect(not dangling, f"模板 {tid} 维度引用了不存在的分组：{dangling}")
        note = str(item.get("note", ""))
        declared = re.search(r"(\d+)\s*维", note)
        checker.expect(bool(declared), f"模板 {tid} 的 note 未声明维度数：{note!r}")
        if declared:
            checker.expect(int(declared.group(1)) == len(dims),
                           f"模板 {tid} 声明 {declared.group(1)} 维，实际 {len(dims)} 维")
        checker.expect(len(groups) >= 8, f"模板 {tid} 分组数异常偏少：{len(groups)}")


def check_scope_persist(checker: Checker) -> None:
    """口径选择必须写入 localStorage['bci.scope'] 并广播事件。"""
    js_path = checker.ci / "web" / "bci.js"
    checker.expect(js_path.is_file(), f"缺少前端脚本 {js_path}")
    if not js_path.is_file():
        return
    source = _read(js_path)
    checker.expect(bool(re.search(r"STORAGE_KEY\s*=\s*'bci\.scope'", source)),
                   "bci.js 未把 STORAGE_KEY 固定为 'bci.scope'")
    body = _function_body(source, "persist")
    checker.expect(bool(body), "bci.js 缺少 persist 函数")
    if body:
        checker.expect("localStorage.setItem(STORAGE_KEY" in body,
                       "persist 未写入 localStorage[STORAGE_KEY]")
        checker.expect("bci:scope-applied" in body, "persist 未派发 bci:scope-applied")
        checker.expect("window.BCI_SCOPE" in body, "persist 未暴露 window.BCI_SCOPE")
    restore = _function_body(source, "restore")
    checker.expect(bool(restore), "bci.js 缺少 restore 函数")
    if restore:
        checker.expect("localStorage.getItem(STORAGE_KEY" in restore,
                       "restore 未读取 localStorage[STORAGE_KEY]")


def check_scope_keys(checker: Checker) -> None:
    """bci.scope 结构必须包含 version 与四类 datasources 键。"""
    js_path = checker.ci / "web" / "bci.js"
    checker.expect(js_path.is_file(), f"缺少前端脚本 {js_path}")
    if not js_path.is_file():
        return
    body = _function_body(_read(js_path), "buildScope")
    checker.expect(bool(body), "bci.js 缺少 buildScope 函数")
    if not body:
        return
    checker.expect("version" in body, "buildScope 未输出 version")
    for key in ("quant_structured", "interview_parsed", "insight_template", "flow_data"):
        checker.expect(key in body, f"buildScope 缺少 datasources.{key}")


def check_task_committed(checker: Checker) -> None:
    """TESTED/LIVE 任务的 commit_paths 必须已入库；未跟踪同样算未入库。

    判定方式：对每个处于 TESTED/LIVE 的任务，取其状态块声明的 commit_paths，
    在仓库根执行 `git status --porcelain -- <paths>`；有任何输出即未入库。
    LIVE 追加检查是否有未推送提交（无上游也判失败）。
    """
    tasks_dir = checker.ci / "tasks"
    checker.expect(tasks_dir.is_dir(), f"缺少任务目录 {tasks_dir}")
    if not tasks_dir.is_dir():
        return
    checked = 0
    for task_dir in sorted(p for p in tasks_dir.iterdir() if p.is_dir()):
        if task_dir.name.startswith("_") or not re.match(r"^BCI-\d{3}$", task_dir.name):
            continue
        task_file = task_dir / "TASK.md"
        if not task_file.is_file():
            continue
        state = _state_block(_read(task_file))
        stage = state.get("stage", "")
        if stage not in COMMIT_STAGES:
            continue
        checked += 1
        task_id = state.get("task_id", task_dir.name)
        raw = state.get("commit_paths", "")
        paths = [p.strip() for p in re.split(r"[,，;；]", raw) if p.strip()]
        if raw.strip().lower() in ("none", "无", "-"):
            paths = []
        if not checker.expect(bool(paths), f"{task_id}: {stage} 任务未声明 commit_paths，无法判定入库"):
            continue
        rc, out = _git(checker.root, "status", "--porcelain", "--", *paths)
        if not checker.expect(rc == 0, f"{task_id}: git status 执行失败：{out.strip()[:120]}"):
            continue
        lines = [line for line in out.splitlines() if line.strip()]
        checker.expect(not lines,
                       f"{task_id}: {len(lines)} 处文件未入库（{stage} 前必须本地提交），"
                       f"例如：{'; '.join(lines[:3])}")
        if stage == "LIVE":
            rc, ahead = _git(checker.root, "rev-list", "--count", "@{u}..HEAD")
            checker.expect(rc == 0, f"{task_id}: LIVE 任务无法确认远程上游，不能判定已推送")
            if rc == 0:
                checker.expect(ahead.strip() == "0",
                               f"{task_id}: LIVE 任务有 {ahead.strip()} 个提交未推送远程")
    if not checked:
        checker.skip("没有处于 TESTED/LIVE 的任务，TASK-COMMITTED 未覆盖任何任务")


def _state_block(text: str) -> dict[str, str]:
    """取首个含 task_id 的代码块，按 key: value 解析。"""
    for block in re.findall(r"```[a-zA-Z]*\n(.*?)```", text, re.S):
        if "task_id:" not in block:
            continue
        state: dict[str, str] = {}
        for line in block.splitlines():
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            state[key.strip()] = value.strip()
        return state
    return {}


def _git(root: Path, *args: str) -> tuple[int, str]:
    try:
        result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                                timeout=60, encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, str(exc)
    return result.returncode, (result.stdout or "") + (result.stderr or "")


CHECKS = {
    "TPL-SOURCE": check_tpl_source,
    "TPL-READY": check_tpl_ready,
    "SCOPE-PERSIST": check_scope_persist,
    "SCOPE-KEYS": check_scope_keys,
    "TASK-COMMITTED": check_task_committed,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="竞品洞察协议约束真断言")
    parser.add_argument("--check", required=True, choices=sorted(CHECKS))
    parser.add_argument("--root", default=None, help="项目根目录，默认按脚本位置推算")
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[3]
    checker = Checker(args.check, root)
    CHECKS[args.check](checker)

    print(f"check: {checker.name}")
    print(f"status: {checker.status}")
    print(f"counts: 应查 {checker.planned} / 实查 {checker.run} / 命中 {len(checker.failures)}")
    for note in checker.notes:
        print(f"note: {note}")
    if checker.failures:
        print("FAIL:")
        for item in checker.failures:
            print("  - " + item)
        return 1
    if checker.skipped:
        print("未覆盖（不代表 0 命中）:")
        for item in checker.skipped:
            print("  - " + item)
        return 0
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
