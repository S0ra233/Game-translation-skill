"""Unity tables and indexed serialized assets; UnityPy is loaded on demand."""
import configparser
import io
import os
import re
import shutil
from pathlib import Path
from collections import defaultdict
from ..storage import read_file, write_file, safe_join
from ..formats.tables import _emit, _extract_table, json_pointer, replace_table, get_json_path
from ..formats import tables

UNITY_VERSION_RE = re.compile(r"([2-9]\d{3}\.\d+\.\d+[a-z0-9]*)", re.I)


def detect_unity(game_dir):
    """检测 Unity 游戏特征。"""
    # 查找 Data 目录
    data_dir = None
    if any(f.endswith(".assets") for f in os.listdir(game_dir)) or os.path.exists(os.path.join(game_dir, "globalgamemanagers")):
        data_dir = game_dir
    else:
        for entry in os.listdir(game_dir):
            if entry.lower() == "il2cpp_data":
                continue
            p = os.path.join(game_dir, entry)
            if os.path.isdir(p) and entry.lower().endswith("_data"):
                data_dir = p
                break

    if not data_dir:
        return None

    # 检测版本
    version = "Unknown"
    for c in (os.path.join(data_dir, "globalgamemanagers"), os.path.join(data_dir, "data.unity3d"), os.path.join(data_dir, "mainData")):
        if os.path.isfile(c):
            try:
                with open(c, "rb") as handle:
                    content = handle.read(2048).decode("latin1")
                m = UNITY_VERSION_RE.search(content)
                if m:
                    version = m.group(1)
                    break
            except Exception:
                pass

    # 检测后端 (Mono vs IL2CPP)
    has_ga = os.path.isfile(os.path.join(game_dir, "GameAssembly.dll")) or os.path.isfile(os.path.join(os.path.dirname(data_dir), "GameAssembly.dll"))
    has_il2cpp = has_ga or os.path.isdir(os.path.join(data_dir, "il2cpp_data")) or os.path.isdir(os.path.join(game_dir, "il2cpp_data"))
    backend = "IL2CPP" if has_il2cpp else ("Mono" if os.path.isdir(os.path.join(data_dir, "Managed")) else "Unknown")

    # 检测子框架 (Addressables StringTable / Utage / TextAsset)
    features = []
    sa_dir = os.path.join(data_dir, "StreamingAssets") if os.path.isdir(os.path.join(data_dir, "StreamingAssets")) else os.path.join(game_dir, "StreamingAssets")
    if os.path.isdir(sa_dir):
        features.append("StreamingAssets")
        for root, _, files in os.walk(sa_dir):
            for fn in files:
                if "string-tables" in fn:
                    features.append("Unity-Localization(StringTable)")
                    break
                if "utage" in fn.lower():
                    features.append("Utage-Engine")
                    break

    # 检查私有加密归档
    priv_archives = [f for f in os.listdir(game_dir) if f.lower().endswith((".dat", ".bin", ".pak", ".arc")) and not f.lower().startswith("unity")]

    return {
        "engine": f"Unity ({backend})",
        "family": "Unity",
        "unity_version": version,
        "backend": backend,
        "data_dir": data_dir,
        "features": list(set(features)),
        "private_archives": priv_archives,
    }

def asset_identity(obj, tree):
    return {"path_id": obj.path_id, "file": str(obj.assets_file.name),
            "name": tree.get("m_Name", ""), "kind": obj.type.name}


def _extract_unity(game_dir, data_dir, entries, warnings=None):
    warnings = warnings if warnings is not None else []
    root, data = Path(game_dir), Path(data_dir or game_dir)
    streaming = data / "StreamingAssets"
    if not streaming.is_dir():
        streaming = root / "StreamingAssets"
    if streaming.is_dir():
        for path in sorted(streaming.rglob("*")):
            if not path.is_file():
                continue
            ext = path.suffix.lower()
            file = path.relative_to(root).as_posix()
            if ext in (".json", ".csv", ".tsv", ".txt"):
                _extract_table(file, read_file(path), "text" if ext == ".txt" else ext[1:], entries)
            elif ext in (".nani", ".xml"):
                warnings.append(f"{file}: 脚本/XML 需要按实际语法适配，未作为普通文本修改")

    assets = [p for p in sorted(data.rglob("*")) if p.is_file() and
              (p.suffix.lower() in (".assets", ".bundle", ".unity3d") or p.name == "globalgamemanagers")]
    if not assets:
        return
    try:
        import UnityPy
    except ImportError as exc:
        raise RuntimeError("Unity 资产读取需要依赖：python -m pip install UnityPy") from exc
    for path in assets:
        file = path.relative_to(root).as_posix()
        try:
            env = UnityPy.load(str(path))
        except Exception as exc:
            warnings.append(f"{file}: Unity 资源未读取 ({type(exc).__name__}: {exc})")
            continue
        for obj in env.objects:
            if obj.type.name not in ("TextAsset", "MonoBehaviour"):
                continue
            try:
                tree = obj.read_typetree()
                identity = asset_identity(obj, tree)
                if obj.type.name == "TextAsset":
                    script = tree.get("m_Script", "")
                    text = script if isinstance(script, str) else bytes(script).decode("utf-8-sig")
                    if text.strip().startswith(("{", "[")):
                        fmt = "json"
                    else:
                        suffix = Path(tree.get("m_Name", "")).suffix.lower()
                        if suffix not in (".csv", ".tsv", ".txt"):
                            if text.strip():
                                warnings.append(f"{file}::{identity['name']}: 非 JSON TextAsset 需要确认格式")
                            continue
                        fmt = "text" if suffix == ".txt" else suffix[1:]
                    _extract_table(file, text, fmt, entries, asset=identity,
                                   scene=file + "::" + str(identity["path_id"]))
                elif isinstance(tree.get("m_TableData"), list):
                    for index, row in enumerate(tree["m_TableData"]):
                        _emit(entries, file, json_pointer(("m_TableData", index, "m_Localized")),
                              "string_table", row.get("m_Localized"), "string-table",
                              asset=identity, scene=file + "::" + str(identity["path_id"]))
            except Exception as exc:
                warnings.append(f"{file} / PathID {obj.path_id}: {type(exc).__name__}: {exc}")

