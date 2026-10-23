# Game Translation

简体中文 | [English](README.en.md)

**Game Translation** 是一套专为 AI Agent 协作设计的本地游戏汉化与文本工程工具链。目前已打通 **RPG Maker、WOLF RPG Editor、Unity、Ren’Py、TyranoScript 和 Godot** 六大引擎的提取、候选审查、翻译校验与独立副本写回闭环。

在分工上，本项目采用 **「确定性核心（Core）+ 智能宿主（Agent）」** 的协作模式：

* **Core（底层核心）**：负责二进制解包与资产定位、统一管理翻译状态（Entry / Task / Scene）、严格校验占位符与术语，并在独立暂存区安全写回、逐条读回核验（Verify）。

* **Agent（宿主大模型）**：专注于结合上下文的自然语言翻译、从海量候选中筛选有效文本列（Candidates），以及协助排查私有加密外壳（如 MoleBox VFS）、特殊编码或字体缺失等个案问题。

## 核心设计亮点

* **原游戏 100% 只读保护**：
  原游戏目录全程保持只读，绝不直接修改或污染源文件。构建时先在独立暂存区生成副本，完成写回并通过读回校验后，才原子发布为最终游戏目录（内置 Windows `\\?\` 超长路径支持与文件锁自动退避重试）。若中途失败，系统会保留暂存现场并在 `build_report.json` 中记录阶段信息，方便 Agent 诊断排障。

* **统一的上下文数据模型**：
  抹平不同引擎的资源差异，统一抽象为三层结构：

  * **Entry（定位坐标）**：记录文本在游戏资产中的精确物理位置，确保写回时严丝合缝。

  * **Task（翻译任务）**：管理单条文本的原文、译文与校验状态；相同文本出现在不同位置时保持独立任务，避免误改上下文。

  * **Scene（语境分组）**：按事件页、脚本标签或数据表组织的有序任务集合，让 Agent 始终在完整剧情语境下翻译，而非盲翻孤立词条。

* **先审查、后提取（Candidates 候选机制）**：
  面对 Unity、Godot 或 WOLF 中动辄数万条的代码字面量、多语言数据表和未知字段，支持先运行 `candidates` 导出候选清单，由 Agent 识别并锁定真正的剧情与 UI 字段后再正式建库，避免盲目提取污染上下文或改坏系统常量。

* **写回即核验（100% Read-back Verify）**：
  每次构建新副本时，核心会自动按原坐标重新反序列化读取已写入的文本，逐字段比对预期值。目前已跨 6 大引擎、20 款真实商业与同人游戏（累计 25 万+ 条目）完成全流程写回与 100% 读回一致性验证。

* **实用的排障诊断工具**：
  内置 `locate GAME "已知文本"` 快速反查画面台词存放在哪个底层资产，以及 `fonts GAME REPORT.json` 自动扫描游戏内的字体引用清单。

## 支持引擎与能力范围

| 引擎家族 | 已原生支持的提取与写回能力 | 边界情况与 Agent 辅助项 | 
| ----- | ----- | ----- | 
| **RPG Maker**  (XP / VX / VX Ace / MV / MZ) | • **MV / MZ**：解析并写回数据库 JSON、系统文本与事件脚本，完整保留控制码。  • **XP / VX / VX Ace**：读写 Ruby Marshal（`.rxdata` / `.rvdata2`）；支持 `Game.rgssad` / `Game.rgss3a` 加密归档全自动解密脱壳，直接生成免加密独立副本。 | 插件内部的私有硬编码文本、动态拼接对白及图片文字需个案适配；输出副本直接使用解包资源运行，无需重新打包加密。 | 
| **WOLF RPG Editor**  (绿狼引擎) | • 集成 `UberWolfCli` 与 `WolfTL` 后端，后台自动解包 `.wolf` 加密归档。  • 按 `cp932` AST 精确提取剧情对白、说话人与分支选项，写回后自动重构可独立运行的游戏副本。 | 魔改加密变体或图片文字需 Agent 辅助处理；生成中文副本后需在游戏设置或配置中指定中文字体。详见 [WOLF 使用说明](tools/wolf/README.md)。 | 
| **Unity**  (表格 / 序列化资产 / 代码字符串) | • **表格与内嵌文本**：支持 StreamingAssets 及无扩展名 `TextAsset` 的启发式格式识别（JSON / CSV / TSV / TXT / XML），保留原编码与 BOM。  • **序列化资产**：基于 `UnityPy` 读写 `TextAsset`、Localization `StringTable`、TMP 文本组件、Fungus 及 Utage（宴）`AdvImportBook` 剧情书。  • **代码字面量**：支持 IL2CPP `global-metadata.dat`（v29）字符串池重构与 Mono `Assembly-CSharp.dll`（`ldstr` 指令）汇编级改写。  • **资源与字体**：支持 Addressables 本地 Bundle 的 CRC/大小/catalog 同步，以及 `--font-plan` / `--tmp-font` 字体替换。 | 剥离类型树（Stripped TypeTree）的商业游戏需按需安装 `TypeTreeGeneratorAPI`；Addressables 远程包与自定义 Provider 需人工确认；修改代码内嵌字符串时需注意多处逻辑共用同一索引的情况。详见 [Mono 说明](tools/unity_mono/README.md)、[Addressables 说明](tools/unity_addressables/README.md) 与 [字体说明](tools/unity_fonts.md)。 | 
| **Ren'Py**  (视觉小说引擎) | • 支持松散 `.rpy` 脚本、`.rpa` 归档（`unrpa`）与 `.rpyc` 编译脚本（`unrpyc`）。  • 按官方翻译 ID 与界面词条提取，在输出副本中生成非侵入式的 `game/tl/<language>/` 多语言覆写脚本。 | 深度混淆脚本或运行时动态拼接字符串需 Agent 辅助分析；默认不动原剧本，通过官方多语言层平滑生效。详见 [Ren'Py 使用说明](tools/renpy/README.md)。 | 
| **TyranoScript**  (Web / Electron 视觉小说) | • 支持松散目录或标准 Electron `resources/app.asar` 容器中的 `.ks` 剧本。  • 按脚本标签分组提取对白、说话人及宏参数，写回后重构归档或生成免封包目录并校验字节。 | 复杂 JS 动态逻辑与自定义宏需单独适配；若主程序对 ASAR 带有哈希完整性校验，需配合去除校验或改为松散目录加载。详见 [ASAR 说明](tools/tyrano_asar.md)。 | 
| **Godot Engine**  (3.x / 4.x 封包与场景) | • 集成 `GDRETools` 读写标准 `.pck` 容器与 EXE 内嵌 GDPC 包，支持 `--godot-exe` 消除多包歧义。  • 支持文本/二进制场景节点属性、PO 文件，以及 `OptimizedTranslation`（`.translation`）编译型二进制语言表的哈希桶定位与 UTF-8 缓冲区无损改写。 | 脚本内动态拼接的未注册字符串需先经 `candidates` 审查；多包挂载优先级或特殊第三方壳需 Agent 辅助研判。详见 [Godot 使用说明](tools/godot/README.md)。 | 

## 快速开始：通过 AI Agent 使用

本项目既可以作为独立 CLI 运行，也内置了标准 Skill 规范，可直接交给支持本地文件读写与命令执行的 Agent（如 Claude Code、Cursor、Windsurf 等）托管执行。

* **完整技能入口**：[skills/game-translation/SKILL.md](skills/game-translation/SKILL.md)（仓库根目录的 `SKILL.md` 为兼容旧版保留的跳转入口）。

* **跨环境部署**：将技能复制到其他宿主环境时，请完整拷贝 `skills/game-translation/` 目录。所有命令均支持直接传入绝对路径（如 `python /源码路径/run.py status /工作目录`），无需切换当前工作目录。

### 常用提示词示例

**1. 完整汉化流程**

> 请先阅读 `<项目目录>/skills/game-translation/SKILL.md`，按照其中的规范帮我汉化这款游戏。
>
> * 原游戏目录：`D:\Games\ExampleGame`
>
> * 工作目录：`D:\TranslationWork\ExampleGame`
>
> * 输出目录：`D:\TranslatedGames\ExampleGame`
>
> * 目标语言：简体中文

**2. 局部排查或单条重翻（Agent 会严格按指定范围执行，不会擅自重跑全流程）**

> 游戏里有一句台词“出発の準備はできた？”没翻译出来，请用 `locate` 帮我查一下它在哪个资源文件里，并看看是不是漏提取的候选字段。

## 环境准备与可选依赖

**核心工作流仅需 Python 3.10+ 标准库**，无需配置任何大模型 API Key（翻译能力由宿主 Agent 直接提供）。如果只处理 RPG Maker（全系列）、明文 Ren'Py、基础 TyranoScript 或通用明文表格，克隆仓库后即可直接运行：

```
python --version
python run.py --help

