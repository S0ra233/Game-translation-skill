# Game Translation

[简体中文](README.md) | English

A game translation Skill for AI agents that connects engine detection, resource extraction, context organization, translation validation, and writing translations back into a repeatable workflow.

This is an early Skill version. The core handles resources and project state, while the host agent handles translation and decisions that require judgment. Future plans include a desktop interface, visual translation editing, and corpus retrieval built on the same core.

## Workflow

```text
Game directory
  → detect identifies the engine
  → The engine adapter unpacks resources and extracts text
  → The core creates Entries, Tasks, and Scenes
  → Export a translation package in a shared format
  → The host agent translates the text
  → The core validates results and updates task states
  → The engine adapter writes translations into a new game copy
  → Read the extracted locations again and check the written text
```

- **Entry**: The location of a text occurrence in the game resources, used to write translations back accurately.
- **Task**: The source text, translation, and processing state for that occurrence. Identical text at different locations remains separate tasks.
- **Scene**: A context group supplied by an engine adapter, containing ordered task IDs. It may represent an event page, a script label, or a text table—not necessarily a complete narrative scene.

Translation packages use `target_ids` to specify the tasks to translate and `scene_context` to provide text and context without duplicating the same occurrence.

## Current Support

| Engine or resource | Implemented handling | Main limitations |
|---|---|---|
| RPG Maker MV / MZ | Extract supported database fields, system text, and event text; write translations back by JSON path | Plugin scripts, custom fields, and text in images need additional adapters |
| RPG Maker XP / VX / VX Ace | Extract and update supported Ruby Marshal data; read RGSS v1 / v3 archives | Not all event commands or custom data are covered; output uses unpacked resources without re-encrypting the archive |
| TyranoScript | Extract supported dialogue, speaker names, and `text` parameters from `.ks` files; group text by script label | Executable scripts, shorthand commands, and dynamic text are outside the generic extraction scope |
| Unity plain-text resources | Process recognizable JSON, CSV, TSV, and TXT files in StreamingAssets | Generic field rules may not suit every game; grouping does not imply narrative order |
| Unity serialized assets | Use UnityPy to process readable TextAssets and string tables matching supported structures | Private formats, encrypted resources, and unsupported data structures need separate adapters |

Support for additional engines is planned.

## Environment and Dependencies

The basic workflow uses only the Python standard library. It requires no model API key and includes no model API client. The host agent using this Skill provides the model.

- Target environment: Python 3.10 or later.
- Automated examples have passed on Windows with Python 3.14.6. Compatibility with the minimum Python version and other operating systems has not yet been verified.
- Processing Unity serialized assets additionally requires **UnityPy**. It is not needed when working only with RPG Maker, Tyrano, or Unity plain-text tables.

After downloading the project, run the following from its root directory:

```powershell
python --version
python run.py --help
```

