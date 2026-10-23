# Game Translation

[简体中文](README.md) | English

**Game Translation** is a local game localization and text engineering toolchain designed for collaboration with AI agents. It provides an end-to-end workflow for extraction, candidate review, translation validation, and writeback to a standalone copy across **RPG Maker, WOLF RPG Editor, Unity, Ren'Py, TyranoScript, and Godot**.

The project follows a **deterministic Core + intelligent host Agent** model:

- **Core**: Unpacks binary resources, locates assets, manages translation state through Entry / Task / Scene, validates placeholders and terminology, and writes translations safely in a separate staging area before verifying them through readback.
- **Agent**: Handles natural-language translation in context, selects relevant text fields from large candidate sets, and helps investigate game-specific issues such as proprietary wrappers or encryption (for example, MoleBox VFS), unusual encodings, or missing fonts.

## Design Highlights

- **Read-only protection for the original game**:
  The original game directory remains read-only throughout the workflow. Source files are never modified directly. A build first creates a copy in a separate staging area, writes the translations, verifies the result through readback, and only then publishes the final output directory atomically. Windows `\\?\` extended-length paths and automatic backoff retries for file locks are supported. If a build fails, the staging files are retained and the failed stage is recorded in `build_report.json` for diagnosis.

- **A unified contextual data model**:
  Engine-specific resource differences are represented through three shared layers:

  - **Entry — resource location**: Records the precise location of a text item within a game asset so that writeback targets the correct field.
  - **Task — translation unit**: Tracks the source text, translation, and validation state of an individual item. Identical text at different locations remains separate to prevent context-dependent translations from affecting the wrong occurrence.
  - **Scene — context group**: An ordered collection of tasks organized by event page, script label, or data table, allowing the Agent to translate within the available context rather than treating every string in isolation.

- **Review before extraction with Candidates**:
  Unity, Godot, and WOLF projects can contain tens of thousands of code literals, multilingual table cells, and unidentified fields. Run `candidates` first to export a review list, let the Agent identify actual dialogue and UI fields, and then create the translation project. This helps avoid polluting the context or modifying system constants.

- **Readback verification after writeback**:
  Every build deserializes and rereads the written text at its original locations, comparing each field with the expected value. The project reports end-to-end writeback and 100% readback consistency checks across six engine families and 20 commercial and independently developed games, covering more than 250,000 entries.

- **Practical diagnostic tools**:
  Use `locate GAME "known text"` to find the resource containing an on-screen line, and `fonts GAME REPORT.json` to scan a game's font references.

## Supported Engines and Scope

| Engine family | Supported extraction and writeback capabilities | Edge cases and Agent-assisted work |
| --- | --- | --- |
| **RPG Maker** (XP / VX / VX Ace / MV / MZ) | **MV / MZ**: Reads and writes database JSON, system text, and event scripts while preserving control codes.<br>**XP / VX / VX Ace**: Reads and writes Ruby Marshal files (`.rxdata` / `.rvdata2`); decrypts and unpacks `Game.rgssad` / `Game.rgss3a` archives to produce a standalone copy using unpacked resources. | Plugin-specific hardcoded text, dynamically assembled dialogue, and text embedded in images may require individual adapters. The output copy runs from unpacked resources, without requiring encrypted repackaging. |
| **WOLF RPG Editor** | Uses the `UberWolfCli` and `WolfTL` backends to unpack encrypted `.wolf` archives in the background. Extracts dialogue, speakers, and choices through a `cp932` AST, then reconstructs a standalone game copy after patching. | Custom encryption variants and image text may require Agent assistance. A Chinese-language copy may require a suitable font to be selected in the game settings or configuration. See the [WOLF guide](tools/wolf/README.md). |
| **Unity** (tables / serialized assets / code strings) | **Tables and embedded text**: Supports StreamingAssets and heuristic format detection for extensionless `TextAsset` resources (JSON / CSV / TSV / TXT / XML), preserving the original encoding and BOM.<br>**Serialized assets**: Uses `UnityPy` to read and write `TextAsset`, Localization `StringTable`, TMP text components, Fungus, and Utage `AdvImportBook` resources.<br>**Code literals**: Reconstructs IL2CPP `global-metadata.dat` v29 string pools and rewrites Mono `ldstr` instructions in `Assembly-CSharp.dll`.<br>**Resources and fonts**: Updates local Addressables bundle CRCs, sizes, and catalogs, with font replacement through `--font-plan` / `--tmp-font`. | Commercial games with stripped type trees may require `TypeTreeGeneratorAPI`. Remote Addressables bundles and custom providers require individual review. When changing code literals, account for multiple code paths sharing the same string index. See the [Mono guide](tools/unity_mono/README.md), [Addressables guide](tools/unity_addressables/README.md), and [font guide](tools/unity_fonts.md). |
| **Ren'Py** | Supports loose `.rpy` scripts, `.rpa` archives through `unrpa`, and compiled `.rpyc` scripts through `unrpyc`. Extracts official translation IDs and UI strings, then generates non-invasive multilingual overrides under `game/tl/<language>/` in the output copy. | Heavily obfuscated scripts and dynamically assembled strings may need Agent analysis. The original script is left unchanged by default; translations use Ren'Py's multilingual layer. See the [Ren'Py guide](tools/renpy/README.md). |
| **TyranoScript** (web / Electron visual novels) | Supports `.ks` scripts in loose directories or standard Electron `resources/app.asar` archives. Extracts dialogue, speakers, and macro arguments by script tag, then reconstructs the archive or creates an unpacked directory and verifies the bytes. | Complex dynamic JavaScript and custom macros need separate handling. If the executable enforces ASAR hash integrity, that restriction must be addressed or the application must be configured to load unpacked resources. See the [ASAR guide](tools/tyrano_asar.md). |
| **Godot Engine** (3.x / 4.x packages and scenes) | Uses `GDRETools` to read and write standard `.pck` containers and GDPC packages embedded in executables; `--godot-exe` resolves ambiguous multi-package projects. Supports text and binary scene properties, PO files, and hash-bucket lookup with lossless UTF-8 buffer rewriting for compiled `OptimizedTranslation` (`.translation`) tables. | Unregistered strings assembled dynamically in scripts should first be reviewed through `candidates`. Package mounting precedence and third-party wrappers may require Agent investigation. See the [Godot guide](tools/godot/README.md). |

## Quick Start: Use Through an AI Agent

The project can run as a standalone CLI or through its Agent Skill. A host that supports local file access and command execution—such as Claude Code, Cursor, or Windsurf—can carry out the workflow.

- **Full Skill entry point**: [skills/game-translation/SKILL.md](skills/game-translation/SKILL.md). The repository-root `SKILL.md` is retained as a compatibility entry pointing to the full Skill.
- **Cross-host deployment**: Copy the complete `skills/game-translation/` directory when installing the Skill in another host. Commands accept absolute paths, such as `python /path/to/source/run.py status /path/to/work`, so switching the current working directory is not required.

### Example Prompts

**1. Full localization workflow**

> Read `<project-directory>/skills/game-translation/SKILL.md` first, then follow its workflow to localize this game.
>
> - Original game: `D:\Games\ExampleGame`
> - Working directory: `D:\TranslationWork\ExampleGame`
> - Output directory: `D:\TranslatedGames\ExampleGame`
> - Target language: Simplified Chinese

**2. Investigate a missing line or retranslate a specific item**

The Agent should stay within the requested scope rather than rerun the entire workflow.

> The line “出発の準備はできた？” is still untranslated in the game. Use `locate` to find its resource, then check whether its field was missed during candidate selection.

## Environment and Optional Dependencies

**The core workflow requires only Python 3.10+ and the standard library.** No model API key is required by the Core; translation is provided by the host Agent. For RPG Maker, plaintext Ren'Py scripts, basic TyranoScript, or ordinary plaintext tables, you can start directly after cloning the repository:

```powershell
python --version
python run.py --help
```

### Optional Components

Unity serialized assets, encrypted packages, and compiled binary scripts may require additional tools. Missing optional dependencies are reported for the relevant engine without preventing unrelated workflows from running.

| Engine | Dependency or tool | Purpose and setup |
| --- | --- | --- |
| **Unity** | `UnityPy` (pip) | Reads and writes Unity serialized assets such as `TextAsset` and `StringTable`. Install in a virtual environment: `pip install UnityPy`. |
| **Unity** | `TypeTreeGeneratorAPI` (pip) | Reconstructs asset structures for commercial games with stripped type trees: `pip install TypeTreeGeneratorAPI`. |
| **Unity** | `UnityMono.exe` (dnlib) | Rewrites Mono `ldstr` string instructions in `Assembly-CSharp.dll`. See [tools/unity_mono/](tools/unity_mono/README.md). |
| **Unity** | Addressables helper | Updates local bundle CRCs, sizes, and catalog cache identifiers. See [tools/unity_addressables/](tools/unity_addressables/README.md). |
| **Godot** | `gdre_tools.exe` (GDRETools) | Unpacks and rebuilds `.pck` containers and converts binary scenes. Configure `$env:GAME_TRANSLATION_GDRE` or place it in `tools/godot/bin/`. See the [Godot guide](tools/godot/README.md). |
| **WOLF** | `UberWolfCli.exe` and `WolfTL` | Decrypts `.wolf` archives and exports/patches the AST. Place the tools in `tools/wolf/bin/` or add them to `PATH`. See the [WOLF guide](tools/wolf/README.md). |
| **Ren'Py** | `unrpa` and `unrpyc` | Unpacks `.rpa` archives and decompiles `.rpyc` scripts. Install the appropriate packages or follow the [Ren'Py guide](tools/renpy/README.md). |
| **Tyrano** | Node.js `asar` / built-in parser | Reads and rebuilds Electron `app.asar` archives. See the [ASAR guide](tools/tyrano_asar.md). |

## Full CLI Workflow

```text
Original game (read-only)
  ├─ 1. detect / candidates → Detect the engine and review uncertain candidate fields
  ├─ 2. prepare             → Extract text; create Entry / Task / Scene and terminology candidates
  ├─ 3. package             → Export a Scene-based JSON translation package
  ├─ 4. Host Agent          → Translate using context, terminology, and style guidance
  ├─ 5. apply               → Validate placeholders and structure; update task states
  └─ 6. build & verify      → Write to a separate copy and verify by rereading each field
