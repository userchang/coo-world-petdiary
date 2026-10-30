/**
 * Python 子进程桥。World 与面板都不直接写 md，所有读写都经 admin.py。
 *
 * 约定（与 diary/admin.py 对齐）：
 * - stdout 只出一行 JSON：{ok, ...} 或 {ok:false,error,hint}；
 * - 日志走 stderr；
 * - 退出码 0 成功 / 1 数据问题 / 2 参数或库根问题。
 *
 * 这里同时负责：UTF-8 强制、20 秒超时、找不到解释器/脚本目录的人话错误。
 */
import { execFile } from 'node:child_process';
import { existsSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { promisify } from 'node:util';
import type { PetDiarySection } from './config.ts';
import { applyDefaults, resolveDefaults, type AppliedDefaults, type PetDiaryDefaults } from './defaults.ts';

const execFileAsync = promisify(execFile);
const DEFAULT_TIMEOUT_MS = 20_000;
const MAX_JSON_BYTES = 8 * 1024 * 1024;

export interface BridgeFailure {
  ok: false;
  code: number;
  error: string;
  hint: string;
  stderr?: string;
  /** 后端退出码非 0 时仍可能带一行 JSON（例如 verify 发现不匹配）；保留给只读查询用。 */
  data?: Record<string, unknown>;
}

export interface BridgeSuccess<T = Record<string, unknown>> {
  ok: true;
  code: 0;
  data: T;
}

export type BridgeResult<T = Record<string, unknown>> = BridgeSuccess<T> | BridgeFailure;

export interface RunOptions {
  timeoutMs?: number;
  /** 仅供测试注入；缺省按配置/候选表。 */
  pythonCandidates?: string[];
  signal?: AbortSignal;
  /** 由 World 推导好的默认值；缺省按插件模块路径推导。 */
  defaults?: PetDiaryDefaults;
  /** 自动初始化默认库等运维日志；缺省写 console.warn。 */
  log?: (message: string) => void;
}

export function resolvePythonCandidates(cfg: PetDiarySection, override?: string[]): string[] {
  if (override?.length) return override;
  const configured = cfg.pythonPath.trim();
  if (configured) return [configured];
  return ['python', 'python3'];
}

/** 留空时用库根同级的 diary/；没有 admin.py 就给人话错误。 */
export function resolveScriptsDir(
  cfg: PetDiarySection,
): { ok: true; dir: string } | { ok: false; error: string; hint: string } {
  const root = cfg.libraryRoot.trim();
  if (!root) {
    return {
      ok: false,
      error: '桌宠日记还没配置库根',
      hint: '打开「桌宠日记」页的配置，把日记库根填成含 index.diary 的目录。',
    };
  }
  const configured = cfg.scriptsDir.trim();
  const dir = configured || join(dirname(root), 'diary');
  if (!existsSync(join(dir, 'admin.py'))) {
    return {
      ok: false,
      error: `找不到日记后端脚本：${join(dir, 'admin.py')}`,
      hint: '留空会自动使用插件内置 runtime/diary；也可以填 scriptsDir（含 admin.py / parser.py / store.py 的目录）。',
    };
  }
  return { ok: true, dir };
}

/** 只取最后一行非空 JSON，容忍后端在 stdout 前多打了一行提示。 */
export function parseAdminJson(stdout: string): Record<string, unknown> | null {
  const lines = String(stdout ?? '').split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    const line = lines[index];
    if (!line.startsWith('{') || !line.endsWith('}')) continue;
    try {
      const value = JSON.parse(line);
      if (value && typeof value === 'object' && !Array.isArray(value)) {
        return value as Record<string, unknown>;
      }
    } catch {
      // 继续往前找：后端偶尔可能先打一行非 JSON 日志。
    }
  }
  return null;
}

export function classifyExit(code: number | string | null | undefined, error: unknown): number {
  const err = error as NodeJS.ErrnoException & { killed?: boolean; signal?: string; message?: string };
  if (err?.code === 'ENOENT') return 4;
  if (
    code === 'ETIMEDOUT'
    || err?.code === 'ETIMEDOUT'
    || err?.killed
    || err?.signal === 'SIGTERM'
    || err?.signal === 'SIGKILL'
    || /timed?\s*out|timeout/i.test(String(err?.message ?? ''))
  ) return 3;
  const numeric = typeof code === 'number' ? code : Number(code);
  if (numeric === 2) return 2;
  if (numeric === 1) return 1;
  if (numeric === 3 || numeric === 4 || numeric === 5) return numeric;
  return 5;
}

