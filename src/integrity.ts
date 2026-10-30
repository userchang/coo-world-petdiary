/**
 * 完整性校验摘要：World（Node 侧）与浏览器面板共用。
 * 本文件不 import 任何 node:* 模块，可以安全地 bundle 进 dist/webui.js。
 */
import type { TextTable } from './i18n.ts';

export type IntegrityStatus = 'ok' | 'mismatch' | 'error';

export interface IntegritySummary {
  status: IntegrityStatus;
  /** 库里的条目总数（取 verify 返回的指纹条数）。 */
  total: number;
  /** 被外部修改 / 消失的条目 id；查询失败时为空。 */
  ids: string[];
  /** 被外部修改的条目 id。 */
  changed_ids: string[];
  /** 库外已消失的条目 id（指纹还在基线里）。 */
  missing_ids: string[];
  /** 后端 verify 的原文 issue 行（含审计链问题）。 */
  issues: string[];
  /** 查询失败的人话原因。 */
  error?: string;
  /** 本次查询时间（epoch ms）。 */
  checked_at: number;
}

/** admin.py verify --json 里我们关心的字段。 */
export interface VerifyJson {
  ok?: unknown;
  issues?: unknown;
  audit_count?: unknown;
  fingerprint_count?: unknown;
  new_count?: unknown;
  summary?: unknown;
}

/** bridge.runAdmin 的结果里我们关心的部分（成功/失败都能带 data）。 */
export interface VerifyBridgeLike {
  ok: boolean;
  code?: number;
  data?: unknown;
  error?: string;
  hint?: string;
}

/** admin.py verify 的条目问题行：`⚠ <entry-id> 被外部修改（哈希不匹配）` / `⚠ <entry-id> 条目消失`。 */
const CHANGED_ISSUE = /⚠\s*([^\s：:]+)\s+被外部修改/u;
const MISSING_ISSUE = /⚠\s*([^\s：:]+)\s+条目消失/u;
const ISSUE_ID = /⚠\s*([^\s：:]+)\s+(?:被外部修改|条目消失)/u;

function matchingIds(issues: readonly string[], pattern: RegExp): string[] {
  const seen = new Set<string>();
  for (const line of issues) {
    const match = pattern.exec(line);
    if (match?.[1]) seen.add(match[1]);
  }
  return [...seen];
}

export function integrityIds(issues: readonly string[]): string[] {
  return matchingIds(issues, ISSUE_ID);
}

export function integrityKinds(issues: readonly string[]): {
  changed: string[];
  missing: string[];
} {
  return {
    changed: matchingIds(issues, CHANGED_ISSUE),
    missing: matchingIds(issues, MISSING_ISSUE),
  };
}

/**
 * 把 bridge 结果收敛成面板要的三态：通过 / 有不匹配 / 无法校验。
 * verify 发现问题时后端退出码是 1，但 JSON 里仍带 issues 与计数；
 * 这时只要有 issues 就算 mismatch，不能当成查询失败。
 */
export function summarizeVerify(result: VerifyBridgeLike, now = Date.now()): IntegritySummary {
  const data = (result.data ?? {}) as VerifyJson;
  const issues = Array.isArray(data.issues) ? data.issues.map((item) => String(item)) : [];
  const total = Math.max(0, Number(data.fingerprint_count ?? data.audit_count ?? 0) || 0);
  const kinds = integrityKinds(issues);
  const ids = [...new Set([...kinds.changed, ...kinds.missing])];

  if (issues.length > 0) {
    return {
      status: 'mismatch',
      total,
      ids,
      changed_ids: kinds.changed,
      missing_ids: kinds.missing,
      issues,
      checked_at: now,
    };
  }
  if (result.ok) {
    return {
      status: 'ok',
      total,
      ids: [],
      changed_ids: [],
      missing_ids: [],
      issues: [],
      checked_at: now,
    };
  }
  return {
    status: 'error',
    total,
    ids: [],
    changed_ids: [],
    missing_ids: [],
    issues,
    error: String(result.error || data.summary || ''),
    checked_at: now,
  };
}

/** 状态块的第一行文案；不匹配时正文固定用 integrityNotice。 */
export function integrityHeadline(summary: IntegritySummary, t: TextTable): string {
  if (summary.status === 'ok') return t.integrityPassed(summary.total);
  if (summary.status === 'mismatch') return t.integrityNotice;
  return t.integrityUnavailable(summary.error || t.integrityUnknown);
}

/**
 * 自动提示只在「上一轮通过、这一轮不匹配」时弹一次。
 * 首次加载不弹；不匹配持续时不重复弹；恢复通过后下次再变坏会重新弹。
 */
export function shouldAlertIntegrity(
  previous: IntegrityStatus | null,
  next: IntegrityStatus,
): boolean {
  return previous === 'ok' && next === 'mismatch';
}
