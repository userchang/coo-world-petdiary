/**
 * 睡前检查闹钟的「只读检查 + 提醒」。
 *
 * 为什么不直接改 alarms.json：
 * Coo 的 Alarms 只在 NoticeWorld 构造时读一次 alarms.json，之后 tick 用的是内存里的
 * saved；到点或取消时还会用 writeFileSync 把内存写回。插件在运行中改文件不会被捡起，
 * 还可能被下一次写回覆盖。因此这里只读取、只判断，发现不一致时由 World 用
 * WorldHost.pushDeferred 把「请对齐」作为内部事件推给 Coo，让她用 alarm_set 自己改。
 *
 * 这个文件不 import 任何浏览器侧模块，可以单独用 node:test 测。
 */
import { existsSync, readFileSync } from 'node:fs';

/** 只匹配 note 里带这个标记的闹钟。 */
export const BEDTIME_MARKER = '睡前检查';

/** 给 Coo 的规范 note；事件里原样给出，让她按这个设。 */
export const BEDTIME_NOTE =
  '睡前检查：用 diary_read 查今天日记写了没。写过就忽略；没写且空闲就补一条；'
  + '正忙就 alarm_set 顺延 30 分钟再查，最多两次。规则见 DIARY.md。';

/** World 推给 Coo 的事件 type。 */
export const ALARM_SYNC_EVENT = 'coopanion.petdiary-alarm-sync';

const DAY_MS = 86_400_000;
const CLOCK = /^(\d{1,2}):(\d{2})$/;

export interface AlarmRecord {
  id?: unknown;
  at?: unknown;
  note?: unknown;
  daily?: unknown;
  setAt?: unknown;
  [key: string]: unknown;
}

export type AlarmSyncReason =
  | 'aligned'
  | 'mismatch'
  | 'missing'
  | 'file-broken'
  | 'bad-config';

export interface AlarmSyncPlan {
  action: 'none' | 'notify';
  reason: AlarmSyncReason;
  /** 规范化后的 HH:MM；配置坏了时是原值。 */
  bedtime: string;
  alarm: AlarmRecord | null;
  /** 现有闹钟的本地时刻，HH:MM。 */
  currentClock: string | null;
  /** 配置时刻的下一次出现（epoch ms）。 */
  desiredAt: number | null;
  /** 下一次出现的 `MM-DD HH:MM`。 */
  desiredLabel: string;
  /** 给 World 去重的稳定 key。 */
  key: string;
  /** 要推给 Coo 的正文；action=none 时为空串。 */
  text: string;
  /** 需要写运行日志时的原因。 */
  log: string;
}

export interface AlarmSyncOptions {
  alarmsPath: string;
  bedtime: string;
  timezone: string;
  now: number;
}

/** 把 `H:MM` / `HH:MM` 收敛成两位 HH:MM；不合法返回 null。 */
export function normalizeBedtime(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const match = CLOCK.exec(value.trim());
  if (!match) return null;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (!(hour >= 0 && hour <= 23 && minute >= 0 && minute <= 59)) return null;
  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
}

interface ZoneParts {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
  second: number;
}

function zoneParts(timezone: string, epoch: number): ZoneParts {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat('en-US', {
      timeZone: timezone,
      hourCycle: 'h23',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }).formatToParts(new Date(epoch)).map((part) => [part.type, part.value]),
  );
  return {
    year: Number(parts.year),
    month: Number(parts.month),
    day: Number(parts.day),
    hour: Number(parts.hour),
    minute: Number(parts.minute),
    second: Number(parts.second),
  };
}

/** UTC 减去本地，分钟数。 */
function offsetMinutes(timezone: string, epoch: number): number {
  const p = zoneParts(timezone, epoch);
  const local = Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second);
  return (Math.floor(epoch / 1000) * 1000 - local) / 60_000;
}

/** 某个时区的墙钟时间对应的 epoch ms。 */
export function localToEpoch(
  timezone: string,
  year: number,
  month: number,
  day: number,
  hour: number,
  minute: number,
): number {
  const guess = Date.UTC(year, month - 1, day, hour, minute);
  const first = guess + offsetMinutes(timezone, guess) * 60_000;
  return guess + offsetMinutes(timezone, first) * 60_000;
}

/** 某个 epoch 在时区里的 HH:MM。 */
export function clockInZone(timezone: string, epoch: number): string {
  const p = zoneParts(timezone, epoch);
  return `${String(p.hour).padStart(2, '0')}:${String(p.minute).padStart(2, '0')}`;
}

/** 某个 epoch 在时区里的 `MM-DD HH:MM`。 */
export function labelInZone(timezone: string, epoch: number): string {
  const p = zoneParts(timezone, epoch);
  return `${String(p.month).padStart(2, '0')}-${String(p.day).padStart(2, '0')} `
    + `${String(p.hour).padStart(2, '0')}:${String(p.minute).padStart(2, '0')}`;
}

/** 配置时刻的下一次出现：今天还没到就用今天，过了就用明天。 */
export function nextBedtimeEpoch(now: number, timezone: string, bedtime: string): number | null {
  const normalized = normalizeBedtime(bedtime);
  if (!normalized) return null;
  const [hour, minute] = normalized.split(':').map(Number) as [number, number];
  const p = zoneParts(timezone, now);
  const today = localToEpoch(timezone, p.year, p.month, p.day, hour, minute);
  return today > now ? today : today + DAY_MS;
}

interface AlarmFileRead {
  alarms: AlarmRecord[];
  missing: boolean;
  error: string | null;
}

