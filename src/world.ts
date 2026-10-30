import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { Language } from 'cortico/core/language.ts';
import type {
  ToolDef,
  ToolOutcome,
  World,
  WorldHost,
  WorldLamp,
  WorldStreamSocket,
  WorldWebUiDecl,
} from 'cortico/core/types.ts';
import { failureText, runAdmin, runBuildSite, type BridgeFailure, type BridgeResult, type RunOptions } from './bridge.ts';
import { ALARM_SYNC_EVENT, normalizeBedtime, planBedtimeAlarm } from './alarmSync.ts';
import { configGroups, PET_DIARY_ID, type PetDiarySection } from './config.ts';
import { applyDefaults, modulePackageDir, resolveDefaults, type PetDiaryDefaults } from './defaults.ts';
import { text } from './i18n.ts';
import {
  summarizeVerify,
  type IntegritySummary,
  type VerifyJson,
} from './integrity.ts';
import {
  PET_DIARY_TOOL_DECLS,
  validateAppendArgs,
  validateDeleteArgs,
  validateReadArgs,
} from './tools.ts';

const ENV_PROMPT = fileURLToPath(new URL('./ENV_PROMPT.md', import.meta.url));

export interface PetDiaryWorldOptions {
  cfg: PetDiarySection;
  /** 宿主给的包目录；实际是 bot 部署目录，仅作内置 runtime 探测的候选之一。 */
  packageDir: string;
  /** 部署目录；alarms.json 与 config.json 同级。 */
  botDir: string;
  /** 宿主数据根（config.paths.data，如 <Coopanion>/data）；默认库根以它为基准。 */
  dataDir?: string;
  /** 模块自身所在包目录；仅在测试 bundle 脱离真实安装位置时注入。默认用 import.meta.url 推导。 */
  moduleDir?: string;
  /** Coo 的时区，用来把 epoch at 读成 HH:MM。 */
  timezone: string;
}

type Json = Record<string, unknown>;

/** verify 子进程至少隔这么久才再跑一次；面板 1 秒轮询不会拖垮机器。 */
const INTEGRITY_TTL_MS = 60_000;

/** 闹钟文件最多 60 秒重读一次；配置值变化时不走这个 TTL，立即重读。 */
const ALARM_SYNC_TTL_MS = 60_000;

/** 每秒看一眼热配置；配置没变就不碰 alarms.json。 */
const ALARM_TICK_MS = 1_000;

/** 面板 state：Python 的 /api/state 原样 + 配置态 + 完整性摘要。 */
export type DiaryPanelState = Json & {
  ok: boolean;
  configured: boolean;
  error?: string;
  hint?: string;
  integrity?: IntegritySummary;
};

export class PetDiaryWorld implements World {
  readonly id = PET_DIARY_ID;
  private host: WorldHost | null = null;
  /** 完整性查询结果缓存；失败也缓存，避免 Python 不在时每秒起子进程。 */
  private integrityCache: { at: number; value: IntegritySummary } | null = null;
  /** 同一个 tick 里的并发调用共用一次查询。 */
  private integrityInFlight: Promise<IntegritySummary> | null = null;
  /** 闹钟同步的定时器与去重状态。 */
  private alarmTimer: ReturnType<typeof setInterval> | null = null;
  private lastAlarmBedtime: string | null = null;
  private lastAlarmReadAt = 0;
  private lastAlarmNoticeKey: string | null = null;

  constructor(private readonly opts: PetDiaryWorldOptions) {}

  private get cfg(): PetDiarySection {
    return this.opts.cfg;
  }

  /** 插件目录 + Coo 数据目录推导出的默认值；用户配置永远优先。
   *
   * 两个宿主上下文陷阱（P5.7 实测踩坑后修正）：
   * - ctx.dataDir 才是数据根（botDir 的 dirname 是 <data>/home，再拼 home/ 会翻倍）；
   * - ctx.packageDir 是 bot 部署目录，内置 runtime 只在插件包安装目录
   *   （模块自身位置）；因此按候选顺序探测谁真有 runtime/diary/admin.py。
   */
  private defaults(): PetDiaryDefaults {
    const pkg = [this.opts.packageDir, this.opts.moduleDir ?? modulePackageDir()].find((dir) =>
      existsSync(join(dir, 'runtime', 'diary', 'admin.py')),
    );
    return resolveDefaults(pkg ?? this.opts.moduleDir ?? modulePackageDir(), this.dataRoot());
  }

