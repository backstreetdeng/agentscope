"""Build a deterministic ZIP distribution and SHA256 checksum."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
ARCHIVE = DIST / "china-passenger-vehicle-month-skill-0.1.0.zip"


def include(path: Path) -> bool:
    if not path.is_file():
        return False
    relative = path.relative_to(ROOT)
    if relative.parts[0] == "dist":
        return False
    if "__pycache__" in relative.parts or path.suffix == ".pyc":
        return False
    return True


def main() -> None:
    DIST.mkdir(parents=True, exist_ok=True)
    files = sorted((path for path in ROOT.rglob("*") if include(path)), key=lambda path: path.as_posix())
    with ZipFile(ARCHIVE, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            relative = Path("month-skill") / path.relative_to(ROOT)
            info = ZipInfo(relative.as_posix(), date_time=(2026, 7, 21, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())

    digest = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    checksum_path = ARCHIVE.with_suffix(ARCHIVE.suffix + ".sha256")
    checksum_path.write_text(f"{digest}  {ARCHIVE.name}\n", encoding="ascii")
    print(
        json.dumps(
            {
                "archive": str(ARCHIVE),
                "files": len(files),
                "bytes": ARCHIVE.stat().st_size,
                "sha256": digest,
                "checksum": str(checksum_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
