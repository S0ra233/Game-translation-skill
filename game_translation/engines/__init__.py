"""Static adapter registry. Each module owns its engine-specific decisions.

Contract: probe(game) -> detection or None; prepare(info, work) -> resources;
extract(info, resources) -> (entries, warnings); read/write handle one file;
configure_font(output, info, font, tmp_font) -> structured report.
All paths passed by Core are pathlib.Path; functions do not print or exit.
"""
from pathlib import Path
from . import rpgmaker, unity, tyrano

ADAPTERS = {"rpgmaker": rpgmaker, "unity": unity, "tyrano": tyrano}


def adapter(info):
    try:
        return ADAPTERS[info["family"]]
    except KeyError as exc:
        raise ValueError("没有对应的引擎适配器，不能继续提取或写回") from exc


def detect(game_dir):
    game = Path(game_dir).resolve()
    if not game.is_dir():
        raise ValueError(f"游戏目录不存在: {game}")
    matches = [info for engine in ADAPTERS.values() if (info := engine.probe(game))]
    if len(matches) > 1:
        raise ValueError("目录同时匹配多个引擎，请指定实际游戏子目录")
    info = matches[0] if matches else {"family": "unknown", "variant": "unknown",
                                        "evidence": [], "data_dir": None}
    info["game_dir"] = str(game)
    info["font_options"] = adapter(info).font_options(info) if matches else []
    return info


def unchanged_font():
    return {"status": "unchanged", "note": "未指定字体；字形覆盖和界面显示需要实机检查"}