```

### 按需安装的扩展组件

当需要处理 Unity 序列化资产、加密封包或二进制编译脚本时，可按需配置以下扩展工具（未安装时仅在对应引擎下给出友好提示，不影响其他功能）：

| 适用引擎 | 依赖或工具 | 用途与配置方式 | 
| ----- | ----- | ----- | 
| **Unity** | `UnityPy` (pip) | 读写 Unity 序列化资产（`TextAsset`、`StringTable` 等）。建议使用虚拟环境安装：`pip install UnityPy`。 | 
| **Unity** | `TypeTreeGeneratorAPI` (pip) | 解析剥离了类型树（Stripped TypeTree）的商业游戏资产结构：`pip install TypeTreeGeneratorAPI`。 | 
| **Unity** | `UnityMono.exe` (dnlib) | 修改 Mono 架构 `Assembly-CSharp.dll` 中的 `ldstr` 字符串指令。详见 [tools/unity_mono/](tools/unity_mono/README.md)。 | 
| **Unity** | Addressables 辅助工具 | 同步本地 Bundle 的 CRC、大小与 catalog 缓存标识。详见 [tools/unity_addressables/](tools/unity_addressables/README.md)。 | 
| **Godot** | `gdre_tools.exe` (GDRETools) | 解包与重构 `.pck` 容器、转换二进制场景。配置环境变量 `$env:GAME_TRANSLATION_GDRE` 或放入 `tools/godot/bin/`。详见 [Godot 说明](tools/godot/README.md)。 | 
| **WOLF** | `UberWolfCli.exe` & `WolfTL` | 解密 `.wolf` 归档并导出/修补 AST。放入 `tools/wolf/bin/` 或加入系统 `PATH`。详见 [WOLF 说明](tools/wolf/README.md)。 | 
| **Ren'Py** | `unrpa` & `unrpyc` | 解包 `.rpa` 归档与反编译 `.rpyc` 脚本。可通过 pip 安装或参考 [Ren'Py 说明](tools/renpy/README.md)。 | 
| **Tyrano** | Node.js `asar` / 内置解析 | 读取与重构 Electron `app.asar` 归档。详见 [ASAR 说明](tools/tyrano_asar.md)。 | 

## 手动命令行全流程指南

整体数据流遵循以下标准闭环：

```
原游戏目录 (只读)
  ├─ 1. detect / candidates ──→ 识别引擎与审查可疑候选字段
  ├─ 2. prepare             ──→ 解包提取文本，建立 Entry / Task / Scene 与术语候选
  ├─ 3. package             ──→ 按 Scene 导出待翻译 JSON 包
  ├─ 4. 宿主 Agent 翻译      ──→ 结合上下文、术语表与风格指南生成译文
  ├─ 5. apply               ──→ 校验占位符与格式，更新任务状态
  └─ 6. build & verify      ──→ 在独立副本写回译文，并逐条重读核验 100% 一致性

