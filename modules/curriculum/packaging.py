from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from .repository import CurriculumRepository

DIRECTORIES = (
    "research/long-term-map-gse-clb-2026-10-02",
    "research/long-term-map-release-2026-10-02",
    "research/long-term-map-model-review-2026-10-02",
)


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        h = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def export_release(workspace: Path, output: Path) -> dict:
    """Local complete research dependency snapshot; no uploads or publishing.

    Reject overwrite. Preserve sibling paths so source/PDF/lexicon refs work.
    Archive files and caches are omitted; raw JSON, SQLite and source code kept.
    """
    workspace = workspace.resolve(); output = output.resolve()
    source = CurriculumRepository(workspace)
    report = source.validate()
    if report["status"] != "passed":
        raise ValueError(report)
    if output.exists():
        raise FileExistsError("Release output already exists; choose a new directory")
    for directory in DIRECTORIES:
        if output.is_relative_to(workspace / directory):
            raise ValueError("Export destination cannot be inside a source directory")
    files = []
    for directory in DIRECTORIES:
        for file in sorted((workspace / directory).rglob("*")):
            if not file.is_file() or "__pycache__" in file.parts or file.suffix in {".pyc", ".zip"}:
                continue
            relative = file.relative_to(workspace)
            destination = output / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, destination)
            copied = digest(destination)
            if copied != digest(file):
                raise RuntimeError("Source changed during export: " + str(relative))
            files.append({"path": relative.as_posix(), "bytes": destination.stat().st_size, "sha256": copied})
    for file in sorted((workspace / "modules/curriculum").glob("*.py")):
        relative = file.relative_to(workspace); destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True);shutil.copy2(file, destination)
        files.append({"path": relative.as_posix(), "bytes": destination.stat().st_size, "sha256": digest(destination)})
    verification = CurriculumRepository(output).validate()
    if verification["status"] != "passed":
        raise RuntimeError(verification)
    manifest = {"schema_version": "1.0", "map_version": source.version,
                "release_scope": "local_map_and_resource_snapshot", "public_ready": False,
                "map_path": "research/long-term-map-model-review-2026-10-02/curriculum_map.json",
                "omitted": ["__pycache__", "*.pyc", "pre-existing *.zip archives"],
                "files": files, "verification": verification}
    (output / "release_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


def verify_release(output: Path) -> dict:
    output = output.resolve(); manifest = json.loads((output / "release_manifest.json").read_text())
    failures = []
    for row in manifest["files"]:
        file = (output / row["path"]).resolve()
        if not file.is_relative_to(output) or not file.is_file():
            failures.append(row["path"] + ":missing_or_unsafe")
        elif file.stat().st_size != row["bytes"] or digest(file) != row["sha256"]:
            failures.append(row["path"] + ":changed")
    report = CurriculumRepository(output).validate()
    return {"status": "failed" if failures or report["status"] != "passed" else "passed",
            "files_checked": len(manifest["files"]), "hash_failures": failures, "data": report}
