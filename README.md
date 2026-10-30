# coo-world-petdiary

Coopanion 桌宠（Coo）的**日记 World 插件**：让 Coo 用 `diary_append` 直接写日记，用户在扩展面板里按公开本 / 私密本回看，并可生成对外分享页。本包只做工具桥接、界面与配置；解析、库、审计链、指纹校验都在独立的 Python 后端（标准库，无第三方依赖）。

- Cortico world：`kind = "world"`，`api = 6`
- npm 包名：`coo-world-petdiary`

## 功能特性

- **公开本 / 私密本**：`public` 本可出现在对外分享页；`private` 本只自留，分享页永远不收录。两本都走同一套工具与审计。
- **Windows 自带运行时**：包内 `runtime/python`（embeddable Python）与 `runtime/diary` 后端脚本；默认库首次使用自动初始化，配置项可全部留空。
- **分类标签**：日常 / 心情 / 想法 / 计划 / 健康 / 游戏 / 交际，可选；不写按关键词推断。
- **三区浏览页**：最近条目、今天写了没、各册与审计计数；公开 / 私密切换；一键构建静态浏览页并用系统浏览器打开。
- **完整性校验**：校验审计哈希链与条目指纹；异常会点名具体条目，只报不修。
- **审计链**：只追加；所有写入走 Python `admin.py`，插件与面板都不自己拼 md。
- **删除留痕**：`diary_delete` 整段移除条目、清掉指纹并写 `delete` 审计；面板对「库外直接删掉」的残留条目提供「确认删除」，不用 `verify --accept`。
- **睡前检查可配置 + 闹钟实时对齐**：配置里的 `bedtimeCheck` 改动后，插件约 1 秒内检测到，并通过内部事件提醒 Coo 用 `alarm_set` 把「睡前检查」闹钟对齐到新时间；插件不直接改 `alarms.json`。还没有睡前检查闹钟时，也会提醒 Coo 先设一个。

## 安装与配置

### 安装

发布后在 Coo 的扩展目录安装（或在扩展页安装）：

```bash
npm install coo-world-petdiary
```

Windows 上**装好即用**：包内自带 Windows embeddable Python 和 `runtime/diary/` 后端脚本，不需要另装 Python，也不需要手动建库。首次打开面板或调用工具时，会自动创建并初始化默认库：

```text
<Coo data>/home/companion/workspace/petdiary/
```

非 Windows 平台没有可用的内置 `python.exe`，会回退到 PATH 里的 `python` / `python3`，需要自备 Python 3.8+；内置 `runtime/diary/` 仍然可用。

### 前置

- Windows：无额外前置。
- 其他平台：Python 3.8+（`python` 或 `python3`）。
- 如果手动指定库根：目录须含 `index.diary`；不要指向 `partner/` 或 `handoffs/`（记忆/交接，不是日记）。

### 配置组 `worlds.pet-diary`

四项都可以留空；留空时按“用户显式配置 > 插件自动默认 > 现有回退链”解析，且**不会把默认值写回 config.json**。

| 配置 | 说明 |
| --- | --- |
| `libraryRoot` | 留空自动使用插件默认库（首次使用自动初始化）；也可填含 `index.diary` 的目录。不能指向 `partner/` 或 `handoffs/`。 |
| `pythonPath` | 留空 Windows 自动使用插件内置 `runtime/python/python.exe`；没有内置时依次试 PATH 里的 `python` / `python3`。 |
| `scriptsDir` | 留空自动使用插件内置 `runtime/diary/`；没有内置时回退到库根同级的 `diary/`。 |
| `bedtimeCheck` | 睡前检查时刻，24 小时制 `HH:MM`，默认 `23:59`；热更新。插件检测到变化后推内部事件让 Coo 用 `alarm_set` 对齐闹钟，不直接写 `alarms.json`。Coo 关着时下次启动再检查。 |
| `partnerAlias` | 主人的习惯称呼，例如 `爬爬`。分类关键词与标题里的说话人识别都按它来；留空按 `主人`。后端也可以用 `diary/alias.json` 的 `{"alias": "…"}` 兜底，环境变量 `PETDIARY_PARTNER_ALIAS` 优先级最高。 |

默认配置示例（全部留空即可）：

```json
{
  "worlds": {
    "pet-diary": {
      "enabled": true,
      "libraryRoot": "",
      "pythonPath": "",
      "scriptsDir": "",
      "bedtimeCheck": "23:59",
      "partnerAlias": ""
    }
  }
}
```

自动默认只基于插件自身位置和 Coo 数据目录推导，不写死任何盘符；用户填了任一项，该项就永远优先。默认库只会在插件使用默认库根、且目录里还没有 `index.diary` 时初始化一次，已有库不会被覆盖。

## 开发 / 贡献

```bash
npm install
npm run build                 # prebuild 会同步 runtime/diary，然后构建 dist/webui.js + .css
npm test                      # 全量单元测试
node scripts/check-world.mjs  # manifest + dryMountWorld；找不到 Cortico 源码时用 CORTICO_SRC 指定
npm pack --dry-run            # 看发布包内容，不发布
```

`runtime/diary/` 是后端脚本副本，开发时从上游后端源码目录同步；`npm run build` 的 `prebuild` 会自动跑 `scripts/sync-runtime.mjs`，也可用 `PETDIARY_BACKEND` 指定源目录。后端改动要同步两处，发布前记得跑一次构建。

目录结构：

```text
src/
  index.ts / definition.ts    World 入口与自描述
  world.ts                   工具桥接、面板、睡前检查、默认配置推导
  defaults.ts                插件目录/data 目录 → 默认 Python、脚本、库根
  alarmSync.ts               只读检查 alarms.json，生成对齐计划
  config.ts                  配置组 schema
  bridge.ts                  调 Python admin.py；默认库自动初始化
  tools.ts                   四个工具声明与参数校验
  panels/                    浏览页面板（构建成 dist/webui.js / .css）
  ENV_PROMPT.md              给 Coo 的环境提示词
runtime/
  python/                    Windows embeddable Python（非 Windows 回退 PATH）
  diary/                     自带后端脚本（admin/parser/store/build/serve 等）
dist/                        面板构建产物（webui.js / webui.css）
assets/                      图标
describe.json                扩展市场/界面用自描述
test/                        node:test 单元测试
scripts/                     构建、runtime 同步与自检脚本（不发布）
```

运行时不带第三方依赖；`esbuild` / `typescript` 只在开发与构建时使用。欢迎提 issue / PR，改动前先跑 `npm test` 与 `npm run build`。

## 许可

MIT，见 [LICENSE](LICENSE)。
