# Game Translation

简体中文 | [English](README.en.md)

这是一个面向 AI Agent 的游戏翻译 Skill，将引擎检测、资源提取、上下文组织、译文校验和写回串成一个可重复执行的流程。

目前是早期的 Skill 版本。核心负责资源处理和项目状态，宿主 Agent 负责翻译与需要判断的部分。后续计划打算在同一套核心上增加桌面界面、译文可视化和语料检索。

## 工作流程

```text
游戏目录
  → detect 检测引擎
  → 对应引擎模块解包、提取文本
  → 核心建立 Entry、Task 和 Scene
  → 导出统一翻译包
  → 宿主 Agent 翻译
  → 核心校验结果、更新任务状态
  → 对应引擎模块写回新的游戏副本
  → 重新读取已提取的位置，核对写回内容
```

- **Entry**：一处文本在游戏资源中的位置，用来准确写回。
- **Task**：这一处文本的原文、译文和处理状态。同一句话出现在不同位置时，保留独立任务。
- **Scene**：由引擎模块提供的上下文分组，保存有序的任务 ID。它可能是事件页、脚本标签或文本表，不一定对应完整的剧情场景。

翻译包用 `target_ids` 指定本次需要翻译的任务，用 `scene_context` 提供文本和上下文，避免重复放入同一处文本。

## 当前支持范围

| 引擎或资源 | 已实现的处理方式 | 主要边界 |
|---|---|---|
| RPG Maker MV / MZ | 提取已适配的数据库字段、系统文本和事件文本；按 JSON 路径写回 | 插件脚本、自定义字段和图片中的文字需要另行适配 |
| RPG Maker XP / VX / VX Ace | 提取和写回已适配的 Ruby Marshal 数据；支持 RGSS v1 / v3 归档读取 | 并非所有事件命令和自定义数据都已覆盖；输出使用解包资源，不重新加密归档 |
| TyranoScript | 提取 `.ks` 中已适配的对白、说话人及 `text` 参数；按脚本标签分组 | 执行脚本、命令简写、动态文本等不属于通用文本提取范围 |
| Unity 明文资源 | 处理 StreamingAssets 中可识别的 JSON、CSV、TSV、TXT | 通用字段规则不保证适合每款游戏；分组不代表剧情顺序 |
| Unity 序列化资产 | 使用 UnityPy 处理可读取的 TextAsset 和符合已适配结构的字符串表 | 私有格式、加密资源及不匹配的数据结构需要单独适配 |

后续会加入其他引擎的适配

## 环境与依赖

基础流程只使用 Python 标准库，不需要配置模型 API Key，也不内置模型调用客户端。模型由使用这个 Skill 的宿主 Agent 提供。

- 代码目标环境：Python 3.10 及以上。
- 当前自动化样例已在 Windows、Python 3.14.6 下通过；最低版本和其他系统尚未完成兼容性验证。
- Unity 序列化资产处理额外需要 **UnityPy**。只处理 RPG Maker、Tyrano 或 Unity 明文表格时，无需安装它。

下载项目后，在项目根目录运行：

```powershell
python --version
python run.py --help
```