```

> **路径安全要求**：原游戏目录、工作目录（`WORK`）、输出目录（`OUTPUT`）三者必须完全独立，不可重合或互相嵌套。

### 第一步：检测引擎与提取文本 (`detect` / `prepare`)

```
python run.py detect "D:\Games\ExampleGame"
python run.py prepare "D:\Games\ExampleGame" "D:\TranslationWork\ExampleGame"

```

首次运行请指定一个空的工作目录。`prepare` 完成后会在工作目录下生成以下工程文件：

| 文件名 | 说明 | 
| ----- | ----- | 
| `project.json` | 记录引擎信息、Scene 分组结构、源文件哈希与工程版本（当前为 v3） | 
| `entries.json` | 每处文本在原始游戏资产中的精确定位索引 | 
| `tasks.jsonl` | 所有翻译任务的原文、译文及当前状态 | 
| `proper_nouns.md` | 自动扫描提取的高频专有名词候选（重新提取时会自动更新） | 
| `glossary.md` | 供人工与 Agent 维护的正式术语表 | 
| `style.md` | 目标语言、角色人称语气及排版风格约定 | 

在开始大批量翻译前，建议先查看 `proper_nouns.md`，将确认的译名填入 `glossary.md`：

```
| 原文 | 译文 | 说明 | 状态 |
|---|---|---|---|
| Alice | 爱丽丝 | 主角 | confirmed |
| Silver Order | | 组织名，待结合剧情确认 | pending |