/** 只读 alarms.json；不存在/坏 JSON/形状不对都不抛。 */
export function readAlarmFile(path: string): AlarmFileRead {
  if (!existsSync(path)) return { alarms: [], missing: true, error: null };
  try {
    const value = JSON.parse(readFileSync(path, 'utf8')) as unknown;
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      return { alarms: [], missing: false, error: 'alarms.json 根节点不是对象' };
    }
    const alarms = (value as { alarms?: unknown }).alarms;
    if (!Array.isArray(alarms)) {
      return { alarms: [], missing: false, error: 'alarms.json 的 alarms 不是数组' };
    }
    return {
      alarms: alarms.filter(
        (item): item is AlarmRecord => Boolean(item) && typeof item === 'object' && !Array.isArray(item),
      ),
      missing: false,
      error: null,
    };
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    return { alarms: [], missing: false, error: detail };
  }
}

function matchingAlarm(alarms: readonly AlarmRecord[]): AlarmRecord | null {
  const matches = alarms.filter(
    (alarm) => typeof alarm.note === 'string' && alarm.note.includes(BEDTIME_MARKER),
  );
  if (!matches.length) return null;
  return matches.slice().sort((a, b) => Number(a.at) - Number(b.at))[0] ?? null;
}

function alarmId(alarm: AlarmRecord): string {
  return typeof alarm.id === 'string' && alarm.id ? alarm.id : '(无 id)';
}

function alarmAt(alarm: AlarmRecord): number | null {
  const value = Number(alarm.at);
  return Number.isFinite(value) ? value : null;
}

function mismatchText(bedtime: string, desiredLabel: string): string {
  return `[桌宠日记] 睡前检查时间已改为 ${bedtime}（下一次 ${desiredLabel}）。`
    + '请用 alarm_list 确认「睡前检查」闹钟，再用 alarm_set 把它改到这个时间，daily: true。'
    + `\nnote 保持：\n${BEDTIME_NOTE}`;
}

function missingText(bedtime: string, desiredLabel: string): string {
  return `[桌宠日记] 还没有「睡前检查」闹钟。请用 alarm_set 设一个每天 ${bedtime} 的`
    + `（daily: true，下一次 ${desiredLabel}）。\nnote 用：\n${BEDTIME_NOTE}`;
}

/**
 * 检查一次，只返回计划，不动任何文件。
 *
 * - 有匹配闹钟且本地时刻 == bedtime：不改、不推。
 * - 有匹配闹钟但时刻不同：推一条对齐事件。
 * - 文件里没有匹配闹钟（或 alarms.json 还不存在）：推一条「设一个」事件。
 * - 文件坏 / 配置坏：不推，返回 log。
 */
export function planBedtimeAlarm(options: AlarmSyncOptions): AlarmSyncPlan {
  const bedtime = normalizeBedtime(options.bedtime);
  const base = {
    bedtime: typeof options.bedtime === 'string' ? options.bedtime : String(options.bedtime ?? ''),
    alarm: null as AlarmRecord | null,
    currentClock: null as string | null,
    desiredAt: null as number | null,
    desiredLabel: '',
    key: '',
    text: '',
    log: '',
  };

  if (!bedtime) {
    return {
      ...base,
      action: 'none',
      reason: 'bad-config',
      log: `bedtimeCheck 不是 HH:MM：${JSON.stringify(options.bedtime)}`,
    };
  }

  const read = readAlarmFile(options.alarmsPath);
  if (read.error) {
    return {
      ...base,
      bedtime,
      action: 'none',
      reason: 'file-broken',
      log: `读不了 alarms.json：${read.error}`,
    };
  }

  const desiredAt = nextBedtimeEpoch(options.now, options.timezone, bedtime);
  if (desiredAt === null) {
    return {
      ...base,
      bedtime,
      action: 'none',
      reason: 'bad-config',
      log: `算不出下一次 ${bedtime}`,
    };
  }
  const desiredLabel = labelInZone(options.timezone, desiredAt);
  const alarm = matchingAlarm(read.alarms);
  const missing = read.missing || alarm === null;

  if (missing) {
    return {
      ...base,
      bedtime,
      desiredAt,
      desiredLabel,
      action: 'notify',
      reason: 'missing',
      key: `missing:${bedtime}`,
      text: missingText(bedtime, desiredLabel),
      log: read.missing
        ? 'alarms.json 不存在，按还没设睡前检查闹钟处理'
        : '没有 note 含「睡前检查」的闹钟',
    };
  }

  const at = alarmAt(alarm);
  if (at === null) {
    return {
      ...base,
      bedtime,
      alarm,
      desiredAt,
      desiredLabel,
      action: 'none',
      reason: 'file-broken',
      log: `睡前检查闹钟 ${alarmId(alarm)} 的 at 不是数字：${String(alarm.at)}`,
    };
  }

  const currentClock = clockInZone(options.timezone, at);
  if (currentClock === bedtime) {
    return {
      ...base,
      bedtime,
      alarm,
      currentClock,
      desiredAt,
      desiredLabel,
      action: 'none',
      reason: 'aligned',
      key: `aligned:${bedtime}`,
    };
  }

  return {
    ...base,
    bedtime,
    alarm,
    currentClock,
    desiredAt,
    desiredLabel,
    action: 'notify',
    reason: 'mismatch',
    key: `mismatch:${alarmId(alarm)}:${currentClock}:${bedtime}`,
    text: mismatchText(bedtime, desiredLabel),
    log: `睡前检查闹钟 ${alarmId(alarm)} 是 ${currentClock}，配置是 ${bedtime}`,
  };
}