需要 UnityPy 时，建议使用独立虚拟环境安装：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install UnityPy
.\.venv\Scripts\python.exe run.py --help
```

后面的示例使用 `python`；如果使用上面的虚拟环境，将它替换为 `.\.venv\Scripts\python.exe`。目前的 Unity 二进制资产测试使用模拟对象，尚不能据此给出真实游戏与 UnityPy 版本的兼容保证。

## 通过 Agent 使用

把项目目录交给能够读取本地文件、执行 Python 命令的 Agent，并让它先阅读 [SKILL.md](SKILL.md)。整个目录都需要保留。

例如：

> 请先阅读 `<项目目录>/SKILL.md`，按其中的流程处理游戏。原游戏目录是 `D:\Games\ExampleGame`，工作目录是 `D:\TranslationWork\ExampleGame`，输出目录是 `D:\TranslatedGames\ExampleGame`。目标语言为简体中文。



## 手动了解完整流程

下面的游戏名和路径均为示例，请替换为实际路径。原游戏、工作目录、输出目录必须互相独立，不能重合或嵌套；工作数据和游戏副本建议放在项目目录之外。

### 1. 检测并提取

```powershell
python run.py detect "D:\Games\ExampleGame"
python run.py prepare "D:\Games\ExampleGame" "D:\TranslationWork\ExampleGame"
```

首次使用请选择空的工作目录。`prepare` 会按需解包并生成：

| 文件 | 用途 |
|---|---|
| `project.json` | 引擎信息、Scene 分组、源资源哈希和项目身份 |
| `entries.json` | 原文在资源中的定位索引 |
| `tasks.jsonl` | 每个任务的原文、译文和状态 |
| `proper_nouns.md` | 自动提取的术语候选，重新提取时会更新 |
| `glossary.md` | 人工确认的术语映射及待确认术语 |
| `style.md` | 目标语言、人物语气和其他翻译要求 |

先查看术语候选，再把确定的映射填入 `glossary.md`。术语表使用如下格式：

```markdown
| 原文 | 译文 | 说明 | 状态 |
|---|---|---|---|
| Alice | 爱丽丝 | 主角 | confirmed |
| Silver Order | | 组织名，待确认 | pending |
```

上面的词条仅用于说明格式，请按实际游戏填写。需要其他目标语言或翻译风格时，可以修改 `style.md`。

### 2. 导出翻译包

```powershell
python run.py status "D:\TranslationWork\ExampleGame"
python run.py package "D:\TranslationWork\ExampleGame"
```

默认导出下一个有待翻译任务的 Scene。命令返回 JSON，并把包保存到工作目录的 `packages/` 中。

将完整翻译包交给 Agent。Agent 按 `target_ids` 从 `scene_context` 找到目标文本，参考术语和风格，返回 UTF-8 JSON 数组：

```json
[
  {
    "id": "从 target_ids 复制的实际任务 ID",
    "translation": "对应的译文",
    "uncertain": false
  }
]
```

每项只包含这三个字段。原文中的 `{p0}`、`{p1}` 等占位符必须按规则保留；名称或语义无法确定时，设置 `uncertain: true`。

### 3. 提交结果并处理待审核任务

假设结果保存为工作目录中的 `results.json`：

```powershell
python run.py apply "D:\TranslationWork\ExampleGame" "实际翻译包ID" "D:\TranslationWork\ExampleGame\results.json"
python run.py status "D:\TranslationWork\ExampleGame"
```

任务状态由核心校验决定：

| 状态 | 含义 |
|---|---|
| `NONE` | 尚未处理 |
| `PROCESSED` | 通过当前规则校验，且没有被译者标记为不确定；不等同于人工逐条审校 |
| `NEEDS_HUMAN` | 控制码、术语或其他校验有问题，或译者标记了不确定 |
| `ERROR` | 当前提交结果缺少目标任务等处理错误 |

继续导出、翻译和提交，直到完成需要处理的 Scene。待审核任务可用 `package WORK --include-review` 导出；也可以按下一节的方式指定单条重翻。

### 4. 写回新副本

```powershell
python run.py build "D:\TranslationWork\ExampleGame" "D:\TranslatedGames\ExampleGame"
```

输出目录必须尚不存在。构建过程先复制到临时目录，写回译文，再按索引重新读取并核对；核验通过后才生成最终输出目录。

默认要求所有任务通过校验。确实需要预览部分译文时，可以加 `--allow-partial`，未通过的任务会保留原文。结果记录在工作目录的 `build_report.json` 和 `verify_report.json` 中。

构建已经包含文本读回检查，无需立即重复运行 `verify`。如果之后人工修改了输出文件，可以重新核对：

```powershell
python run.py verify "D:\TranslationWork\ExampleGame" "D:\TranslatedGames\ExampleGame"
```

最后启动游戏检查对白、选项、字体、换行和界面。

## 重翻、恢复与字体

### 单条重翻

```powershell
python run.py package "D:\TranslationWork\ExampleGame" --target "实际任务ID"
```

默认保留完整 Scene 上下文。长场景或局部重翻可以使用邻近模式：

```powershell
python run.py package "D:\TranslationWork\ExampleGame" --target "实际任务ID" --context neighbors --window 2
```

此时 `scene_context` 只包含目标，`context_before/context_after` 动态提供前后文，不重复存进 Task。涉及整段剧情语义时，优先保留完整 Scene。

每包默认限制为 60000 字符，可通过 `--max-chars` 调整。

### 重新提取和继续工作

- 相同工作目录可以再次 `prepare`。定位、原文和场景上下文未变时保留已有译文；发生变化的已有译文会转为待审核。
- 任务 ID 基于资源位置。数组插入、行号变化或移动文本后，不能保证身份稳定，也不自动把旧译文搬到新位置。
- 导出后，如果项目索引、该 Scene 的任务状态或术语/风格发生变化，旧包可能被拒绝，需要重新导出。原游戏文件变化会在构建时检查，应先重新提取。
- 同一工作目录的修改操作需要串行执行。多 Agent 可以负责翻译，提交和项目更新应由一个调用方协调。
- 当前项目格式为版本 3，翻译包格式为版本 2。旧版项目需使用独立的新工作目录；版本 1 翻译包需重新导出。

### 字体配置

MV/MZ 可以使用用户提供的 TTF、OTF、WOFF 或 WOFF2 文件：

```powershell
python run.py build "D:\TranslationWork\ExampleGame" "D:\TranslatedGames\ExampleGame" --font "D:\Fonts\MyFont.ttf"
```

Unity 可以使用 `--tmp-font` 指定 TMP 字体 AssetBundle，前提是游戏副本中具备所需的 XUnity.AutoTranslator 环境，且 Bundle 与目标游戏兼容。

XP/VX/VX Ace、Tyrano 的字体暂未提供通用自动配置。未指定字体时保持原配置。当前字体功能只负责了复制和设置。

## 验证与已知限制

在项目根目录运行现有测试：

```powershell
python -m unittest discover -s tests -v
```

当前 12 个自动化测试已通过，覆盖 Scene 翻译包提交与写回、单条重翻与过期结果、部分翻译、格式样例和原文件保护等。

测试不调用模型，也不包含商业游戏本体。Unity 二进制资产使用模拟对象；字体样例检查复制和配置，不验证字形渲染。测试数据中的 `translations.json` 是原文到译文的样例映射，供测试使用。



## 代码结构与后续计划

```text
run.py                    命令行入口
SKILL.md                  给 Agent 的执行说明
game_translation/
  project.py              Entry、Task、Scene 和项目状态
  translation.py          翻译包导出、结果校验与提交
  build.py                副本构建与文本读回核验
  glossary.py              术语候选、术语表和风格
  text.py / storage.py    控制码处理、文件存储与路径检查
  engines/                各引擎的检测、提取、写回和字体配置
  formats/                通用表格、Marshal、RGSS 格式处理