function cleanStderr(value: unknown): string {
  const text = String(value ?? '').trim();
  if (!text) return '';
  // 错误也可能被日志塞很长；截断，永不把参数/正文回显出去。
  return text.length > 600 ? `${text.slice(0, 600)}…` : text;
}

/** 习惯称呼透传给 Python 后端：分类关键词与说话人识别都按它来。 */
function aliasEnv(cfg: PetDiarySection): Record<string, string> {
  const alias = cfg.partnerAlias?.trim();
  return alias ? { PETDIARY_PARTNER_ALIAS: alias } : {};
}

async function execOnce(
  python: string,
  script: string,
  adminArgs: string[],
  cfg: PetDiarySection,
  opts: RunOptions,
  timeoutMs: number,
): Promise<{ stdout: string; stderr: string; code: number }> {
  const env = {
    ...process.env,
    PYTHONIOENCODING: 'utf-8',
    PYTHONUTF8: '1',
    ...aliasEnv(cfg),
  };
  try {
    const result = await execFileAsync(python, [script, ...adminArgs], {
      cwd: dirname(script),
      env,
      timeout: timeoutMs,
      windowsHide: true,
      encoding: 'utf8',
      maxBuffer: MAX_JSON_BYTES,
      signal: opts.signal,
    });
    return { stdout: result.stdout, stderr: result.stderr, code: 0 };
  } catch (error) {
    const err = error as NodeJS.ErrnoException & {
      code?: number | string;
      killed?: boolean;
      signal?: string;
      stdout?: string;
      stderr?: string;
    };
    if (err.code === 'ENOENT') throw error;
    return {
      stdout: err.stdout ?? '',
      stderr: err.stderr ?? '',
      code: typeof err.code === 'number' ? err.code : classifyExit(null, err),
    };
  }
}

/**
 * 首次使用默认库根时建目录 + admin.py init。已有 index.diary 直接跳过，
 * 因此重复 state/verify 不会重复初始化；用户自己配置的库根永远不会走这里。
 */