  /**
   * Coopanion 数据根（<root>/data）。实测两个宿主字段都不能直接信：
   * - ctx.dataDir = abs(config.paths.data)，而 paths.data 是相对 botDir 的 'data'，
   *   实际得到 <botDir>/data，再拼 home/companion/... 会翻倍（0.3.2 现场日志实证）；
   * - ctx.packageDir = bot 部署目录，不是插件安装目录。
   * 因此按目录形态识别：插件安装目录向上三级（node_modules/extensions 形态）优先，
   * 其次 botDir=<data>/home/companion 向上两级；都对不上才退回 ctx.dataDir。
   */
  private dataRoot(): string | undefined {
    const pkg = resolve(this.opts.moduleDir ?? modulePackageDir());
    if (basename(dirname(pkg)) === 'node_modules' && basename(dirname(dirname(pkg))) === 'extensions') {
      return dirname(dirname(dirname(pkg)));
    }
    const bot = this.opts.botDir ? resolve(this.opts.botDir) : undefined;
    if (bot && basename(bot) === 'companion' && basename(dirname(bot)) === 'home') {
      return dirname(dirname(bot));
    }
    return this.opts.dataDir;
  }

  private effectiveCfg(): PetDiarySection {
    return applyDefaults(this.cfg, this.defaults()).cfg;
  }

  private admin<T = Record<string, unknown>>(
    command: string,
    args: string[] = [],
    opts: RunOptions = {},
  ): Promise<BridgeResult<T>> {
    if (Array.isArray(command) || !command || command.startsWith('-')) {
      // 0.3.2 现场：admin(cli) 漏传子命令，数组被逗号拼成 argv[1]，argparse 报退出码 2。
      // 这里直接抛错，把这类回归变成响亮失败。
      throw new TypeError(`pet-diary 内部错误：admin() 缺少子命令（收到 ${JSON.stringify(command).slice(0, 60)}）`);
    }
    return runAdmin<T>(this.cfg, command, args, {
      ...opts,
      defaults: opts.defaults ?? this.defaults(),
      log: opts.log ?? ((message) => this.host?.log.info(message)),
    });
  }

  async envPromptVars(): Promise<Record<string, string> | null> {
    const root = this.effectiveCfg().libraryRoot.trim();
    if (!root) return null;
    this.syncBedtimeAlarm();
    return { 'petdiary.root': root };
  }

  /**
   * 配置是活对象（WorldContext.cfg），每秒看一次 bedtimeCheck。
   * 配置没变且离上次读盘不到 60 秒，就不碰 alarms.json；变化时立即读并推事件。
   */
  private syncBedtimeAlarm(force = false): void {
    const host = this.host;
    if (!host) return;
    if (!this.effectiveCfg().libraryRoot.trim()) {
      this.lastAlarmBedtime = null;
      this.lastAlarmNoticeKey = null;
      return;
    }

    const rawBedtime = this.cfg.bedtimeCheck.trim() || '23:59';
    const bedtime = normalizeBedtime(rawBedtime) ?? rawBedtime;
    const now = Date.now();
    const bedtimeChanged = bedtime !== this.lastAlarmBedtime;
    if (!force && !bedtimeChanged && now - this.lastAlarmReadAt < ALARM_SYNC_TTL_MS) return;
    // 配置换了就允许为新时间再推一次；同一个时间反复出现则由 lastAlarmNoticeKey 去重。
    if (bedtimeChanged) this.lastAlarmNoticeKey = null;

    this.lastAlarmBedtime = bedtime;
    this.lastAlarmReadAt = now;
    let plan: ReturnType<typeof planBedtimeAlarm>;
    try {
      plan = planBedtimeAlarm({
        alarmsPath: join(this.opts.botDir, 'alarms.json'),
        bedtime: rawBedtime,
        timezone: this.opts.timezone,
        now,
      });
    } catch (error) {
      host.log.warn('[pet-diary] 检查睡前检查闹钟失败', error);
      return;
    }

    if (plan.log) host.log.warn(`[pet-diary] ${plan.log}`);
    if (plan.action === 'notify') {
      if (plan.key === this.lastAlarmNoticeKey) return;
      this.lastAlarmNoticeKey = plan.key;
      try {
        host.pushDeferred(
          {
            type: ALARM_SYNC_EVENT,
            origin: 'internal',
            render: () => plan.text,
          },
          { trigger: 'flush' },
        );
      } catch (error) {
        host.log.warn('[pet-diary] 推送睡前检查对齐事件失败', error);
      }
      return;
    }
    if (plan.reason === 'aligned') this.lastAlarmNoticeKey = null;
  }

