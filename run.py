"""Thin Skill CLI. The reusable package has no terminal or provider dependencies."""
import argparse
import json
from pathlib import Path
import sys

import game_translation as api


def main(argv=None):
    parser = argparse.ArgumentParser(description="Scene 游戏翻译工作流")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("detect", help="检测引擎和字体能力")
    p.add_argument("game")
    p = commands.add_parser("prepare", help="检测、解包、提取并建立 Scene/Task/Entry")
    p.add_argument("game")
    p.add_argument("work")
    p = commands.add_parser("status", help="查看任务状态和 Scene ID")
    p.add_argument("work")
    p = commands.add_parser("package", help="导出下一 Scene，或指定任务重翻")
    p.add_argument("work")
    p.add_argument("--scene")
    p.add_argument("--target", action="append")
    p.add_argument("--context", choices=("scene", "neighbors"), default="scene")
    p.add_argument("--window", type=int, default=2)
    p.add_argument("--include-review", action="store_true")
    p.add_argument("--max-chars", type=int, default=60000)
    p = commands.add_parser("apply", help="校验并提交翻译结果 JSON 数组")
    p.add_argument("work")
    p.add_argument("package_id")
    p.add_argument("results")
    p = commands.add_parser("build", help="写回一个全新的游戏副本")
    p.add_argument("work")
    p.add_argument("output")
    p.add_argument("--allow-partial", action="store_true")
    fonts = p.add_mutually_exclusive_group()
    fonts.add_argument("--font")
    fonts.add_argument("--tmp-font")
    p = commands.add_parser("verify", help="重新读取已提取位置，核对写回内容")
    p.add_argument("work")
    p.add_argument("output")
    args = parser.parse_args(argv)
    try:
        if args.command == "detect":
            result = api.detect(args.game)
        elif args.command == "prepare":
            result = api.prepare(args.game, args.work)
        elif args.command == "status":
            result = api.status(args.work)
        elif args.command == "package":
            result = api.make_package(args.work, args.scene, args.target, context=args.context,
                                      window=args.window, include_review=args.include_review,
                                      max_chars=args.max_chars)
        elif args.command == "apply":
            values = json.loads(Path(args.results).read_text(encoding="utf-8-sig"))
            result = api.apply_results(args.work, args.package_id, values)
        elif args.command == "build":
            result = api.build(args.work, args.output, allow_partial=args.allow_partial,
                               font=args.font, tmp_font=args.tmp_font)
        else:
            result = api.verify(args.work, args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if args.command == "verify" and not result["indexed_values_match"] else 0
    except (OSError, ValueError, RuntimeError, ImportError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