If you need UnityPy, installing it in a separate virtual environment is recommended:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install UnityPy
.\.venv\Scripts\python.exe run.py --help
```

The examples below use `python`. If you use the virtual environment above, replace it with `.\.venv\Scripts\python.exe`. Current Unity binary asset tests use mock objects, so they do not establish compatibility between real games and UnityPy versions.

## Using the Skill with an Agent

Give the project directory to an agent that can read local files and run Python commands, and ask it to read [SKILL.md](SKILL.md) first. Keep the entire directory together.

For example:

> Read `<project-directory>/SKILL.md` first and follow its workflow. The original game is in `D:\Games\ExampleGame`, the working directory is `D:\TranslationWork\ExampleGame`, and the output directory is `D:\TranslatedGames\ExampleGame`. Translate into Simplified Chinese.

## Walking Through the Full Workflow

The game names and paths below are examples; replace them with your actual paths. The original game, working directory, and output directory must be separate: they cannot overlap or be nested within one another. Keep working data and game copies outside the project directory when possible.

### 1. Detect and Extract

```powershell
python run.py detect "D:\Games\ExampleGame"
python run.py prepare "D:\Games\ExampleGame" "D:\TranslationWork\ExampleGame"
```

Choose an empty working directory for the first run. `prepare` unpacks resources when needed and generates:

| File | Purpose |
|---|---|
| `project.json` | Engine information, Scene groups, source resource hashes, and project identity |
| `entries.json` | An index of source text locations in the resources |
| `tasks.jsonl` | Source text, translation, and state for each task |
| `proper_nouns.md` | Automatically extracted terminology candidates, refreshed on re-extraction |
| `glossary.md` | Confirmed term mappings and terms awaiting confirmation |
| `style.md` | Target language, character voice, and other translation requirements |

Review the terminology candidates, then add confirmed mappings to `glossary.md`. Use this table format:

```markdown
| Source | Translation | Notes | Status |
|---|---|---|---|
| Alice | 爱丽丝 | Protagonist | confirmed |
| Silver Order | | Organization name, awaiting confirmation | pending |
```

These entries only illustrate the format; use terms from your actual game. To change the target language or translation style, edit `style.md`.

### 2. Export a Translation Package

```powershell
python run.py status "D:\TranslationWork\ExampleGame"
python run.py package "D:\TranslationWork\ExampleGame"
```

By default, this exports the next Scene with tasks awaiting translation. The command returns JSON and saves the package under `packages/` in the working directory.

Give the complete package to the agent. It uses `target_ids` to find target text in `scene_context`, follows the glossary and style, and returns a UTF-8 JSON array:

```json
[
  {
    "id": "actual task ID copied from target_ids",
    "translation": "the corresponding translation",
    "uncertain": false
  }
]
```

Each item contains only these three fields. Preserve source placeholders such as `{p0}` and `{p1}` according to the package rules. Set `uncertain: true` when a name or meaning is unclear.

### 3. Submit Results and Resolve Tasks Needing Review

Assuming the results are saved as `results.json` in the working directory:

```powershell
python run.py apply "D:\TranslationWork\ExampleGame" "actual-package-ID" "D:\TranslationWork\ExampleGame\results.json"
python run.py status "D:\TranslationWork\ExampleGame"
```

The core determines task states through validation:

| State | Meaning |
|---|---|
| `NONE` | Not yet processed |
| `PROCESSED` | Passed the current validation rules and was not marked uncertain by the translator; this does not mean it has received individual human review |
| `NEEDS_HUMAN` | A control-code, terminology, or other validation issue was found, or the translator marked the result uncertain |
| `ERROR` | A processing error, such as a target task missing from the submitted results |

Continue exporting, translating, and submitting until the required Scenes are complete. Use `package WORK --include-review` to include tasks needing review, or select a single task for retranslation as shown below.

### 4. Build a New Game Copy

```powershell
python run.py build "D:\TranslationWork\ExampleGame" "D:\TranslatedGames\ExampleGame"
```

The output directory must not already exist. The build first copies the game into a temporary directory, writes translations, and reads the indexed locations again to verify the result. It creates the final output directory only after these checks pass.

By default, all tasks must pass validation. To preview a partial translation, add `--allow-partial`; tasks that have not passed retain their original text. Results are recorded in `build_report.json` and `verify_report.json` in the working directory.

The build already includes text readback checks, so there is no need to run `verify` immediately afterward. If you later edit output files manually, you can check them again:

```powershell
python run.py verify "D:\TranslationWork\ExampleGame" "D:\TranslatedGames\ExampleGame"
```

Finally, launch the game and check dialogue, choices, fonts, line wrapping, and the interface.

## Retranslation, Resuming Work, and Fonts

### Retranslating a Single Task

```powershell
python run.py package "D:\TranslationWork\ExampleGame" --target "actual-task-ID"
```

This keeps the full Scene context by default. For a long Scene or a local retranslation, you can use neighboring context:

```powershell
python run.py package "D:\TranslationWork\ExampleGame" --target "actual-task-ID" --context neighbors --window 2
```

In this mode, `scene_context` contains only the target. `context_before/context_after` provide neighboring text dynamically, without duplicating it in the Task. Prefer the full Scene when understanding the whole passage matters.

Each package has a default limit of 60,000 characters, adjustable with `--max-chars`.

### Re-extracting and Continuing Work

- Run `prepare` again using the same working directory. Existing translations are retained when the location, source text, and Scene context are unchanged. Existing translations affected by changes are marked for review.
- Task IDs are based on resource locations. Array insertions, line-number changes, or moved text may change task identities; old translations are not automatically transferred to new locations.
- After export, changes to the project index, task states in that Scene, or glossary/style rules may cause an old package to be rejected. Export a new package in that case. Changes to original game files are checked during the build and should be handled by re-extracting first.
- Operations that modify the same working directory must run sequentially. Multiple agents may translate, but one caller should coordinate submissions and project updates.
- The current project format is version 3, and the translation package format is version 2. Older projects require a separate new working directory; version 1 translation packages must be exported again.

### Font Configuration

MV/MZ can use a user-supplied TTF, OTF, WOFF, or WOFF2 file:

```powershell
python run.py build "D:\TranslationWork\ExampleGame" "D:\TranslatedGames\ExampleGame" --font "D:\Fonts\MyFont.ttf"
```

For Unity, use `--tmp-font` to specify a TMP font AssetBundle. The game copy must have the required XUnity.AutoTranslator setup, and the Bundle must be compatible with the target game.

Generic automatic font configuration is not yet available for XP/VX/VX Ace or Tyrano. If no font is specified, the original configuration is retained. The current font functionality handles only copying and configuration.

## Validation and Known Limitations

Run the existing tests from the project root:

```powershell
python -m unittest discover -s tests -v
```

The current 12 automated tests have passed. They cover Scene package submission and writeback, single-task retranslation and stale results, partial translation, format samples, and preservation of original files.

Tests do not call models or include commercial game runtimes. Unity binary asset tests use mock objects. Font samples check copying and configuration, not glyph rendering. The test fixture `translations.json` is a source-to-translation mapping used by the tests.

## Code Structure and Future Plans

```text
run.py                    Command-line entry point
SKILL.md                  Execution instructions for agents
game_translation/
  project.py              Entries, Tasks, Scenes, and project state
  translation.py          Package export, result validation, and submission
  build.py                Game copy construction and text readback checks
  glossary.py             Term candidates, glossary, and style
  text.py / storage.py    Control codes, file storage, and path checks
  engines/                Engine detection, extraction, writeback, and fonts
  formats/                Shared table, Marshal, and RGSS format handling
