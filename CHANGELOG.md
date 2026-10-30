# Changelog

## 0.3.4

- 调整初始提示词"睡前检查"部分：改为到点后用 `diary_read` 查今天两个本子还有什么要写的，空闲就补上；正忙就 `alarm_set` 顺延 15 分钟再查，最多两次。

## 0.3.3

修复 0.3.0 引入的两个工具链回归（新装机 diary_append / diary_read 一律报"退出码 2"）：

- **子命令丢失（主因）**：P5.7 重构后 append/read 的 `admin(cli)` 调用漏传子命令字符串，参数数组被整体嵌套进 argv 并被逗号拼接，argparse 报 "invalid choice"。已在两处调用点补回 `admin('append', cli)` / `admin('read', cli)`，并给 `admin()` 加防御：收到数组/空串/选项串直接抛 TypeError，让这类回归变成响亮失败。
- **默认库根再次翻倍**：宿主 `ctx.dataDir` 实为 `<botDir>/data`（paths.data 是相对路径），不能当数据根用。改为按目录形态识别：插件安装目录向上三级（node_modules/extensions 形态）优先，其次 botDir=<data>/home/companion 向上两级。
- 新增 handler 级回归测试（真实调用 world.tools() 的 diary_append / diary_read，走内置 runtime 全链路）——正是此前单测覆盖缺失的那一层。

## 0.3.2

诊断增强：日记后端以非 0 退出且没有返回 JSON 时（典型如 argparse 用法错误只写 stderr），把后端 stderr 摘要透出到工具错误文本里，不再只报"退出码 2"，现场可直接看到真实原因。

## 0.3.1

修复开箱即用默认值在真实宿主环境下的两个推导错误（0.3.0 在新机器上配置全空时报"找不到日记后端脚本"）：

- 库根翻倍：误用 `dirname(botDir)` 推数据根，得到 `<data>/home` 后再拼 `home/companion/...`；改用宿主直给的 `ctx.dataDir`（`botDir` 上两级仅作兜底）。
- 内置 runtime 找不到：宿主 `ctx.packageDir` 实为 bot 部署目录，不含 `runtime/`；改为按候选探测（`ctx.packageDir` → 模块自身位置），谁有 `runtime/diary/admin.py` 用谁。

## 0.3.0

- 开箱即用：包内新增 `runtime/python`（Windows embeddable Python 3.13）与 `runtime/diary/`（admin/parser/store/build 等后端脚本副本）；`files` 白名单加入 `runtime`。
- `src/defaults.ts`：以插件目录/data 目录推导默认 `pythonPath`、`scriptsDir`、`libraryRoot`；用户显式配置永远优先，默认值不写回 config.json。
- `bridge.ts`：首次使用默认库根时自动 `mkdir` + `admin.py init`；已有 `index.diary` 幂等跳过；初始化写 host 日志。
- `world.ts`：默认值用于 libraryRoot/pythonPath/scriptsDir；面板、ENV_PROMPT、浏览页与工具统一走有效配置。
- `scripts/sync-runtime.mjs` + `prebuild`：开发时把 `agdiary/diary` 同步到 `runtime/diary`；发布包不含 scripts。
- 配置说明与 README 改为“装好即用（Windows）”；非 Windows 回退 PATH 的 python/python3。
- 新增 `test/defaults.test.mjs`：默认推导、回退链、用户覆盖、默认库自动初始化幂等。

## 0.2.9

- 新增 `diary_delete` 工具与 `admin.py delete --entry <id>`：删除是留痕操作，整段移除 md 条目、清掉基线指纹、写 `last_seen` 墓碑并追加 `action=delete` 审计；审计链本身不删。删除前面的条目时，同文件后续条目的基线会随序号前移，避免 verify 误报「消失 + 新增」。
- 面板完整性块区分「被外部修改」与「条目消失」：消失的条目改文案为「已被删除……可点确认删除」，提供「确认删除」按钮，走 `World.invoke('diary','integrity-ack-delete')` → `admin.py delete`，成功后自动刷新；不再需要 `verify --accept` 这种通用接受入口。
- `admin.py verify` 行为不变，仍只报不修；纯基线清理模式只清残留指纹与写删除审计，不动 md。
- 新增 Python `test/test_p56.py` 与插件 `diary_delete` 校验/面板删除测试。

## 0.2.8