async function ensureDefaultLibrary(
  applied: AppliedDefaults,
  opts: RunOptions,
): Promise<BridgeFailure | null> {
  if (!applied.usedDefaults.libraryRoot) return null;
  const root = applied.cfg.libraryRoot.trim();
  if (!root) return null;
  const index = join(root, 'index.diary');
  if (existsSync(index)) return null;

  const log = opts.log ?? ((message: string) => console.warn(message));
  try {
    mkdirSync(root, { recursive: true });
  } catch (error) {
    const message = `建默认日记库目录失败：${(error as Error).message}`;
    log(`[pet-diary] ${message}`);
    return { ok: false, code: 2, error: message, hint: root };
  }

  const scripts = resolveScriptsDir(applied.cfg);
  if (!scripts.ok) {
    log(`[pet-diary] 自动初始化默认日记库失败：${scripts.error}`);
    return { ok: false, code: 2, error: scripts.error, hint: scripts.hint };
  }
  const script = join(scripts.dir, 'admin.py');
  const candidates = resolvePythonCandidates(applied.cfg, opts.pythonCandidates);
  const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const env = { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1', ...aliasEnv(applied.cfg) };
  let lastMissing: unknown = null;

  for (const python of candidates) {
    try {
      await execFileAsync(
        python,
        [script, 'init', '--root', root, '--name', '桌宠日记'],
        {
          cwd: dirname(script),
          env,
          timeout: timeoutMs,
          windowsHide: true,
          encoding: 'utf8',
          maxBuffer: MAX_JSON_BYTES,
          signal: opts.signal,
        },
      );
      log(`[pet-diary] 已初始化默认日记库：${root}`);
      return null;
    } catch (error) {
      const err = error as NodeJS.ErrnoException & { stdout?: string; stderr?: string };
      if (err.code === 'ENOENT') {
        lastMissing = error;
        continue;
      }
      const detail = cleanStderr(err.stderr ?? err.stdout ?? '');
      const message = `初始化默认日记库失败：${detail || err.message}`;
      log(`[pet-diary] ${message}`);
      return {
        ok: false,
        code: classifyExit(null, error),
        error: '初始化默认日记库失败',
        hint: detail || root,
        stderr: detail,
      };
    }
  }

  const missingError = lastMissing as NodeJS.ErrnoException | null;
  const message = `找不到 Python 解释器，无法初始化默认日记库：${root}`;
  log(`[pet-diary] ${message}`);
  return {
    ok: false,
    code: 4,
    error: '找不到 Python 解释器',
    hint: `试过 ${candidates.join(' / ')}${missingError ? `；${missingError.message}` : ''}。`,
  };
}

/** 跑一条 admin 子命令并返回统一结果；不抛异常（除非调用方传了 abort）。 */
export async function runAdmin<T = Record<string, unknown>>(
  cfg: PetDiarySection,
  command: string,
  args: string[] = [],
  opts: RunOptions = {},
): Promise<BridgeResult<T>> {
  const defaults = opts.defaults ?? resolveDefaults();
  const applied = applyDefaults(cfg, defaults);
  const effective = applied.cfg;
  if (!effective.libraryRoot.trim()) {
    return {
      ok: false,
      code: 2,
      error: '桌宠日记还没有可用的库根',
      hint: '留空会自动使用插件默认库；也可以填一个含 index.diary 的目录。',
    };
  }
  const initFailure = await ensureDefaultLibrary(applied, opts);
  if (initFailure) return initFailure;

  const scripts = resolveScriptsDir(effective);
  if (!scripts.ok) return { ok: false, code: 2, error: scripts.error, hint: scripts.hint };
  const script = join(scripts.dir, 'admin.py');
  const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const candidates = resolvePythonCandidates(effective, opts.pythonCandidates);
  const adminArgs = [command, '--root', effective.libraryRoot.trim(), ...args, '--json'];

  let lastMissing: unknown = null;
  for (const python of candidates) {
    let executed: { stdout: string; stderr: string; code: number };
    try {
      executed = await execOnce(python, script, adminArgs, effective, opts, timeoutMs);
    } catch (error) {
      const err = error as NodeJS.ErrnoException & { killed?: boolean; signal?: string };
      if (err.code === 'ENOENT') {
        lastMissing = error;
        continue;
      }
      const code = classifyExit(null, error);
      return {
        ok: false,
        code,
        error: code === 3 ? `日记后端超时（${Math.round(timeoutMs / 1000)} 秒）` : `调用日记后端失败：${err.message}`,
        hint: '检查 pythonPath 与 scriptsDir；库根必须是含 index.diary 的目录。',
      };
    }

    const parsed = parseAdminJson(executed.stdout);
    if (executed.code === 0) {
      if (!parsed) {
        return {
          ok: false,
          code: 5,
          error: '日记后端没有返回 JSON',
          hint: '确认 scriptsDir 指向的是本项目的 diary/（admin.py 支持 --json）。',
          stderr: cleanStderr(executed.stderr),
        };
      }
      if (parsed.ok === false) {
        const issues = Array.isArray(parsed.issues)
          ? parsed.issues.map((item) => String(item)).slice(0, 5).join('；')
          : '';
        return {
          ok: false,
          code: Number(parsed.code) || 1,
          error: String(parsed.error ?? parsed.reason ?? parsed.summary ?? '日记后端拒绝了这个操作'),
          hint: String(parsed.hint ?? issues),
          stderr: cleanStderr(executed.stderr),
          data: parsed,
        };
      }
      return { ok: true, code: 0, data: parsed as T };
    }

    const mapped = classifyExit(executed.code, null);
    if (mapped === 3) {
      return {
        ok: false,
        code: 3,
        error: `日记后端超时（${Math.round(timeoutMs / 1000)} 秒）`,
        hint: '库太大或磁盘卡住；先用服务模式，或检查库根是否在慢盘上。',
      };
    }
    const issues = Array.isArray(parsed?.issues)
      ? parsed.issues.map((item) => String(item)).slice(0, 5).join('；')
      : '';
    // 后端没吐 JSON（比如 argparse 用法错误只写 stderr）时，把 stderr 摘要透出来，
    // 否则现场只能看到"退出码 2"，没法定位。
    const stderr = cleanStderr(executed.stderr);
    const fallbackHint =
      mapped === 2 ? '检查参数、库根与 index.diary。' : '数据有问题；用 diary_verify 或 admin.py verify 看具体条目。';
    return {
      ok: false,
      code: mapped,
      error: String(parsed?.error ?? parsed?.reason ?? parsed?.summary ?? `日记后端退出码 ${executed.code}`),
      hint: String((parsed?.hint ?? issues) || (stderr ? `后端输出：${stderr.slice(0, 200)}` : fallbackHint)),
      stderr,
      data: parsed ?? undefined,
    };
  }

  const missingError = lastMissing as NodeJS.ErrnoException | null;
  return {
    ok: false,
    code: 4,
    error: '找不到 Python 解释器',
    hint: `试过 ${candidates.join(' / ')}${missingError ? `；${missingError.message}` : ''}。请在配置里填 pythonPath，或确认插件 runtime/python 完整。`,
  };
}

/** 给工具回执：把 BridgeFailure 变成一句人话，不夹带私人正文。 */
export function failureText(result: BridgeFailure): string {
  const hint = result.hint ? `\n提示：${result.hint}` : '';
  return `${result.error}${hint}`;
}

/** 浏览页构建结果。 */
export interface BuildSiteResult {
  ok: true;
  /** 生成的 index.html 绝对路径。 */
  htmlPath: string;
}

/**
 * 跑 build.py 生成全库浏览页（--scope all，含私密本；分享页另行构建，不走这里）。
 * build.py 输出的是人读文本而非 JSON，成功以退出码 0 判定。
 */
export async function runBuildSite(
  cfg: PetDiarySection,
  outDir: string,
  opts: RunOptions = {},
): Promise<BuildSiteResult | BridgeFailure> {
  const defaults = opts.defaults ?? resolveDefaults();
  const applied = applyDefaults(cfg, defaults);
  const effective = applied.cfg;
  if (!effective.libraryRoot.trim()) {
    return {
      ok: false,
      code: 2,
      error: '桌宠日记还没有可用的库根',
      hint: '留空会自动使用插件默认库；也可以填一个含 index.diary 的目录。',
    };
  }
  const initFailure = await ensureDefaultLibrary(applied, opts);
  if (initFailure) return initFailure;

  const scripts = resolveScriptsDir(effective);
  if (!scripts.ok) return { ok: false, code: 2, error: scripts.error, hint: scripts.hint };
  const script = join(scripts.dir, 'build.py');
  if (!existsSync(script)) {
    return {
      ok: false,
      code: 2,
      error: '没找到 build.py',
      hint: `确认 scriptsDir 指向含 build.py 的 diary 目录（当前：${scripts.dir}）。`,
    };
  }
  const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const candidates = resolvePythonCandidates(effective, opts.pythonCandidates);
  const buildArgs = ['--root', effective.libraryRoot.trim(), '--scope', 'all', '--out', outDir];
  const env = { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1', ...aliasEnv(effective) };

  let lastMissing: unknown = null;
  for (const python of candidates) {
    try {
      await execFileAsync(python, [script, ...buildArgs], {
        cwd: dirname(script),
        env,
        timeout: timeoutMs,
        windowsHide: true,
        encoding: 'utf8',
        maxBuffer: MAX_JSON_BYTES,
        signal: opts.signal,
      });
      return { ok: true, htmlPath: join(outDir, 'index.html') };
    } catch (error) {
      const err = error as NodeJS.ErrnoException & { code?: number | string; stdout?: string; stderr?: string };
      if (err.code === 'ENOENT') {
        lastMissing = error;
        continue;
      }
      const detail = cleanStderr(err.stderr ?? err.stdout ?? '');
      return {
        ok: false,
        code: classifyExit(null, err),
        error: '构建浏览页失败',
        hint: detail || '检查 pythonPath 与库根；详情见构建输出。',
        stderr: detail,
      };
    }
  }
  const missingError = lastMissing as NodeJS.ErrnoException | null;
  return {
    ok: false,
    code: 4,
    error: '找不到 Python 解释器',
    hint: `试过 ${candidates.join(' / ')}${missingError ? `；${missingError.message}` : ''}。请在配置里填 pythonPath，或确认插件 runtime/python 完整。`,
  };
}