tests/                    Synthetic samples and minimal regression checks
```

To understand the implementation, start with `project.py`, then read `translation.py` and `build.py`, and finally explore an engine adapter. The core exports a synchronous Python API through `game_translation/__init__.py`.

Future directions include visual translation editing and review, a main agent coordinating translation models or subagents, terminology and corpus retrieval, and additional adapters based on real games.

The project uses AI-assisted development. Its design and the maintainer's understanding of the code continue to evolve.

## License and Third-Party Sources

This project uses the [MIT License](LICENSE).

The Ruby Marshal parser and writer are based on `plugins/rm_marshal.py` from [MizaGBF/RPGMTL](https://github.com/MizaGBF/RPGMTL). The local file is `game_translation/formats/marshal.py`, and the [upstream MIT license text](game_translation/formats/RPGMTL-LICENSE.txt) is retained. This file includes adaptations and fixes made for this project; it is not an unchanged upstream copy. The exact upstream commit was not recorded when it was originally imported, and no verified source revision is claimed.

[UnityPy](https://github.com/K0lb3/UnityPy) is an external dependency installed as needed; its source is not bundled here. Its license and dependency notices are provided with that package. [XUnity.AutoTranslator](https://github.com/bbepis/XUnity.AutoTranslator) and [BepInEx](https://github.com/BepInEx/BepInEx), referenced for font configuration, are also not distributed with this project.

`tests/fixtures/` contains synthetic samples created for this project. User-supplied games, fonts, and other resources retain their respective rights and licenses; using this project does not place those assets under the MIT License.