  /**
   * 轻量完整性查询：复用 bridge 跑 `admin.py verify --json`，只取汇总。
   * 结果缓存 60 秒（失败也缓存），并发调用共用一次子进程。
   */
  async integrity(): Promise<IntegritySummary> {
    const cached = this.integrityCache;
    if (cached && Date.now() - cached.at < INTEGRITY_TTL_MS) return cached.value;
    if (this.integrityInFlight) return this.integrityInFlight;

    const pending = this.queryIntegrity()
      .then((value) => {
        this.integrityCache = { at: Date.now(), value };
        return value;
      })
      .finally(() => {
        if (this.integrityInFlight === pending) this.integrityInFlight = null;
      });
    this.integrityInFlight = pending;
    return pending;
  }

  private async queryIntegrity(): Promise<IntegritySummary> {
    const result = await this.admin<VerifyJson>('verify');
    return summarizeVerify(result);
  }

  tools(): ToolDef[] {
    const byName = new Map(PET_DIARY_TOOL_DECLS.map((decl) => [decl.name, decl]));
    const pick = (name: string) => {
      const decl = byName.get(name);
      if (!decl) throw new Error(`缺少工具声明：${name}`);
      return decl;
    };

    return [
      {
        ...pick('diary_append'),
        handler: (args) => this.append(args),
      },
      {
        ...pick('diary_read'),
        handler: (args) => this.read(args),
      },
      {
        ...pick('diary_verify'),
        handler: () => this.verify(),
      },
      {
        ...pick('diary_delete'),
        handler: (args) => this.delete(args),
      },
    ];
  }

  private failure(result: BridgeFailure): ToolOutcome {
    return { text: failureText(result), failed: true };
  }

  private async append(args: Record<string, unknown>): Promise<ToolOutcome> {
    const checked = validateAppendArgs(args);
    if (!checked.ok) return { text: checked.error, failed: true };
    const value = checked.value;
    const cli = [
      '--book', value.book,
      '--time', value.time,
      '--title', value.title,
      '--body', value.body,
    ];
    if (value.kind) cli.push('--kind', value.kind);
    if (value.private) cli.push('--private');

    const result = await this.admin<{
      entry: string;
      path: string;
      audit_seq: number;
      heading: string;
      private: boolean;
    }>('append', cli);
    if (!result.ok) return this.failure(result);
    const data = result.data;
    const number = data.entry.includes('#') ? data.entry.slice(data.entry.lastIndexOf('#') + 1) : '';
    return {
      text:
        `已写入 ${data.private ? 'private' : 'public'} 本${number ? ` #${number}` : ''}\n`
        + `落盘：${data.path}；审计 seq=${data.audit_seq}`,
    };
  }