- 睡前检查时间改为**配置改动后实时检测**：World 每秒读一次热配置 `bedtimeCheck`，变化时只读 `alarms.json` 并推一条内部事件，让 Coo 用 `alarm_set` 对齐闹钟（不直接写 `alarms.json`——Coo 的 `Alarms` 只在启动时读一次，运行中改文件不会被捡起，且可能被它下一次写回覆盖）。
- 新增 `src/alarmSync.ts`：只读检查、按 note「睡前检查」匹配、比较本地 `HH:MM`、算下一次出现（跨日/时区），文件不存在/损坏/配置坏都不抛异常。
- ENV_PROMPT 睡前检查段去掉“设/对齐闹钟”的职责，只保留到点后的查日记、补写、顺延；移除 `petdiary.bedtime` 变量声明与模板引用。
- 配置「睡前检查时间」说明改为实际机制；`describe.json` 增加 `coopanion.petdiary-alarm-sync` 事件声明。
- 新增 `test/alarmSync.test.mjs`：正常对齐、已一致、文件损坏、无匹配闹钟、文件不存在、跨日、同日、坏配置。

## 0.2.7

- ENV_PROMPT 睡前检查增加对齐规则：已有提醒但时间与配置的 bedtime 不一致时改到配置时间，消除「用户改配置后旧闹钟时间残留」的冲突。

## 0.2.6

- ENV_PROMPT 重写去冗余（删与工具描述重复的字段说明，可见性并入 book 条目，睡前检查压缩为一段）；`petdiary.root` 改用 `{{petdiary.root}}` 模板引用，消除提示词界面「声明未使用」提示。

## 0.2.5

- 新增配置「睡前检查时间」（`worlds.pet-diary.bedtimeCheck`，HH:MM，默认 23:59）：兜底唤醒时刻可由用户在设置界面直接改，不再写死在提示词里；ENV_PROMPT 改用 `{{petdiary.bedtime}}` 模板变量动态渲染。

## 0.2.4

- 浏览页改版：新增起始 / 结束日期筛选；排序只保留时间正序 / 倒序（默认倒序，
  最新在前），移除「类型视图」这一排序维度。
- 公开本 / 私密本改为页面顶部互斥切换，默认只显示公开本；左栏删除
  「本子」筛选块，两本的计数与筛选状态随切换重置。
- 分类枚举改为从页面数据动态生成（来源 `parser.KINDS` / `kinds.json`），
  左栏同步新枚举：日常 / 心情 / 想法 / 计划 / 健康 / 游戏 / 交际 / 未分类；
  页面与样式里的旧枚举（剧情 / 对话 / 结论 / 伏笔 / 操作 / 状态）已清除。
- 历史 md 里的旧标签不重写，按普通文本保留；分类落不到新枚举的条目按
  「未分类」显示。

## 0.2.3

- 新增「游戏」分类（通关 / 关卡 / 存档 / 手感 / 卡关等）。
- 关键词表按桌宠视角校准：散步、买菜、感冒、运动等词条保留——它们多是在描述
  主人的日常，工具描述与 ENV_PROMPT 里已注明这一记法。

## 0.2.2

- 分类（kind）从视觉小说玩法语义改为日常语义：日常 / 心情 / 想法 / 计划 / 健康 / 交际。
- Python 侧 `parser.py` / `kinds.json` 同步新枚举与关键词表；旧标签（如 #操作）
  不再是合法 kind，按关键词回退分类，不报错。

## 0.2.1

- 面板新增「打开浏览页」按钮：一键构建全库浏览页（`build.py --scope all`，
  含私密本，仅本地自用）并用系统默认浏览器打开，产物落在 `<库根>/state/site/index.html`。
- `build.py` 新增 `--scope {public,all}` 参数；缺省 `public`（分享页，行为不变）。

## 0.2.0

- 破坏性语义变更：删除「暂缓」可见性层。条目不再有 `visibility` 字段，工具层不再有
  `diary_flip`，设置面板不再有 `overlayPublicOnly`。
- 语义收敛为两本：public 本整本可分享，会出现在对外分享页面；private 本只自留，
  分享页面硬排除，永远不收录。
- `diary_append` 去掉 `visibility` 参数，描述改为按 public/private 选本。
- World 不再同步 overlay 配置；面板去掉翻可见性按钮与计数。

## 0.1.2

- 去直播化：定位为单纯日记本。「直播贴片」表述全部改为「对外分享/可见」，
  涉及工具描述、ENV_PROMPT、设置面板与 README；overlay 机制本身不变。

## 0.1.1

- P4.2：私密降级为分类，删除面板私密开关、`set-private` 方法与工具层预检；
  `diary_append --private` / `diary_read --scope all` 直接转发 Python。
- 设置面板只保留 `overlayPublicOnly`；贴片仍永远不含私密本。

## 0.1.0

- 首个 P4 包：World 外壳、四个日记工具、bridge、私密开关面板与静态快照。
- Python 侧修复 `| 公开 #操作` 被误判为「暂缓」；新增 public/private 物理分册、
  `admin.py append / mode / private / read / state` 与 `/api/private-toggle`。
