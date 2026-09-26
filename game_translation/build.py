"""Build a new game copy and read back each indexed value before publishing it."""
from collections import defaultdict
from pathlib import Path
import shutil
import tempfile

from .engines import adapter
from .project import load_project
from .storage import file_hash, safe_join, separate_directories, write_json
from .translation import approved_translations


def _verify(output, manifest, entries, tasks, approved):
    groups = defaultdict(list)
    for entry in entries:
        groups[entry["file"]].append(entry)
    engine = adapter(manifest["engine"])
    report = {"output_dir": str(output), "references": len(entries), "matched": 0,
              "missing": [], "mismatches": [], "unchanged": [],
              "warnings": manifest["warnings"], "runtime_verified": False,
              "approved_tasks": len(approved), "total_tasks": len(tasks)}
    for file, group in groups.items():
        try:
            values = engine.read(safe_join(output, file), group)
            if len(values) != len(group):
                raise ValueError("适配器返回数量与索引数量不同")
            for entry, actual in zip(group, values):
                expected = approved.get(entry["task_id"], entry["text"])
                if expected == actual:
                    report["matched"] += 1
                else:
                    report["mismatches"].append({"file": file, "path": entry["path"],
                                                 "expected": expected, "actual": actual})
                if actual == entry["text"]:
                    report["unchanged"].append(entry["entry_id"])
        except Exception as exc:
            report["missing"].append({"file": file, "reason": str(exc)})
    report["indexed_values_match"] = report["matched"] == len(entries)
    report["all_tasks_approved"] = len(approved) == len(tasks)
    return report


def verify(work_dir, output_dir):
    work, output = Path(work_dir).resolve(), Path(output_dir).resolve()
    manifest, entries, tasks = load_project(work)
    approved, _ = approved_translations(tasks, work)
    report = _verify(output, manifest, entries, tasks, approved)
    write_json(work / "verify_report.json", report)
    return report


def build(work_dir, output_dir, *, allow_partial=False, font=None, tmp_font=None):
    work, output = Path(work_dir).resolve(), Path(output_dir).resolve()
    manifest, entries, tasks = load_project(work)
    game = Path(manifest["game_dir"]).resolve()
    separate_directories(game, work)
    separate_directories(game, output)
    separate_directories(work, output)
    if output.exists():
        raise FileExistsError("输出目录已存在，请指定新目录")
    if font and tmp_font:
        raise ValueError("font 与 tmp_font 不能同时提供")
    resources = Path(manifest["resource_root"]).resolve()
    if resources != game and work not in resources.parents:
        raise ValueError("解包资源必须在当前工作目录内")
    for name, expected in manifest["source_hashes"].items():
        if file_hash(safe_join(resources, name)) != expected:
            raise ValueError(f"源资源已改变，请重新 prepare: {name}")
    info = manifest["engine"]
    archive = Path(info["archive"]).resolve() if info.get("archive") else None
    if archive and file_hash(archive) != manifest["archive_hash"]:
        raise ValueError("源归档已改变，请重新 prepare")
    approved, blocked = approved_translations(tasks, work)
    if blocked and not allow_partial:
        raise ValueError(f"{len(blocked)} 个任务未通过审核；处理后重试，或明确使用 --allow-partial")
    if not approved:
        raise ValueError("没有可写回的已审核译文")
    groups = defaultdict(list)
    for entry in entries:
        if entry["task_id"] in approved:
            groups[entry["file"]].append((entry, approved[entry["task_id"]]))
    engine = adapter(info)
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {"success": False, "output_dir": str(output), "written": 0, "blocked": blocked}
    try:
        with tempfile.TemporaryDirectory(prefix=".game-translation-build-", dir=output.parent) as directory:
            staging = Path(directory) / "game"

            def ignore_archive(folder, names):
                return [archive.name] if archive and Path(folder).resolve() == game else []

            shutil.copytree(game, staging, ignore=ignore_archive)
            if archive:
                shutil.copytree(resources, staging, dirs_exist_ok=True)
            written = sum(engine.write(safe_join(staging, name), items) for name, items in groups.items())
            report["fonts"] = engine.configure_font(staging, info, font, tmp_font)
            checks = _verify(staging, manifest, entries, tasks, approved)
            checks["output_dir"] = str(output)
            if not checks["indexed_values_match"]:
                report["verification"] = checks
                raise ValueError("写回后重新读取的文本与预期不一致；详见 build_report.json")
            # No final directory exists until all writes and readback succeed.
            if output.exists():
                raise FileExistsError("构建过程中输出目录被创建，请换新目录")
            staging.rename(output)
            report.update(success=True, written=written, verification=checks)
            write_json(work / "verify_report.json", checks)
    except Exception as exc:
        report["error"] = str(exc)
        write_json(work / "build_report.json", report)
        raise
    write_json(work / "build_report.json", report)
    return report