  private async read(args: Record<string, unknown>): Promise<ToolOutcome> {
    const checked = validateReadArgs(args);
    if (!checked.ok) return { text: checked.error, failed: true };
    const value = checked.value;
    const cli = ['--scope', value.scope, '--limit', String(value.limit)];
    if (value.book) cli.push('--book', value.book);

    const result = await this.admin<{
      today: { date: string; count: number };
      counts: Record<string, number>;
      total: number;
      entries: Array<Record<string, unknown>>;
      private_count?: number;
    }>('read', cli);
    if (!result.ok) return this.failure(result);
    const data = result.data;
    const lines: string[] = [];
    const today = data.today;
    lines.push(today.count > 0 ? `今天已经写了 ${today.count} 条（${today.date}）` : '今天还没写。');
    const counts = Object.entries(data.counts ?? {})
      .map(([book, count]) => `${book} ${count}`)
      .join(' · ');
    if (counts) lines.push(`各册：${counts}`);
    if (typeof data.private_count === 'number') lines.push(`私密本 ${data.private_count} 条`);
    if (data.entries?.length) {
      lines.push('最近：');
      for (const entry of data.entries) {
        const flag = entry.shelf === 'private' ? ' [私密]' : '';
        lines.push(
          `- ${String(entry.date ?? '')} ${String(entry.time ?? '—')} `
          + `${String(entry.title ?? '')}（${String(entry.kind ?? '未分类')}）${flag}`,
        );
      }
    } else {
      lines.push('没有符合条件的条目。');
    }
    return { text: lines.join('\n') };
  }

  private async verify(): Promise<ToolOutcome> {
    const result = await this.admin<{
      summary?: string;
      issues?: string[];
      audit_count?: number;
      fingerprint_count?: number;
    }>('verify');
    if (!result.ok) return this.failure(result);
    return {
      text: result.data.summary
        ?? `正常 ${result.data.audit_count ?? 0} 条审计 / ${result.data.fingerprint_count ?? 0} 条指纹`,
    };
  }

  private async removeEntry(entryId: string) {
    const result = await this.admin<{
      entry: string;
      mode: 'deleted' | 'baseline';
      path: string;
      heading?: string;
      audit_seq?: number;
      hash_removed?: boolean;
    }>('delete', ['--entry', entryId]);
    if (result.ok) this.integrityCache = null;
    return result;
  }

  private deleteMessage(data: {
    entry: string;
    mode: 'deleted' | 'baseline';
    audit_seq?: number;
  }): string {
    const baseline = data.mode === 'baseline'
      ? '（md 里本来就没有这条，已清掉残留指纹）'
      : '';
    return `已确认删除 ${data.entry}${baseline}；审计 seq=${data.audit_seq ?? '?'}（action=delete）`;
  }

  private async delete(args: Record<string, unknown>): Promise<ToolOutcome> {
    const checked = validateDeleteArgs(args);
    if (!checked.ok) return { text: checked.error, failed: true };
    const result = await this.removeEntry(checked.value.entry_id);
    if (!result.ok) return this.failure(result);
    return { text: this.deleteMessage(result.data) };
  }

  async start(host: WorldHost): Promise<void> {
    // 不在这里探测库：首次 invoke('diary','state') 时懒加载。start 只保存宿主。
    this.host = host;
    if (this.alarmTimer) clearInterval(this.alarmTimer);
    this.syncBedtimeAlarm(true);
    this.alarmTimer = setInterval(() => this.syncBedtimeAlarm(), ALARM_TICK_MS);
  }

  async stop(): Promise<void> {
    if (this.alarmTimer) clearInterval(this.alarmTimer);
    this.alarmTimer = null;
    this.host = null;
  }

  webUi(language: Language = 'zh'): WorldWebUiDecl {
    const w = text(language);
    const effective = this.effectiveCfg();
    const root = effective.libraryRoot.trim();
    const usingDefault = !this.cfg.libraryRoot.trim();
    const lamp: WorldLamp = !root
      ? { label: '日记库', state: 'offline', hint: '还没有可用的库根' }
      : existsSync(join(root, 'index.diary'))
        ? { label: '日记库', state: 'online', hint: root }
        : {
            label: '日记库',
            state: 'error',
            hint: usingDefault ? '默认库将在首次使用时自动初始化' : '库根缺少 index.diary',
          };
    return {
      label: w.worldLabel,
      lamps: [lamp],
      panels: [{
        id: 'diary',
        title: w.panelTitle,
        description: w.panelDescription,
        getMethods: ['state'],
      }],
      invoke: (panel, method, args) => this.invoke(panel, method, args),
      stream: (panel, socket) => this.stream(panel, socket),
      promptDocs: [{
        key: `worlds.${PET_DIARY_ID}.envPrompt`,
        title: w.envTitle,
        description: w.envDescription,
        path: ENV_PROMPT,
        role: 'envPrompt',
        vars: [
          { name: 'petdiary.root', description: '日记库根的绝对路径。' },
        ],
      }],
      config: configGroups(),
    };
  }

