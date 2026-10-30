/**
 * 「日记」面板：最近条目（公开/私密分区）、今天写了没、完整性校验、
 * 审计条数与最近动作。数据走 World.invoke('diary', ...)，推送走 ctx.stream()
 *（World 每 1 秒轮询 Python 的 state）。
 *
 * 浏览器端只 import type，不运行时 import cortico/*；需要的值自己带。
 */
import type {
  WebUiClientBundle,
  WebUiPanel,
  WebUiPanelContext,
} from 'cortico/web/shared/client-panel.ts';
import { text } from '../i18n.ts';
import {
  integrityHeadline,
  shouldAlertIntegrity,
  type IntegrityStatus,
  type IntegritySummary,
} from '../integrity.ts';
import './diary.css';

interface DiaryEntry {
  id: string;
  book?: string;
  book_title?: string;
  date?: string;
  time?: string;
  title?: string;
  kind?: string;
  shelf?: string;
  body?: string;
}

interface DiaryState {
  ok?: boolean;
  configured?: boolean;
  error?: string;
  hint?: string;
  library?: { name?: string; mode?: string };
  counts?: { total?: number; private?: number; shelf_public?: number };
  entries?: DiaryEntry[];
  audit?: {
    total?: number;
    read?: number;
    edit?: number;
    build?: number;
    chain_ok?: boolean;
    issues?: string[];
    recent?: Array<{ t?: string; actor?: string; action?: string; entry?: string; target?: string; external?: boolean }>;
  };
  progress?: { last_write?: string; latest_date?: string };
  integrity?: IntegritySummary;
}