```

> **Path requirements**: The original game directory, working directory (`WORK`), and output directory (`OUTPUT`) must be separate. They must not overlap or be nested inside one another.

### Step 1: Detect the Engine and Extract Text (`detect` / `prepare`)

```powershell
python run.py detect "D:\Games\ExampleGame"
python run.py prepare "D:\Games\ExampleGame" "D:\TranslationWork\ExampleGame"
```

Use an empty working directory for the first run. `prepare` creates these project files:

| File | Purpose |
| --- | --- |
| `project.json` | Engine details, Scene groups, source hashes, and project format version (currently v3). |
| `entries.json` | Exact locations of text within the original game resources. |
| `tasks.jsonl` | Source text, translations, and current states for all translation tasks. |
| `proper_nouns.md` | Automatically detected high-frequency proper-name candidates; updated on re-extraction. |
| `glossary.md` | The formal glossary maintained by the user and Agent. |
| `style.md` | Target language, character voice, forms of address, and formatting conventions. |

Before translating in bulk, review `proper_nouns.md` and add confirmed translations to `glossary.md`:

```markdown
| Source | Translation | Notes | Status |
|---|---|---|---|
| Alice | 爱丽丝 | Protagonist | confirmed |
| Silver Order | | Organization; needs story context | pending |
```

### Step 2: Export a Translation Package (`package`)

```powershell
python run.py status "D:\TranslationWork\ExampleGame"
python run.py package "D:\TranslationWork\ExampleGame"
```

By default, the next Scene containing unfinished tasks is exported in order and saved under the working directory's `packages/` folder. The default package limit is `60,000` characters, configurable through `--max-chars`.

The package distinguishes **translation targets** from **context references**:

- `target_ids`: IDs of the tasks whose translations must be submitted.
- `scene_context`: Contextual dialogue for understanding the Scene without submitting those reference items again.

The Agent produces a UTF-8 JSON array, for example in `results.json`:

```json
[
  {
    "id": "task ID copied from target_ids",
    "translation": "对应的中文译文",
    "uncertain": false
  }
]
```

> **Validation rules**: Preserve protected control-code placeholders such as `{p0}` and `{p1}` exactly. Set `uncertain` to `true` when meaning or a character name requires review.

### Step 3: Submit Translations and Update Task States (`apply`)

```powershell
python run.py apply "D:\TranslationWork\ExampleGame" "package-ID" "D:\TranslationWork\ExampleGame\results.json"
python run.py status "D:\TranslationWork\ExampleGame"
```

The Core checks placeholders, control codes, and terminology consistency, then assigns each task one of these states:

- **`NONE`**: Not translated yet.
- **`PROCESSED`**: Passed the configured checks and is not marked `uncertain`. This means engineering validation passed, not that human editing is complete.
- **`NEEDS_HUMAN`**: Placeholder or terminology checks failed, or the Agent marked the item `uncertain: true`.
- **`ERROR`**: A target ID is missing from the submitted result or the result has an invalid format.

To export items marked `NEEDS_HUMAN` for review:

```powershell
python run.py package "D:\TranslationWork\ExampleGame" --include-review
```

### Step 4: Build a New Game Copy and Verify Readback (`build` / `verify`)

```powershell
python run.py build "D:\TranslationWork\ExampleGame" "D:\TranslatedGames\ExampleGame"
```

- **Complete validation by default**: All tasks must be `PROCESSED` before a normal build. To preview a partially translated copy, add `--allow-partial`; unfinished items retain their source text.
- **Built-in readback verification**: `build` includes the readback checks and saves `build_report.json` and `verify_report.json` in the working directory. You can also run verification separately after editing output files manually:

```powershell
python run.py verify "D:\TranslationWork\ExampleGame" "D:\TranslatedGames\ExampleGame"
```

## Advanced Workflows: Retranslation, Incremental Progress, and Fonts

### 1. Retranslate a Specific Item

If a line reads awkwardly during gameplay, export a package for that task ID. Full Scene context is included by default:

```powershell
python run.py package "D:\TranslationWork\ExampleGame" --target "task-ID"
```

For a very long Scene, request a neighboring context window instead:

```powershell
python run.py package "D:\TranslationWork\ExampleGame" --target "task-ID" --context neighbors --window 2
```

### 2. Incremental Extraction and Continued Translation

- **Preserve progress**: Running `prepare` again on the same working directory preserves translations when the item's location, source text, and Scene context remain unchanged. Items with changed source text are marked `NEEDS_HUMAN`.
- **Concurrency and versions**: Multiple subagents may translate separate packages in parallel, but `apply` operations on the same working directory should run serially. The current project format is `v3`; the translation package format is `v2`.

### 3. Font Discovery and Configuration

- **Scan font references**: Run `python run.py fonts "D:\Games\ExampleGame" "D:\TranslationWork\fonts_report.json"` to export the game's font asset references.
- **RPG Maker MV / MZ**: Pass `--font "D:\Fonts\MyFont.ttf"` during the build to inject a TTF / OTF / WOFF / WOFF2 font.
- **Unity**: Use `--font-plan` to replace TTF/OTF or TMP font assets according to a plan, or use `--tmp-font` to mount a compatible TMP AssetBundle in an environment configured with `XUnity.AutoTranslator`. See the [Unity font guide](tools/unity_fonts.md).

> [!IMPORTANT]
> **Readback consistency and the in-game experience are different checks.**
>
> A report showing 100% readback verification means the targeted writeback checks passed without detected text corruption or incorrect resource offsets. It does not establish that every story resource was extracted, that the active language column of a multilingual game was covered, or that fonts and dialogue layouts render correctly. After building, launch the output copy and inspect the opening screens and main story flow.

## Project Structure

```text
run.py                    Unified CLI entry point
SKILL.md                  Compatibility entry pointing to skills/game-translation/SKILL.md
skills/game-translation/  Full Agent Skill and engine/host references
game_translation/
  project.py              Entry / Task / Scene model and project state
  translation.py          Package export, placeholder/terminology checks, and result submission
  build.py                Staged-copy builds, extended paths, and readback verification
  glossary.py             Proper-name candidates, glossary, and style configuration
  text.py / storage.py    Control-code protection, atomic I/O, and path checks
  engines/
    build_steps.py        Shared build lifecycle hook dispatch
    ...                   Detection, candidate scans, extraction, writeback, and fonts
  formats/                Tables, Ruby Marshal, RGSS archives, and WOLF AST parsing
