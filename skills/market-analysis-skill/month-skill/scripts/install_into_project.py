"""Safely merge the monthly Skill payload into an AgentScope project."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD_ROOT = ROOT / "payload"
PROFILE_ROOT = ROOT / "profiles" / "passenger_vehicle_monthly"
CONFIG_EXAMPLE = ROOT / "config" / "market_analysis.example.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_install_files(target: Path) -> list[tuple[Path, Path]]:
    files: list[tuple[Path, Path]] = []
    for source in PAYLOAD_ROOT.rglob("*"):
        if source.is_file() and "__pycache__" not in source.parts and source.suffix != ".pyc":
            files.append((source, target / source.relative_to(PAYLOAD_ROOT)))

    profile_target = target / "skills" / "market_analysis_skill" / "profiles" / "passenger_vehicle_monthly"
    for source in PROFILE_ROOT.rglob("*"):
        if source.is_file() and "__pycache__" not in source.parts:
            files.append((source, profile_target / source.relative_to(PROFILE_ROOT)))

    files.append((CONFIG_EXAMPLE, target / "model_config" / "market_analysis.skill.example.json"))
    return sorted(files, key=lambda item: str(item[1]).lower())


def main() -> int:
    parser = argparse.ArgumentParser(description="Install the monthly report Skill into a project")
    parser.add_argument("--target", required=True, help="Target AgentScope project root")
    parser.add_argument("--apply", action="store_true", help="Write files; default is dry-run")
    parser.add_argument("--force", action="store_true", help="Back up and replace conflicting files")
    args = parser.parse_args()

    target = Path(args.target).expanduser().resolve()
    if not target.is_dir():
        print(json.dumps({"ok": False, "error": f"target does not exist: {target}"}, ensure_ascii=False, indent=2))
        return 1

    host_markers = [target / "main.py", target / "app.py", target / "requirements.txt"]
    host_warning = "" if any(path.exists() for path in host_markers) else "目标目录未发现常见AgentScope工程文件。"

    install_files = iter_install_files(target)
    actions: list[dict[str, str]] = []
    conflicts: list[str] = []
    for source, destination in install_files:
        if not destination.exists():
            action = "create"
        elif sha256(source) == sha256(destination):
            action = "unchanged"
        else:
            action = "replace" if args.force else "conflict"
            if action == "conflict":
                conflicts.append(str(destination.relative_to(target)))
        actions.append(
            {
                "action": action,
                "source": str(source.relative_to(ROOT)).replace("\\", "/"),
                "target": str(destination.relative_to(target)).replace("\\", "/"),
            }
        )

    summary: dict[str, object] = {
        "ok": not conflicts or not args.apply,
        "mode": "apply" if args.apply else "dry-run",
        "target": str(target),
        "warning": host_warning,
        "conflicts": conflicts,
        "actions": actions,
    }

    if not args.apply:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    if conflicts:
        summary["error"] = "目标存在不同内容的同名文件；请先审查差异，确认后使用 --force。"
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 2

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root = target / ".market_monthly_skill_backups" / timestamp
    installed: list[str] = []
    backed_up: list[str] = []

    for source, destination in install_files:
        if destination.exists() and sha256(source) == sha256(destination):
            continue
        if destination.exists():
            backup = backup_root / destination.relative_to(target)
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(destination, backup)
            backed_up.append(str(backup.relative_to(target)).replace("\\", "/"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        installed.append(str(destination.relative_to(target)).replace("\\", "/"))

    record_path = target / "skills" / "market_analysis_skill" / "INSTALLATION.json"
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(
        json.dumps(
            {
                "skill": "china-passenger-vehicle-monthly-report",
                "version": "0.1.1",
                "installed_at": datetime.now().isoformat(timespec="seconds"),
                "source_package": str(ROOT),
                "installed_files": installed,
                "backed_up_files": backed_up,
                "next_step": "Merge model_config/market_analysis.skill.example.json into the host config manually.",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    summary.update(
        {
            "ok": True,
            "installed_count": len(installed),
            "backup_count": len(backed_up),
            "installation_record": str(record_path.relative_to(target)).replace("\\", "/"),
        }
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