  async invoke(panel: string, method: string, args: unknown[]): Promise<unknown> {
    if (panel !== 'diary') throw new Error(`未知面板：${panel}`);
    switch (method) {
      case 'state':
        return this.panelState();
      case 'verify':
        return this.verify();
      case 'integrity':
        return this.integrity();
      case 'integrity-ack-delete': {
        const entryId = typeof args[0] === 'string' ? args[0].trim() : '';
        if (!entryId) return { ok: false, failed: true, text: 'entry_id 不能为空' };
        const result = await this.removeEntry(entryId);
        if (!result.ok) return { ok: false, failed: true, text: failureText(result) };
        return {
          ok: true,
          entry: entryId,
          mode: result.data.mode,
          text: this.deleteMessage(result.data),
        };
      }
      case 'openSite':
        return this.openSite();
      default:
        throw new Error(`未知方法：${method}`);
    }
  }

  /** 一次 1 秒轮询；连接关闭就停。 */
  private stream(panel: string, socket: WorldStreamSocket): void {
    if (panel !== 'diary') {
      socket.close('未知面板');
      return;
    }
    let busy = false;
    let stopped = false;
    const tick = async () => {
      if (busy || stopped) return;
      busy = true;
      try {
        const state = await this.panelState();
        if (!stopped && socket.open) socket.send(JSON.stringify({ type: 'state', state }));
      } catch {
        // 下一轮再试；不把异常正文推给浏览器。
      } finally {
        busy = false;
      }
    };
    void tick();
    const timer = setInterval(() => { void tick(); }, 1000);
    socket.onClose(() => {
      stopped = true;
      clearInterval(timer);
    });
  }

  private async panelState(): Promise<DiaryPanelState> {
    const w = text();
    const effective = this.effectiveCfg();
    if (!effective.libraryRoot.trim()) {
      return { ok: false, configured: false, error: w.noRoot, integrity: await this.integrity() };
    }
    this.syncBedtimeAlarm();
    const result = await this.admin<{ state: Json }>('state');
    const integrity = await this.integrity();
    if (!result.ok) {
      return {
        ok: false,
        configured: true,
        error: result.error,
        hint: result.hint,
        integrity,
      };
    }
    return {
      ...(result.data.state ?? {}),
      ok: true,
      configured: true,
      integrity,
    } as DiaryPanelState;
  }

  /** 构建全库浏览页（含私密本，仅本地）并用系统默认浏览器打开。 */
  private async openSite(): Promise<Json> {
    const effective = this.effectiveCfg();
    if (!effective.libraryRoot.trim()) {
      return { ok: false, error: text('zh').noRoot };
    }
    // 先走 state：默认库不存在时会在这里完成 mkdir + init。
    const prepared = await this.admin<{ state: Json }>('state');
    if (!prepared.ok) return { ok: false, error: failureText(prepared) };
    const outDir = join(effective.libraryRoot.trim(), 'state', 'site');
    const result = await runBuildSite(this.cfg, outDir, {
      defaults: this.defaults(),
      log: (message) => this.host?.log.info(message),
    });
    if (!result.ok) {
      return { ok: false, error: failureText(result) };
    }
    this.launchBrowser(result.htmlPath);
    return { ok: true, path: result.htmlPath };
  }

  /** 用系统默认程序打开文件；开不了也不报错，路径已返回给面板。 */
  private launchBrowser(htmlPath: string): void {
    try {
      if (process.platform === 'win32') {
        spawn('explorer', [htmlPath], { detached: true, stdio: 'ignore' }).unref();
      } else if (process.platform === 'darwin') {
        spawn('open', [htmlPath], { detached: true, stdio: 'ignore' }).unref();
      } else {
        spawn('xdg-open', [htmlPath], { detached: true, stdio: 'ignore' }).unref();
      }
    } catch {
      // 打不开就算了；面板会把路径展示出来，用户可手动打开。
    }
  }
}