def _patch_asset(path, items):
    import UnityPy
    env = UnityPy.load(str(path))
    groups = defaultdict(list)
    for entry, text in items:
        identity = entry["asset"]
        groups[(identity["file"], identity["path_id"])].append((entry, text))
    written = 0
    for (asset_file, path_id), replacements in groups.items():
        objects = [obj for obj in env.objects
                   if obj.path_id == path_id and str(obj.assets_file.name) == asset_file]
        if len(objects) != 1:
            raise ValueError(f"资产定位不是唯一结果: {asset_file} / {path_id}")
        obj = objects[0]
        tree = obj.read_typetree()
        identity = asset_identity(obj, tree)
        if identity != replacements[0][0]["asset"]:
            raise ValueError("资产名称或类型与提取时不一致")
        formats = {entry["format"] for entry, _ in replacements}
        if len(formats) != 1:
            raise ValueError("一个资产不能混用多个解析格式")
        fmt = formats.pop()
        if obj.type.name == "TextAsset":
            script = tree["m_Script"]
            was_bytes = not isinstance(script, str)
            text = bytes(script).decode("utf-8-sig") if was_bytes else script
            translated = replace_table(text, fmt, replacements)
            tree["m_Script"] = translated.encode("utf-8") if was_bytes else translated
        elif obj.type.name == "MonoBehaviour" and fmt == "string-table":
            tree = replace_table(tree, fmt, replacements)
        else:
            raise ValueError("资产类型与文本格式不匹配")
        obj.save_typetree(tree)
        written += len(replacements)
    write_file(path, env.file.save(), binary=True)
    return written


def probe(game):
    info = detect_unity(str(game))
    if info:
        info.update(family="unity", variant=info["backend"].lower(),
                    evidence=[Path(info["data_dir"]).relative_to(game).as_posix()])
    return info


def prepare(info, work):
    return {"root": info["game_dir"], "data_dir": info["data_dir"]}


def extract(info, resources):
    entries, warnings = [], []
    _extract_unity(resources["root"], resources["data_dir"], entries, warnings)
    warnings.extend(f"私有归档未解析: {name}" for name in info.get("private_archives", []))
    for entry in entries:
        entry["scene_kind"] = "text_group"
    return entries, warnings


def read(path, entries):
    if not any("asset" in e for e in entries):
        return tables.read(path, entries)
    import UnityPy
    env = UnityPy.load(str(path))
    cache, result = {}, []
    for entry in entries:
        identity = entry["asset"]
        key = (identity["file"], identity["path_id"])
        if key not in cache:
            objects = [o for o in env.objects if o.path_id == key[1] and str(o.assets_file.name) == key[0]]
            if len(objects) != 1:
                raise ValueError("输出资产缺失或定位不唯一")
            tree = objects[0].read_typetree()
            if asset_identity(objects[0], tree) != identity:
                raise ValueError("输出资产身份改变")
            if entry["format"] == "string-table":
                value = tree
            else:
                import csv
                import json
                script = tree["m_Script"]
                text = script if isinstance(script, str) else bytes(script).decode("utf-8-sig")
                fmt = entry["format"]
                if fmt == "json":
                    value = json.loads(text)
                elif fmt in ("csv", "tsv"):
                    value = list(csv.reader(io.StringIO(text), delimiter="\t" if fmt == "tsv" else ","))
                elif fmt == "text":
                    value = text.splitlines()
                else:
                    raise ValueError(f"未知 TextAsset 格式: {fmt}")
            cache[key] = value
        result.append(get_json_path(cache[key], entry["path"]))
    return result


def write(path, items):
    if any("asset" in e for e, _ in items):
        if not all("asset" in e for e, _ in items):
            raise ValueError("文件不能同时作为资产和明文写回")
        return _patch_asset(path, items)
    return tables.write(path, items)


def font_options(info):
    return ["tmp_assetbundle"]


def configure_font(output, info, font=None, tmp_font=None):
    from . import unchanged_font
    if font:
        raise ValueError("Unity 需要 TMP 字体 AssetBundle，不能直接使用普通字体文件")
    if not tmp_font:
        return unchanged_font()
    source = Path(tmp_font).resolve()
    plugins = output / "BepInEx/plugins"
    if not source.is_file() or not plugins.is_dir() or not any(
            "autotranslator" in p.name.lower() for p in plugins.rglob("*.dll")):
        raise ValueError("需要现有 TMP Bundle 和已安装的 XUnity.AutoTranslator")
    target = safe_join(output, source.name)
    if target.exists():
        raise FileExistsError("字体 Bundle 名称与游戏文件冲突，请重命名字体文件")
    shutil.copyfile(source, target)
    config_path = output / "BepInEx/config/AutoTranslatorConfig.ini"
    config = configparser.ConfigParser(interpolation=None, strict=False)
    config.optionxform = str
    if config_path.exists():
        config.read_string(read_file(config_path))
    if not config.has_section("Behaviour"):
        config.add_section("Behaviour")
    config.set("Behaviour", "FallbackFontTextMeshPro", source.name)
    buffer = io.StringIO()
    config.write(buffer)
    write_file(config_path, buffer.getvalue())
    return {"status": "configured", "asset": source.name,
            "note": "已配置 TMP 回退；Bundle 版本兼容性与显示效果需实机检查"}
