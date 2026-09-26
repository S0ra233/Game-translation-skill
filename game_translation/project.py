"""Persistent Scene/Task/Entry index, shared by the Skill and future desktop UI.

Entries describe occurrences. Tasks own mutable translation state. Scenes own
ordered task IDs. JSON dictionaries deliberately match the on-disk API.
Public operations are synchronous: callers must serialize writes to one work dir.
"""
from collections import Counter
import json
from pathlib import Path
import uuid

from .engines import adapter, detect
from .glossary import initialize
from .storage import (file_hash, load_tasks, read_file, safe_join, save_tasks,
                      separate_directories, stable_id, write_file, write_json)
from .text import protect_tags

SCHEMA_VERSION = 3


def index_entries(entries, family):
    """Core creates all identities; adapters supply only locations and grouping."""
    tasks, scenes = [], {}
    seen = set()
    for entry in entries:
        location = [family, entry["file"], entry.get("asset"), entry["path"]]
        identity = stable_id(location)
        if identity in seen:
            raise ValueError("适配器产生重复文本定位")
        seen.add(identity)
        sid = "s_" + stable_id([family, entry.get("scene", entry["file"])])
        tid = "t_" + identity
        entry.update(entry_id="e_" + identity, task_id=tid, scene_id=sid)
        scene = scenes.setdefault(sid, {"id": sid,
            "title": entry.get("scene", entry["file"]),
            "kind": entry.get("scene_kind", "database"), "task_ids": []})
        protected, codes = protect_tags(entry["text"])
        source = {"text": entry["text"], "type": entry["type"],
                  "speaker": entry.get("speaker", ""), "structure": entry.get("structure", {})}
        task = {"id": tid, "scene_id": sid, "order": len(scene["task_ids"]), **source,
                "source_hash": stable_id(source), "protected_text": protected, "codes": codes,
                "translation": "", "status": "NONE", "revision": 0}
        tasks.append(task)
        scene["task_ids"].append(tid)
    by_id = {t["id"]: t for t in tasks}
    for scene in scenes.values():
        context_hash = stable_id([scene, [by_id[t]["source_hash"] for t in scene["task_ids"]]])
        for tid in scene["task_ids"]:
            by_id[tid]["context_hash"] = context_hash
    return tasks, list(scenes.values())


def prepare(game_dir, work_dir):
    game, work = Path(game_dir).resolve(), Path(work_dir).resolve()
    separate_directories(game, work)
    previous_manifest = json.loads(read_file(work / "project.json") or "null")
    if previous_manifest:
        if previous_manifest.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("工作目录版本不兼容，请为重构版使用新的工作目录")
        if Path(previous_manifest["game_dir"]).resolve() != game:
            raise ValueError("工作目录属于另一个游戏")
    elif work.exists() and any(work.iterdir()):
        raise ValueError("工作目录非空且没有项目记录，请使用空目录")
    previous = load_tasks(work / "tasks.jsonl")
    info = detect(game)
    engine = adapter(info)
    resources = engine.prepare(info, work)
    entries, warnings = engine.extract(info, resources)
    if not entries:
        raise ValueError("没有提取到文本；不能将未支持的资源当作提取成功")
    tasks, scenes = index_entries(entries, info["family"])
    old_tasks = {t["id"]: t for t in previous}
    for task in tasks:
        old = old_tasks.get(task["id"])
        if not old:
            continue
        same = all(old.get(k) == task[k] for k in ("source_hash", "context_hash"))
        task.update(translation=old.get("translation", ""), revision=old.get("revision", 0))
        if same:
            for field in ("status", "review_reason", "last_submission"):
                if field in old:
                    task[field] = old[field]
        else:
            task["revision"] += 1
            if task["translation"]:
                task.update(status="NEEDS_HUMAN", review_reason="原文或场景上下文改变，请重新审核")
    manifest = {"schema_version": SCHEMA_VERSION,
                "project_id": previous_manifest["project_id"] if previous_manifest else uuid.uuid4().hex,
                "game_dir": str(game), "resource_root": resources["root"], "engine": info,
                "scenes": scenes, "warnings": warnings, "entries_hash": stable_id(entries),
                "source_hashes": {name: file_hash(safe_join(resources["root"], name))
                                  for name in sorted({e["file"] for e in entries})}}
    if info.get("archive"):
        manifest["archive_hash"] = file_hash(info["archive"])
    work.mkdir(parents=True, exist_ok=True)
    if previous:
        write_file(work / "tasks.previous.jsonl", read_file(work / "tasks.jsonl"))
    initialize(work, tasks)
    write_json(work / "entries.json", entries)
    save_tasks(work / "tasks.jsonl", tasks)
    # Last file is a commit marker: load_project rejects incomplete index updates.
    write_json(work / "project.json", manifest)
    return status(work)


def load_project(work_dir):
    work = Path(work_dir).resolve()
    manifest = json.loads(read_file(work / "project.json") or "null")
    if not manifest or manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("缺少版本 3 项目，请先 prepare 到独立工作目录")
    entries = json.loads(read_file(work / "entries.json") or "null")
    if not isinstance(entries, list) or not entries or stable_id(entries) != manifest["entries_hash"]:
        raise ValueError("文本定位索引与项目记录不一致，请重新 prepare")
    tasks = load_tasks(work / "tasks.jsonl")
    expected, scenes = index_entries([dict(e) for e in entries], manifest["engine"]["family"])
    if scenes != manifest["scenes"] or [t["id"] for t in tasks] != [t["id"] for t in expected]:
        raise ValueError("任务或 Scene 与定位索引不匹配")
    mutable = {"translation", "status", "revision"}
    for actual, original in zip(tasks, expected):
        if any(actual.get(k) != v for k, v in original.items() if k not in mutable):
            raise ValueError("任务原文或上下文被修改，请通过 prepare 更新")
        if (not isinstance(actual.get("translation"), str) or
                type(actual.get("revision")) is not int or actual["revision"] < 0):
            raise ValueError("任务译文或版本无效")
    return manifest, entries, tasks


def save_state(work, tasks):
    """One atomic mutable-state write, with the immediately previous version."""
    work = Path(work)
    write_file(work / "tasks.previous.jsonl", read_file(work / "tasks.jsonl"))
    save_tasks(work / "tasks.jsonl", tasks)


def status(work_dir):
    manifest, entries, tasks = load_project(work_dir)
    by_id = {t["id"]: t for t in tasks}
    return {"project_id": manifest["project_id"], "engine": manifest["engine"],
            "entries": len(entries), "tasks": len(tasks),
            "counts": dict(Counter(t["status"] for t in tasks)),
            "scenes": [{**s, "counts": dict(Counter(by_id[t]["status"] for t in s["task_ids"]))}
                       for s in manifest["scenes"]], "warnings": manifest["warnings"]}