```

### 第二步：导出翻译包 (`package`)

```
python run.py status "D:\TranslationWork\ExampleGame"
python run.py package "D:\TranslationWork\ExampleGame"

```

默认按顺序导出下一个包含未完成任务的 Scene，并保存在工作目录的 `packages/` 下（单包默认上限 `60,000` 字符，可通过 `--max-chars` 调整）。

翻译包结构清晰区分了**待翻译目标**与**上下文参考**：

* `target_ids`：本次真正需要提交译文的任务 ID 列表。

* `scene_context`：提供该场景的前后文台词，帮助 Agent 把握对话语境，同时避免重复翻译相同句子。

Agent 完成翻译后，只需生成如下格式的 UTF-8 JSON 数组文件（例如 `results.json`）：

```
[
  {
    "id": "从 target_ids 复制的任务 ID",
    "translation": "对应的中文译文",
    "uncertain": false
  }
]

```

> **校验规则**：原文中的 `{p0}`、`{p1}` 等控制码占位符必须原样保留；若遇到语境不明或人名存疑的句子，可将 `uncertain` 设为 `true`，交由后续审校处理。

### 第三步：提交译文与状态流转 (`apply`)

```
python run.py apply "D:\TranslationWork\ExampleGame" "翻译包ID" "D:\TranslationWork\ExampleGame\results.json"
python run.py status "D:\TranslationWork\ExampleGame"

```

提交后，Core 会自动检查占位符、控制码与术语一致性，并将每条任务更新为以下状态之一：

* **`NONE`**：尚未翻译。

* **`PROCESSED`**：已通过规则校验且未标记 `uncertain`（代表工程校验通过，不等同于人工润色完毕）。

* **`NEEDS_HUMAN`**：占位符/术语校验未通过，或被 Agent 标记为 `uncertain: true`，需复核。

* **`ERROR`**：提交结果缺失目标 ID 或格式异常。

若需专门导出 `NEEDS_HUMAN` 状态的词条进行复核，可使用：

```
python run.py package "D:\TranslationWork\ExampleGame" --include-review

```

### 第四步：构建新游戏副本与读回核验 (`build` / `verify`)

```
python run.py build "D:\TranslationWork\ExampleGame" "D:\TranslatedGames\ExampleGame"

```

* **默认全量校验**：默认要求所有任务均处于 `PROCESSED` 状态才允许构建。若希望在半成品阶段先行进游戏预览首屏效果，可附带 `--allow-partial` 参数（未完成词条将安全保留原文）。

* **内置读回核验**：`build` 过程已自动包含完整的 `verify` 读回检查，结果保存在工作目录的 `build_report.json` 与 `verify_report.json` 中。若后续手动微调了输出目录的文件，也可单独运行核验：

```
python run.py verify "D:\TranslationWork\ExampleGame" "D:\TranslatedGames\ExampleGame"

```

## 进阶操作：单条重翻、增量续译与字体替换

### 1. 定向单条重翻

实机测试时发现某句台词不通顺，可直接按任务 ID 导出单条重翻包（默认附带完整 Scene 上下文）：

```
python run.py package "D:\TranslationWork\ExampleGame" --target "任务ID"

```

若所在 Scene 极长、只需看前后几句语境，可切换为邻近窗口模式：

```
python run.py package "D:\TranslationWork\ExampleGame" --target "任务ID" --context neighbors --window 2

