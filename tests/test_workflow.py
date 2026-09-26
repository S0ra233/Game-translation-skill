"""Small behavioral suite: existing format samples plus the new Scene pipeline."""
import csv
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import game_translation as api
from game_translation.engines import unity
from game_translation.formats import marshal, rgss
from game_translation.storage import read_file, write_file, write_json
from game_translation.text import protect_tags
from fixtures_helpers import actor_blob, archive_v1, archive_v3


class Workflow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="game-translation-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.game, self.work, self.output = (self.base / n for n in ("game", "work", "output"))

    def mv(self):
        shutil.copytree(ROOT / "tests/fixtures/mv", self.game)
        return api.prepare(self.game, self.work)

    def snapshot(self, root):
        return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}

    def submit(self, package, translations=None, uncertain=False):
        translations = translations or {}
        context = {t["id"]: t for t in package["scene_context"]}
        values = [{"id": tid, "translation": translations.get(tid, context[tid]["source"]),
                   "uncertain": uncertain} for tid in package["target_ids"]]
        return api.apply_results(self.work, package["id"], values), values

    def translate_all(self, mappings):
        while api.status(self.work)["counts"].get("NONE", 0):
            package = api.make_package(self.work)
            _, _, tasks = api.load_project(self.work)
            by_id = {t["id"]: t for t in tasks}
            # Fixtures contain restored translations; model output uses protected tokens.
            translated = {tid: protect_tags(mappings[by_id[tid]["text"]])[0]
                          for tid in package["target_ids"]}
            self.submit(package, translated)

    def test_scene_package_apply_build_and_original_preservation(self):
        summary = self.mv()
        package = api.make_package(self.work)
        scene = next(s for s in summary["scenes"] if s["id"] == package["scene"]["id"])
        self.assertEqual([t["id"] for t in package["scene_context"]], scene["task_ids"])
        self.assertEqual(package["target_ids"], scene["task_ids"])
        self.assertNotIn("targets", package)
        before = self.snapshot(self.game)
        mapping = json.loads(read_file(ROOT / "tests/fixtures/translations.json"))
        self.translate_all(mapping)
        self.assertEqual(api.status(self.work)["counts"], {"PROCESSED": 18})
        report = api.build(self.work, self.output)
        self.assertTrue(report["success"])
        self.assertEqual(report["verification"]["matched"], summary["entries"])
        self.assertFalse(report["verification"]["runtime_verified"])
        self.assertEqual(before, self.snapshot(self.game))
        original = json.loads((self.game / "data/System.json").read_text(encoding="utf-8"))
        result = json.loads((self.output / "data/System.json").read_text(encoding="utf-8"))
        for key in ("switches", "variables"):
            self.assertEqual(original[key], result[key])
        with self.assertRaises(FileExistsError):
            api.build(self.work, self.output)

    def test_single_target_context_duplicate_and_stale_results(self):
        self.mv()
        _, _, tasks = api.load_project(self.work)
        task = next(t for t in tasks if t["type"] == "dialogue")
        package = api.make_package(self.work, target_ids=[task["id"]], context="neighbors")
        self.assertIn("context_before", package)
        self.assertNotIn("context_before", task)
        records = package["context_before"] + package["scene_context"] + package["context_after"]
        self.assertEqual(len(records), len({t["id"] for t in records}))
        self.assertEqual([t["id"] for t in package["scene_context"]], [task["id"]])
        self.assertEqual(api.make_package(self.work, target_ids=[task["id"]], context="neighbors"), package)
        before = {t["id"]: t for t in tasks}
        _, values = self.submit(package)
        duplicate = api.apply_results(self.work, package["id"], values)
        self.assertTrue(duplicate["duplicate"])
        _, _, after = api.load_project(self.work)
        for item in after:
            if item["id"] != task["id"]:
                self.assertEqual(item, before[item["id"]])
        stale = api.make_package(self.work, target_ids=[task["id"]])
        context_only = next(t for t in stale["scene_context"] if t["id"] != task["id"])
        saved = (self.work / "tasks.jsonl").read_bytes()
        with self.assertRaisesRegex(ValueError, "非目标"):
            api.apply_results(self.work, stale["id"], [{"id": context_only["id"],
                               "translation": "不应写入", "uncertain": False}])
        self.assertEqual(saved, (self.work / "tasks.jsonl").read_bytes())
        write_file(self.work / "style.md", "changed rules")
        with self.assertRaisesRegex(ValueError, "过期"):
            self.submit(stale)

    def test_invalid_envelope_and_review_gate(self):
        self.mv()
        task = next(t for t in api.load_project(self.work)[2] if t["codes"])
        package = api.make_package(self.work, target_ids=[task["id"]])
        before = (self.work / "tasks.jsonl").read_bytes()
        with self.assertRaises(ValueError):
            api.apply_results(self.work, package["id"], [{"id": "unknown", "translation": "你好", "uncertain": False}])
        self.assertEqual(before, (self.work / "tasks.jsonl").read_bytes())
        result, _ = self.submit(package, {task["id"]: "丢失控制码"})
        self.assertEqual(result["counts"], {"NEEDS_HUMAN": 1})
        with self.assertRaises(ValueError):
            api.build(self.work, self.output)
        package = api.make_package(self.work, target_ids=[task["id"]])
        self.submit(package)
        report = api.build(self.work, self.output, allow_partial=True)
        self.assertEqual(report["written"], 1)
        self.assertTrue(report["verification"]["indexed_values_match"])
        self.assertFalse(report["verification"]["all_tasks_approved"])

    def test_location_identity_and_reextract_review(self):
        self.mv()
        task = next(t for t in api.load_project(self.work)[2] if t["text"] == "Alice")
        package = api.make_package(self.work, target_ids=[task["id"]])
        self.submit(package, {task["id"]: "爱丽丝"})
        api.prepare(self.game, self.work)
        same = next(t for t in api.load_project(self.work)[2] if t["id"] == task["id"])
        self.assertEqual(same["status"], "PROCESSED")
        actors_path = self.game / "data/Actors.json"
        actors = json.loads(read_file(actors_path))
        actors[1]["name"] = "Alicia"
        write_json(actors_path, actors)
        with self.assertRaisesRegex(ValueError, "源资源"):
            api.build(self.work, self.output, allow_partial=True)
        api.prepare(self.game, self.work)
        changed = next(t for t in api.load_project(self.work)[2] if t["id"] == task["id"])
        self.assertEqual(changed["text"], "Alicia")
        self.assertEqual(changed["translation"], "爱丽丝")
        self.assertEqual(changed["status"], "NEEDS_HUMAN")
        self.assertTrue((self.work / "tasks.previous.jsonl").is_file())

    def test_glossary_missing_results_and_changed_index(self):
        self.mv()
        task = next(t for t in api.load_project(self.work)[2] if t["text"] == "Alice")
        write_file(self.work / "glossary.md", "| Alice | 爱丽丝 | 人名 | confirmed |\n")
        package = api.make_package(self.work, target_ids=[task["id"]])
        self.assertEqual(package, api.make_package(self.work, target_ids=[task["id"]]))
        result, _ = self.submit(package, {task["id"]: "错误译名"})
        self.assertEqual(result["counts"], {"NEEDS_HUMAN": 1})
        package = api.make_package(self.work, target_ids=[task["id"]])
        result = api.apply_results(self.work, package["id"], [])
        self.assertEqual(result["counts"], {"ERROR": 1})
        entries = json.loads(read_file(self.work / "entries.json"))
        entries[0]["path"] = "/wrong"
        write_json(self.work / "entries.json", entries)
        with self.assertRaises(ValueError):
            api.load_project(self.work)

    def test_font_configuration_and_cli_independence(self):
        self.mv()
        self.translate_all(json.loads(read_file(ROOT / "tests/fixtures/translations.json")))
        font = self.base / "example.woff2"
        font.write_bytes(b"synthetic asset: tests copying, not glyph rendering")
        report = api.build(self.work, self.output, font=font)
        self.assertEqual(report["fonts"]["status"], "configured")
        self.assertEqual((self.output / "fonts/game-translation.woff2").read_bytes(), font.read_bytes())
        self.assertFalse((self.game / "fonts").exists())
        result = subprocess.run([sys.executable, "-B", "-X", "utf8", str(ROOT / "run.py"),
                                 "detect", str(self.game)], cwd=self.base, capture_output=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["family"], "rpgmaker")

    def test_tyrano_labels_roundtrip_bom_crlf_and_script_preservation(self):
        path = self.game / "data/scenario/start.ks"
        content = ('*start\r\n#Alice\r\nHello[l][p]\r\n[glink text="Enter" target="*next"]\r\n'
                   '[iscript]\r\nvar x = "keep";\r\n[endscript]\r\n*next\r\nHello[l]\r\n')
        write_file(path, b"\xef\xbb\xbf" + content.encode(), binary=True)
        api.prepare(self.game, self.work)
        tasks = api.load_project(self.work)[2]
        repeated = [t for t in tasks if t["text"] == "Hello"]
        self.assertEqual(len(repeated), 2)
        self.assertNotEqual(repeated[0]["scene_id"], repeated[1]["scene_id"])
        self.assertNotEqual(repeated[0]["id"], repeated[1]["id"])
        self.translate_all({"Alice": "爱丽丝", "Hello": "你好", "Enter": "进入"})
        api.build(self.work, self.output)
        result = (self.output / "data/scenario/start.ks").read_bytes()
        self.assertTrue(result.startswith(b"\xef\xbb\xbf"))
        text = result.decode("utf-8-sig")
        self.assertIn("#爱丽丝\r\n你好[l][p]\r\n", text)
        self.assertIn('target="*next"', text)
        self.assertIn('var x = "keep";', text)

    def test_unity_csv_roundtrip(self):
        path = self.game / "Demo_Data/StreamingAssets/dialogue.csv"
        write_file(path, 'id,text\nhero,"Hello,\ntraveler"\n')
        api.prepare(self.game, self.work)
        self.translate_all({"Hello,\ntraveler": '你好，\n"旅人"'})
        api.build(self.work, self.output)
        rows = list(csv.reader(io.StringIO(read_file(self.output / path.relative_to(self.game)))))
        self.assertEqual(rows, [["id", "text"], ["hero", '你好，\n"旅人"']])

    def test_unity_textasset_selected_field(self):
        path = self.base / "story.assets"
        path.write_bytes(b"synthetic")
        tree = {"m_Name": "Story", "m_Script": '{"id":"Cat","text":"Cat","extra":"Caterpillar"}'}
        obj = types.SimpleNamespace(path_id=7, assets_file=types.SimpleNamespace(name="CAB-a"),
                                    type=types.SimpleNamespace(name="TextAsset"),
                                    read_typetree=lambda: tree, save_typetree=lambda value: None)
        env = types.SimpleNamespace(objects=[obj], file=types.SimpleNamespace(save=lambda: b"saved"))
        entry = {"file": "story.assets", "path": "/text", "text": "Cat", "format": "json",
                 "asset": unity.asset_identity(obj, tree)}
        with patch.dict(sys.modules, {"UnityPy": types.SimpleNamespace(load=lambda _: env)}):
            self.assertEqual(unity.write(path, [(entry, '猫"咪')]), 1)
            self.assertEqual(unity.read(path, [entry]), ['猫"咪'])
        self.assertEqual(json.loads(tree["m_Script"]), {"id": "Cat", "text": '猫"咪', "extra": "Caterpillar"})

    def test_rgss_archive_to_marshal_translated_copy(self):
        archive = self.game / "Game.rgss3a"
        original = archive_v3("Data/Actors.rvdata2", actor_blob("Alice"))
        write_file(archive, original, binary=True)
        api.prepare(self.game, self.work)
        self.translate_all({"Alice": "爱丽丝"})
        api.build(self.work, self.output)
        self.assertEqual(archive.read_bytes(), original)
        self.assertFalse((self.output / "Game.rgss3a").exists())
        self.assertEqual((self.output / "Data/Actors.rvdata2").read_bytes(), actor_blob("爱丽丝"))

    def test_rgss_v1_and_invalid_paths(self):
        archive = self.game / "Game.rgssad"
        files = [("Data/Actors.rxdata", actor_blob("Alice")), ("Graphics/readme.txt", b"abcde")]
        write_file(archive, archive_v1(files), binary=True)
        rgss.unpack_rgss(archive, self.work)
        for name, value in files:
            self.assertEqual((self.work / name).read_bytes(), value)
        for name in ("../outside", "C:/outside"):
            write_file(archive, archive_v3(name, b"data"), binary=True)
            with self.assertRaises(ValueError):
                rgss.unpack_rgss(archive, self.work)

    def test_marshal_reference_cycle_attributes_and_truncation(self):
        obj = marshal.MC.load(b'\x04\x08[\x07"\x06a@\x06')
        self.assertIs(obj.root.data[0], obj.root.data[1].at())
        cycle = marshal.MC.load(b"\x04\x08[\x06@\x00")
        self.assertIs(cycle.root.data[0].at(), cycle.root)
        blob = b'\x04\x08[\x07I"\x06a\x06:\x06ET@\x06'
        self.assertEqual(marshal.MC.load(blob).dump(), blob)
        with self.assertRaises(ValueError):
            marshal.MC.load(b'\x04\x08"\x08ab')


if __name__ == "__main__":
    unittest.main()