tests/                    自编样例和最小回归验证
```

想了解实现，可以先读 `project.py`，再看 `translation.py` 和 `build.py`，最后选择一个引擎模块深入。核心通过 `game_translation/__init__.py` 导出同步 Python 接口。

后续方向包括译文可视化与审核、由主 Agent 协调不同翻译模型或子代理、术语和语料检索，以及针对真实游戏补充适配。

项目采用了 AI 辅助开发，项目设计和代码理解也在持续迭代。

## 许可证与第三方来源

本项目使用 [MIT License](LICENSE)。

Ruby Marshal 解析与写回代码基于 [MizaGBF/RPGMTL](https://github.com/MizaGBF/RPGMTL) 的 `plugins/rm_marshal.py`，本地文件为 `game_translation/formats/marshal.py`，保留 [上游 MIT 许可文本](game_translation/formats/RPGMTL-LICENSE.txt)。该文件包含本项目的适配与修复，不是未经修改的上游副本；早期引入时没有记录准确的上游提交版本，当前不声称已核实该版本。

[UnityPy](https://github.com/K0lb3/UnityPy) 是按需安装的外部依赖，未将其源码打包进本项目；其许可与依赖说明随该软件包提供。字体配置中涉及的 [XUnity.AutoTranslator](https://github.com/bbepis/XUnity.AutoTranslator) 和 [BepInEx](https://github.com/BepInEx/BepInEx) 也未随项目分发。

`tests/fixtures/` 是自编样例。用户提供的游戏、字体和其他资源保留各自的权利与许可，不因使用本项目而转为 MIT 许可。