tools/                    Unity Mono, Addressables, WOLF, Godot, and Ren'Py helper guides
tests/                    Local unit-test fixtures and regression checks
```

To understand the code or add an engine, start with `project.py`, then read `translation.py` and `build.py`, followed by `engines/build_steps.py` and the relevant engine adapter. Synchronous Python APIs are exported through `game_translation/__init__.py`.

## License and Acknowledgments

The project is released under the [MIT License](LICENSE).

- **Ruby Marshal parsing and writeback**: `game_translation/formats/marshal.py` is adapted from `plugins/rm_marshal.py` in [MizaGBF/RPGMTL](https://github.com/MizaGBF/RPGMTL), with project-specific changes and fixes. The [upstream MIT notice](game_translation/formats/RPGMTL-LICENSE.txt) is retained in full.
- **Optional external dependencies**: [UnityPy](https://github.com/K0lb3/UnityPy), `TypeTreeGeneratorAPI`, [XUnity.AutoTranslator](https://github.com/bbepis/XUnity.AutoTranslator), [BepInEx](https://github.com/BepInEx/BepInEx), GDRETools, UberWolfCli / WolfTL, and `unrpa` / `unrpyc` are independent external tools or optional packages. Their sources are not bundled with this repository, and each retains its own license. References for Godot binary translation-table handling are listed in the [Godot dependency guide](tools/godot/README.md).
- **Test assets and copyright**: `tests/fixtures/` contains small, self-authored fixtures. Games, fonts, and other commercial assets processed by users remain the property of their respective copyright holders.