const panel: WebUiPanel = {
  async mount(ctx: WebUiPanelContext) {
    const t = text(ctx.language);
    const el = <K extends keyof HTMLElementTagNameMap>(tag: K, cls?: string, value?: string) =>
      ctx.ui.h(tag, cls, value);

    const root = el('div', 'pd-panel');
    const head = el('div', 'pd-head');
    const headText = el('div');
    const title = el('h2', 'pd-title', '日记');
    const sub = el('p', 'pd-sub', t.loading);
    headText.append(title, sub);

    const actions = el('div', 'pd-actions');
    const status = el('span', 'pd-status');
    const verifyBtn = ctx.ui.button(t.verify, { size: 'sm', onClick: () => void verify() });
    const openSiteBtn = ctx.ui.button(t.openSite, { size: 'sm', onClick: () => void openSite() });
    actions.append(status, verifyBtn, openSiteBtn);
    head.append(headText, actions);

    const stats = el('div', 'pd-grid');
    const todayStat = stat('今天', '—');
    const totalStat = stat('合计', '—');
    const bookStat = stat('公开本', '—');
    const privateStat = stat('私密本', '—');
    stats.append(todayStat.node, totalStat.node, bookStat.node, privateStat.node);

    const integritySection = el('section', 'pd-section pd-integrity');
    const integrityTitle = el('h3', undefined, t.integrity);
    const integrityBody = el('div', 'pd-integrity-body');
    integritySection.append(integrityTitle, integrityBody);

    const entriesSection = el('section', 'pd-section');
    const entriesTitle = el('h3', undefined, t.recent);
    const entriesList = el('div', 'pd-list');
    entriesSection.append(entriesTitle, entriesList);

    const auditSection = el('section', 'pd-section');
    const auditTitle = el('h3', undefined, t.recentActions);
    const auditLine = el('div', 'pd-row');
    const auditList = el('div', 'pd-log');
    auditSection.append(auditTitle, auditLine, auditList);

    const msg = ctx.ui.msgline();
    root.append(head, stats, integritySection, entriesSection, auditSection, msg);
    ctx.root.append(root);

    let busy = false;
    let lastIntegrity: IntegrityStatus | null = null;

    function stat(label: string, value: string) {
      const node = el('div', 'pd-stat');
      node.append(el('div', 'k', label), el('div', 'v', value));
      return { node, value: node.lastElementChild as HTMLElement };
    }

    function setMsg(value: string, bad = false) {
      msg.textContent = value;
      msg.classList.toggle('bad', bad);
    }

    function todayKey(): string {
      const now = new Date();
      const pad = (value: number) => String(value).padStart(2, '0');
      return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
    }

    function render(next: DiaryState) {
      if (!next || next.ok === false) {
        sub.textContent = next?.configured === false ? t.noRoot : (next?.error || t.loadFailed);
        setMsg([next?.error, next?.hint].filter(Boolean).join('\n'), true);
        renderIntegrity(next);
        return;
      }
      const library = next.library ?? {};
      const counts = next.counts ?? {};
      const entries = next.entries ?? [];
      const modeDual = library.mode === 'dual';
      const today = entries.filter((entry) => entry.date === todayKey()).length;
      const privateCount = modeDual ? Number(counts.private ?? 0) : 0;
      const publicCount = Number(counts.shelf_public ?? (Number(counts.total ?? entries.length) - privateCount));

      sub.textContent = `${library.name || '—'} · ${modeDual ? t.modeDual : t.modeSingle} · ${next.progress?.last_write || '—'}`;
      status.textContent = modeDual ? `私密本 ${privateCount} 条` : '单本';
      status.className = 'pd-status';
      todayStat.value.textContent = String(today);
      totalStat.value.textContent = String(counts.total ?? entries.length);
      bookStat.value.textContent = String(publicCount);
      privateStat.value.textContent = modeDual ? String(privateCount) : '—';

      setMsg('');
      renderIntegrity(next);
      renderEntries(entries, modeDual, next.integrity);
      renderAudit(next);
    }

    /** 完整性状态块：通过=绿、不匹配=警示、查询失败=灰；自动提示只在上次通过时弹一次。 */
    function renderIntegrity(next: DiaryState | undefined) {
      const summary = next?.integrity;
      integrityBody.replaceChildren();
      integritySection.dataset.status = summary?.status ?? 'checking';
      if (!summary) {
        integrityBody.append(el('div', 'pd-integrity-line muted', t.integrityChecking));
        return;
      }
      if (summary.status === 'ok') {
        const line = el('div', 'pd-integrity-line ok', integrityHeadline(summary, t));
        integrityBody.append(line);
      } else if (summary.status === 'mismatch') {
        const block = el('div', 'pd-integrity-bad');
        const changed = summary.changed_ids ?? summary.ids ?? [];
        const missing = summary.missing_ids ?? [];
        if (changed.length) {
          block.append(el('p', 'pd-integrity-note', t.integrityNotice));
          const list = el('div', 'pd-integrity-list');
          for (const id of changed) {
            const row = el('div', 'pd-integrity-row');
            row.append(el('code', 'pd-code', id));
            row.append(ctx.ui.button(t.integrityView, {
              size: 'sm',
              onClick: () => viewEntry(id),
            }));
            list.append(row);
          }
          block.append(list);
        }
        if (missing.length) {
          block.append(el('p', 'pd-integrity-note', t.integrityDeletedNotice));
          const list = el('div', 'pd-integrity-list');
          for (const id of missing) {
            const row = el('div', 'pd-integrity-row');
            row.append(el('code', 'pd-code', id));
            row.append(ctx.ui.button(t.integrityAckDelete, {
              size: 'sm',
              onClick: () => void ackDelete(id),
            }));
            list.append(row);
          }
          block.append(list);
        }
        if (!changed.length && !missing.length) {
          const list = el('div', 'pd-integrity-list');
          for (const issue of summary.issues.slice(0, 8)) {
            list.append(el('div', 'pd-integrity-row muted', issue));
          }
          block.append(list);
        }
        integrityBody.append(block);
      } else {
        integrityBody.append(el(
          'div',
          'pd-integrity-line muted',
          integrityHeadline(summary, t),
        ));
      }

      if (shouldAlertIntegrity(lastIntegrity, summary.status)) {
        const message = t.integrityAlert;
        ctx.ui.toast(message, 'bad');
        setMsg(message, true);
      }
      lastIntegrity = summary.status;
    }

    /** 点「查看」：滚到对应卡片并闪一下；异常条目已在 renderEntries 里保证渲染。 */
    function viewEntry(entryId: string) {
      const card = Array.from(entriesList.querySelectorAll<HTMLElement>('[data-entry-id]'))
        .find((node) => node.dataset.entryId === entryId);
      if (!card) {
        setMsg(t.integrityViewMissing(entryId), true);
        return;
      }
      card.scrollIntoView({ behavior: 'smooth', block: 'center' });
      card.classList.add('pd-flash');
      window.setTimeout(() => card.classList.remove('pd-flash'), 1800);
    }

    function entryCard(entry: DiaryEntry, flagged = false) {
      const card = el('article', 'pd-card');
      card.dataset.kind = entry.kind || '未分类';
      card.dataset.entryId = entry.id;
      if (flagged) card.classList.add('pd-card-flagged');
      const top = el('div', 'pd-card-top');
      top.append(el('span', 'pd-time', entry.time || '—'));
      top.append(el('span', 'pd-book', entry.book_title || entry.book || ''));
      top.append(el('span', 'pd-badge kind', entry.kind || '未分类'));
      if (entry.shelf === 'private') {
        top.append(el('span', 'pd-badge private', '私密本'));
      }
      if (flagged) {
        top.append(el('span', 'pd-badge bad', t.integrityFlagged));
      }
      card.append(top);
      card.append(el('h4', 'pd-card-title', entry.title || '（无标题）'));
      card.append(el('p', 'pd-card-body', (entry.body || '').split('\n').slice(0, 4).join('\n') || '（没有正文）'));
      return card;
    }

    function renderEntries(entries: DiaryEntry[], showPrivate: boolean, integrity?: IntegritySummary) {
      entriesList.replaceChildren();
      const recent = entries.slice(-8).reverse();
      const flagged = new Set(integrity?.ids ?? []);
      // 不匹配的条目可能不在最近 8 条里；补进来，保证「查看」能跳到。
      for (const id of flagged) {
        const entry = entries.find((item) => item.id === id);
        if (entry && !recent.includes(entry)) recent.push(entry);
      }
      if (!recent.length) {
        entriesList.append(el('span', 'pd-empty', t.noEntries));
        return;
      }
      const publicEntries = recent.filter((entry) => (entry.shelf || 'public') !== 'private');
      const privateEntries = recent.filter((entry) => entry.shelf === 'private');
      if (showPrivate) {
        entriesList.append(el('h3', undefined, t.publicBook));
      }
      const pubWrap = el('div', 'pd-list');
      if (publicEntries.length) {
        for (const entry of publicEntries) pubWrap.append(entryCard(entry, flagged.has(entry.id)));
      } else {
        pubWrap.append(el('span', 'pd-empty', t.noEntries));
      }
      entriesList.append(pubWrap);
      if (showPrivate) {
        entriesList.append(el('h3', undefined, t.privateBook));
        const privWrap = el('div', 'pd-list');
        if (privateEntries.length) {
          for (const entry of privateEntries) privWrap.append(entryCard(entry, flagged.has(entry.id)));
        } else {
          privWrap.append(el('span', 'pd-empty', t.noEntries));
        }
        entriesList.append(privWrap);
      }
    }

    function renderAudit(next: DiaryState) {
      const audit = next.audit ?? {};
      auditLine.replaceChildren();
      const k = el('span', 'k', t.auditCount);
      const v = el('span', undefined, `共 ${audit.total ?? 0} 条 · 读 ${audit.read ?? 0} · 改动 ${audit.edit ?? 0} · 构建 ${audit.build ?? 0}`);
      auditLine.append(k, v);
      auditList.replaceChildren();
      const recent = (audit.recent ?? []).slice(0, 8);
      if (!recent.length) {
        auditList.append(el('span', 'pd-empty', '还没有审计记录。'));
        return;
      }
      for (const item of recent) {
        const row = el('div', 'pd-log-row');
        row.append(
          el('span', 'muted', String(item.t ?? '').slice(11, 19) || '—'),
          el('span', undefined, item.actor || 'unknown'),
          el('span', undefined, item.action || '?'),
          el('span', 'muted', item.entry || item.target || '—'),
        );
        auditList.append(row);
      }
      if (audit.chain_ok === false) {
        setMsg(`审计链异常：${(audit.issues ?? []).slice(0, 3).join('；')}`, true);
      }
    }

    async function load(force = false) {
      if (busy && !force) return;
      busy = true;
      try {
        const next = await ctx.invoke<DiaryState>('state');
        render(next);
      } catch (error) {
        setMsg(`${t.loadFailed}：${error instanceof Error ? error.message : String(error)}`, true);
      } finally {
        busy = false;
      }
    }

    async function verify() {
      try {
        const result = await ctx.invoke<{ text?: string; failed?: boolean }>('verify');
        const message = result?.text || '校验完成';
        setMsg(message, Boolean(result?.failed));
        ctx.ui.toast(message, result?.failed ? 'bad' : 'ok');
      } catch (error) {
        setMsg(`校验失败：${error instanceof Error ? error.message : String(error)}`, true);
      }
    }

    /** 确认库外删除：只清残留指纹并留 delete 审计，然后刷新状态块。 */
    async function ackDelete(entryId: string) {
      if (busy) return;
      busy = true;
      try {
        const result = await ctx.invoke<{ text?: string; failed?: boolean }>(
          'integrity-ack-delete',
          [entryId],
        );
        const message = result?.text || '已确认删除';
        setMsg(message, Boolean(result?.failed));
        ctx.ui.toast(message, result?.failed ? 'bad' : 'ok');
        if (!result?.failed) await load(true);
      } catch (error) {
        const message = `确认删除失败：${error instanceof Error ? error.message : String(error)}`;
        setMsg(message, true);
        ctx.ui.toast(message, 'bad');
      } finally {
        busy = false;
      }
    }

    async function openSite() {
      if (busy) return;
      busy = true;
      try {
        const result = await ctx.invoke<{ ok?: boolean; path?: string; error?: string }>('openSite');
        if (result?.ok) {
          const message = t.openSiteOk(result.path || '');
          setMsg(message);
          ctx.ui.toast(message, 'ok');
        } else {
          const message = t.openSiteFailed(result?.error || '未知错误');
          setMsg(message, true);
          ctx.ui.toast(message, 'bad');
        }
      } catch (error) {
        const message = t.openSiteFailed(error instanceof Error ? error.message : String(error));
        setMsg(message, true);
      } finally {
        busy = false;
      }
    }

    const handle = ctx.stream({
      message(raw) {
        try {
          const frame = JSON.parse(raw) as { type?: string; state?: DiaryState };
          if (frame.type === 'state' && frame.state) render(frame.state);
        } catch {
          // 坏帧忽略，等下一帧。
        }
      },
    });
    ctx.own(handle);

    await load();
  },
};

const bundle: WebUiClientBundle = { panels: { diary: panel } };

export default bundle;