```

### 2. 增量提取与工程续译

* **保留已有进度**：对同一工作目录再次运行 `prepare` 时，只要条目定位、原文及场景上下文未发生变动，已有的译文会自动保留；原文发生变动的条目会自动转为 `NEEDS_HUMAN` 待审状态。

* **并发与版本约定**：多个子 Agent 可以并行翻译不同的翻译包，但对同一工作目录的 `apply` 提交操作应串行执行。当前工程格式为 `v3`、翻译包格式为 `v2`。

### 3. 字体扫描与配置

* **扫描字体引用**：运行 `python run.py fonts "D:\Games\ExampleGame" "D:\TranslationWork\fonts_report.json"` 可导出游戏内引用的字体资产清单。

* **RPG Maker MV / MZ**：构建时可通过 `--font "D:\Fonts\MyFont.ttf"` 直接注入 TTF / OTF / WOFF / WOFF2 字体。

* **Unity**：支持通过 `--font-plan` 按规则替换 TTF/OTF 或 TMP 字体资产，或在配置了 `XUnity.AutoTranslator` 的环境下使用 `--tmp-font` 挂载兼容的 TMP AssetBundle（详见 [Unity 字体说明](tools/unity_fonts.md)）。

> [!IMPORTANT]
> **关于「100% 读回一致」与「实机显示效果」的说明**：
> 构建报告中的 `100% 读回核验通过` 代表底层工程写回无字节损坏、无偏移错位；但游戏的实际汉化体验还取决于**主线剧本是否全部纳入候选提取**、**多语言游戏是否覆盖了当前系统生效的语言列**，以及**实机字体是否缺字、对话框是否溢出折行**。完成构建后，请务必启动输出副本进行实机首屏与主线走查。

## 项目结构

```
run.py                    CLI 命令行统一入口
SKILL.md                  根目录兼容入口（实际跳转至 skills/game-translation/SKILL.md）
skills/game-translation/  完整 Agent 技能定义与各引擎/宿主参考文档
game_translation/
  project.py              Entry、Task、Scene 数据模型与工程状态管理
  engines/build_steps.py  跨引擎构建生命周期钩子调度
  translation.py          翻译包导出、占位符/术语校验与结果提交
  build.py                安全暂存副本构建、长路径兼容与读回核验
  glossary.py             高频专有名词提取、术语表与风格配置
  text.py / storage.py    控制码保护、原子文件读写与路径安全检查
  engines/                六大引擎的检测、候选扫描、提取、写回与字体适配器
  formats/                通用表格、Ruby Marshal、RGSS 归档与 WOLF AST 解析
tools/                    Unity Mono、Addressables、WOLF、Godot、Ren'Py 等辅助工具链说明
tests/                    单元测试样例与回归验证套件

```

如果想阅读源码或扩展新引擎，建议从 `project.py` 入手了解核心数据结构，接着阅读 `translation.py` 与 `build.py`（含 `engines/build_steps.py` 钩子分发），最后参考 `engines/` 下的具体引擎适配器。核心功能同时通过 `game_translation/__init__.py` 暴露同步 Python API。

## 开源许可与致谢

本项目基于 [MIT License](LICENSE) 开源。

* **Ruby Marshal 解析与写回**：`game_translation/formats/marshal.py` 修改自 [MizaGBF/RPGMTL](https://github.com/MizaGBF/RPGMTL) 的 `plugins/rm_marshal.py`，包含本项目的适配与修复，并完整保留 [上游 MIT 许可声明](game_translation/formats/RPGMTL-LICENSE.txt)。

* **外部按需依赖**：[UnityPy](https://github.com/K0lb3/UnityPy)、`TypeTreeGeneratorAPI`、[XUnity.AutoTranslator](https://github.com/bbepis/XUnity.AutoTranslator)、[BepInEx](https://github.com/BepInEx/BepInEx)、GDRETools、UberWolfCli / WolfTL 及 `unrpa` / `unrpyc` 等均为外部独立工具或按需安装的软件包，未将其源码打包进本仓库，各自遵循其原始开源许可。Godot 二进制翻译表修改等参考来源详见 [Godot 依赖说明](tools/godot/README.md)。

* **测试资产与版权声明**：仓库内的 `tests/fixtures/` 均为自编最小测试样例。用户使用本工具处理的游戏本体、字体及其他商业资产均归原著作权人所有。