// src/i18n.ts
var zh = {
  worldLabel: "\u684C\u5BA0\u65E5\u8BB0",
  panelTitle: "\u65E5\u8BB0",
  panelDescription: "\u6700\u8FD1\u6761\u76EE\u3001\u4ECA\u5929\u5199\u4E86\u6CA1\u3001\u516C\u5F00\u672C\u4E0E\u79C1\u5BC6\u672C\u5206\u7C7B\u3001\u5B8C\u6574\u6027\u68C0\u67E5\u3002",
  envTitle: "\u684C\u5BA0\u65E5\u8BB0 \xB7 \u73AF\u5883\u63D0\u793A\u8BCD",
  envDescription: "\u544A\u8BC9 Coo \u600E\u4E48\u5199\u65E5\u8BB0\uFF0C\u4EE5\u53CA\u516C\u5F00\u672C\u4E0E\u79C1\u5BC6\u672C\u7684\u533A\u522B\u3002",
  noRoot: "\u8FD8\u6CA1\u914D\u7F6E\u65E5\u8BB0\u5E93\u6839\u3002\u6253\u5F00\u672C\u9875\u7684\u914D\u7F6E\uFF0C\u586B\u542B index.diary \u7684\u76EE\u5F55\u3002",
  loading: "\u6B63\u5728\u8BFB\u65E5\u8BB0\u2026",
  loadFailed: "\u8BFB\u65E5\u8BB0\u5931\u8D25",
  today: "\u4ECA\u5929",
  wroteToday: (count) => `\u4ECA\u5929\u5DF2\u7ECF\u5199\u4E86 ${count} \u6761`,
  notToday: "\u4ECA\u5929\u8FD8\u6CA1\u5199",
  total: "\u5408\u8BA1",
  publicBook: "\u516C\u5F00\u672C",
  privateBook: "\u79C1\u5BC6\u672C",
  auditCount: "\u5BA1\u8BA1",
  recent: "\u6700\u8FD1\u6761\u76EE",
  noEntries: "\u8FD8\u6CA1\u6709\u6761\u76EE\u3002",
  verify: "\u6821\u9A8C\u5B8C\u6574\u6027",
  openSite: "\u6253\u5F00\u6D4F\u89C8\u9875",
  openSiteOk: (path) => `\u6D4F\u89C8\u9875\u5DF2\u751F\u6210\u5E76\u5728\u6D4F\u89C8\u5668\u6253\u5F00\uFF1A${path}`,
  openSiteFailed: (message) => `\u6253\u5F00\u6D4F\u89C8\u9875\u5931\u8D25\uFF1A${message}`,
  verifyNormal: (count) => `\u6B63\u5E38 ${count} \u6761`,
  verifyBad: (count) => `\u53D1\u73B0 ${count} \u4E2A\u95EE\u9898`,
  modeSingle: "\u5355\u672C",
  modeDual: "\u516C\u5F00 / \u79C1\u5BC6\u4E24\u672C",
  recentActions: "\u6700\u8FD1\u52A8\u4F5C",
  reason: "\u539F\u56E0",
  integrity: "\u5B8C\u6574\u6027",
  integrityPassed: (count) => `\u5B8C\u6574\u6027\u6821\u9A8C\u901A\u8FC7\uFF08${count} \u6761\uFF09`,
  integrityNotice: '\u4EE5\u4E0B\u6761\u76EE\u5728\u5E93\u5916\u88AB\u4FEE\u6539\u8FC7\uFF0C\u4E0E\u5BA1\u8BA1\u6307\u7EB9\u4E0D\u7B26\u3002\u65E5\u8BB0\u662F"\u5199\u5B8C\u4E0D\u6539"\u7684\uFF0C\u8FD9\u901A\u5E38\u610F\u5473\u7740\u76F4\u63A5\u7F16\u8F91\u8FC7 md \u6587\u4EF6\u3002\u53EF\u70B9\u300E\u67E5\u770B\u300F\u8DF3\u5230\u5BF9\u5E94\u6761\u76EE\uFF0C\u6216\u5FFD\u7565\u3002',
  integrityDeletedNotice: "\u4EE5\u4E0B\u6761\u76EE\u5DF2\u88AB\u5220\u9664\uFF08\u5E93\u5916\u76F4\u63A5\u5220\u7684\uFF09\uFF0C\u6307\u7EB9\u8FD8\u7559\u5728\u57FA\u7EBF\u91CC\u3002\u53EF\u70B9\u300E\u786E\u8BA4\u5220\u9664\u300F\u6E05\u6389\u6B8B\u7559\u6307\u7EB9\uFF0C\u5BA1\u8BA1\u94FE\u4F1A\u8BB0\u5F55\u8FD9\u6B21\u786E\u8BA4",
  integrityAckDelete: "\u786E\u8BA4\u5220\u9664",
  integrityAlert: "\u5B8C\u6574\u6027\u6821\u9A8C\u53D1\u73B0\u5F02\u5E38\uFF0C\u8BF7\u67E5\u770B\u5B8C\u6574\u6027\u72B6\u6001\u5757",
  integrityUnavailable: (reason) => `\u65E0\u6CD5\u6821\u9A8C\uFF08${reason}\uFF09`,
  integrityUnknown: "\u672A\u77E5\u539F\u56E0",
  integrityChecking: "\u6B63\u5728\u6821\u9A8C\u5B8C\u6574\u6027\u2026",
  integrityView: "\u67E5\u770B",
  integrityViewMissing: (entryId) => `\u6700\u8FD1\u6761\u76EE\u91CC\u6CA1\u6709 ${entryId}`,
  integrityFlagged: "\u6821\u9A8C\u5F02\u5E38"
};
var en = {};
function text(language = "zh") {
  if (language === "en") return { ...zh, ...en };
  return zh;
}

// src/integrity.ts
function integrityHeadline(summary, t) {
  if (summary.status === "ok") return t.integrityPassed(summary.total);
  if (summary.status === "mismatch") return t.integrityNotice;
  return t.integrityUnavailable(summary.error || t.integrityUnknown);
}
function shouldAlertIntegrity(previous, next) {
  return previous === "ok" && next === "mismatch";
}

// src/panels/diary.ts
var panel = {
  async mount(ctx) {
    const t = text(ctx.language);
    const el = (tag, cls, value) => ctx.ui.h(tag, cls, value);
    const root = el("div", "pd-panel");
    const head = el("div", "pd-head");
    const headText = el("div");
    const title = el("h2", "pd-title", "\u65E5\u8BB0");
    const sub = el("p", "pd-sub", t.loading);
    headText.append(title, sub);
    const actions = el("div", "pd-actions");
    const status = el("span", "pd-status");
    const verifyBtn = ctx.ui.button(t.verify, { size: "sm", onClick: () => void verify() });
    const openSiteBtn = ctx.ui.button(t.openSite, { size: "sm", onClick: () => void openSite() });
    actions.append(status, verifyBtn, openSiteBtn);
    head.append(headText, actions);
    const stats = el("div", "pd-grid");
    const todayStat = stat("\u4ECA\u5929", "\u2014");
    const totalStat = stat("\u5408\u8BA1", "\u2014");
    const bookStat = stat("\u516C\u5F00\u672C", "\u2014");
    const privateStat = stat("\u79C1\u5BC6\u672C", "\u2014");
    stats.append(todayStat.node, totalStat.node, bookStat.node, privateStat.node);
    const integritySection = el("section", "pd-section pd-integrity");
    const integrityTitle = el("h3", void 0, t.integrity);
    const integrityBody = el("div", "pd-integrity-body");
    integritySection.append(integrityTitle, integrityBody);
    const entriesSection = el("section", "pd-section");
    const entriesTitle = el("h3", void 0, t.recent);
    const entriesList = el("div", "pd-list");
    entriesSection.append(entriesTitle, entriesList);
    const auditSection = el("section", "pd-section");
    const auditTitle = el("h3", void 0, t.recentActions);
    const auditLine = el("div", "pd-row");
    const auditList = el("div", "pd-log");
    auditSection.append(auditTitle, auditLine, auditList);
    const msg = ctx.ui.msgline();
    root.append(head, stats, integritySection, entriesSection, auditSection, msg);
    ctx.root.append(root);
    let busy = false;
    let lastIntegrity = null;
    function stat(label, value) {
      const node = el("div", "pd-stat");
      node.append(el("div", "k", label), el("div", "v", value));
      return { node, value: node.lastElementChild };
    }
    function setMsg(value, bad = false) {
      msg.textContent = value;
      msg.classList.toggle("bad", bad);
    }
    function todayKey() {
      const now = /* @__PURE__ */ new Date();
      const pad = (value) => String(value).padStart(2, "0");
      return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
    }
    function render(next) {
      if (!next || next.ok === false) {
        sub.textContent = next?.configured === false ? t.noRoot : next?.error || t.loadFailed;
        setMsg([next?.error, next?.hint].filter(Boolean).join("\n"), true);
        renderIntegrity(next);
        return;
      }
      const library = next.library ?? {};
      const counts = next.counts ?? {};
      const entries = next.entries ?? [];
      const modeDual = library.mode === "dual";
      const today = entries.filter((entry) => entry.date === todayKey()).length;
      const privateCount = modeDual ? Number(counts.private ?? 0) : 0;
      const publicCount = Number(counts.shelf_public ?? Number(counts.total ?? entries.length) - privateCount);
      sub.textContent = `${library.name || "\u2014"} \xB7 ${modeDual ? t.modeDual : t.modeSingle} \xB7 ${next.progress?.last_write || "\u2014"}`;
      status.textContent = modeDual ? `\u79C1\u5BC6\u672C ${privateCount} \u6761` : "\u5355\u672C";
      status.className = "pd-status";
      todayStat.value.textContent = String(today);
      totalStat.value.textContent = String(counts.total ?? entries.length);
      bookStat.value.textContent = String(publicCount);
      privateStat.value.textContent = modeDual ? String(privateCount) : "\u2014";
      setMsg("");
      renderIntegrity(next);
      renderEntries(entries, modeDual, next.integrity);
      renderAudit(next);
    }
    function renderIntegrity(next) {
      const summary = next?.integrity;
      integrityBody.replaceChildren();
      integritySection.dataset.status = summary?.status ?? "checking";
      if (!summary) {
        integrityBody.append(el("div", "pd-integrity-line muted", t.integrityChecking));
        return;
      }
      if (summary.status === "ok") {
        const line = el("div", "pd-integrity-line ok", integrityHeadline(summary, t));
        integrityBody.append(line);
      } else if (summary.status === "mismatch") {
        const block = el("div", "pd-integrity-bad");
        const changed = summary.changed_ids ?? summary.ids ?? [];
        const missing = summary.missing_ids ?? [];
        if (changed.length) {
          block.append(el("p", "pd-integrity-note", t.integrityNotice));
          const list = el("div", "pd-integrity-list");
          for (const id of changed) {
            const row = el("div", "pd-integrity-row");
            row.append(el("code", "pd-code", id));
            row.append(ctx.ui.button(t.integrityView, {
              size: "sm",
              onClick: () => viewEntry(id)
            }));
            list.append(row);
          }
          block.append(list);
        }
        if (missing.length) {
          block.append(el("p", "pd-integrity-note", t.integrityDeletedNotice));
          const list = el("div", "pd-integrity-list");
          for (const id of missing) {
            const row = el("div", "pd-integrity-row");
            row.append(el("code", "pd-code", id));
            row.append(ctx.ui.button(t.integrityAckDelete, {
              size: "sm",
              onClick: () => void ackDelete(id)
            }));
            list.append(row);
          }
          block.append(list);
        }
        if (!changed.length && !missing.length) {
          const list = el("div", "pd-integrity-list");
          for (const issue of summary.issues.slice(0, 8)) {
            list.append(el("div", "pd-integrity-row muted", issue));
          }
          block.append(list);
        }
        integrityBody.append(block);
      } else {
        integrityBody.append(el(
          "div",
          "pd-integrity-line muted",
          integrityHeadline(summary, t)
        ));
      }
      if (shouldAlertIntegrity(lastIntegrity, summary.status)) {
        const message = t.integrityAlert;
        ctx.ui.toast(message, "bad");
        setMsg(message, true);
      }
      lastIntegrity = summary.status;
    }
    function viewEntry(entryId) {
      const card = Array.from(entriesList.querySelectorAll("[data-entry-id]")).find((node) => node.dataset.entryId === entryId);
      if (!card) {
        setMsg(t.integrityViewMissing(entryId), true);
        return;
      }
      card.scrollIntoView({ behavior: "smooth", block: "center" });
      card.classList.add("pd-flash");
      window.setTimeout(() => card.classList.remove("pd-flash"), 1800);
    }
    function entryCard(entry, flagged = false) {
      const card = el("article", "pd-card");
      card.dataset.kind = entry.kind || "\u672A\u5206\u7C7B";
      card.dataset.entryId = entry.id;
      if (flagged) card.classList.add("pd-card-flagged");
      const top = el("div", "pd-card-top");
      top.append(el("span", "pd-time", entry.time || "\u2014"));
      top.append(el("span", "pd-book", entry.book_title || entry.book || ""));
      top.append(el("span", "pd-badge kind", entry.kind || "\u672A\u5206\u7C7B"));
      if (entry.shelf === "private") {
        top.append(el("span", "pd-badge private", "\u79C1\u5BC6\u672C"));
      }
      if (flagged) {
        top.append(el("span", "pd-badge bad", t.integrityFlagged));
      }
      card.append(top);
      card.append(el("h4", "pd-card-title", entry.title || "\uFF08\u65E0\u6807\u9898\uFF09"));
      card.append(el("p", "pd-card-body", (entry.body || "").split("\n").slice(0, 4).join("\n") || "\uFF08\u6CA1\u6709\u6B63\u6587\uFF09"));
      return card;
    }
    function renderEntries(entries, showPrivate, integrity) {
      entriesList.replaceChildren();
      const recent = entries.slice(-8).reverse();
      const flagged = new Set(integrity?.ids ?? []);
      for (const id of flagged) {
        const entry = entries.find((item) => item.id === id);
        if (entry && !recent.includes(entry)) recent.push(entry);
      }
      if (!recent.length) {
        entriesList.append(el("span", "pd-empty", t.noEntries));
        return;
      }
      const publicEntries = recent.filter((entry) => (entry.shelf || "public") !== "private");
      const privateEntries = recent.filter((entry) => entry.shelf === "private");
      if (showPrivate) {
        entriesList.append(el("h3", void 0, t.publicBook));
      }
      const pubWrap = el("div", "pd-list");
      if (publicEntries.length) {
        for (const entry of publicEntries) pubWrap.append(entryCard(entry, flagged.has(entry.id)));
      } else {
        pubWrap.append(el("span", "pd-empty", t.noEntries));
      }
      entriesList.append(pubWrap);
      if (showPrivate) {
        entriesList.append(el("h3", void 0, t.privateBook));
        const privWrap = el("div", "pd-list");
        if (privateEntries.length) {
          for (const entry of privateEntries) privWrap.append(entryCard(entry, flagged.has(entry.id)));
        } else {
          privWrap.append(el("span", "pd-empty", t.noEntries));
        }
        entriesList.append(privWrap);
      }
    }
    function renderAudit(next) {
      const audit = next.audit ?? {};
      auditLine.replaceChildren();
      const k = el("span", "k", t.auditCount);
      const v = el("span", void 0, `\u5171 ${audit.total ?? 0} \u6761 \xB7 \u8BFB ${audit.read ?? 0} \xB7 \u6539\u52A8 ${audit.edit ?? 0} \xB7 \u6784\u5EFA ${audit.build ?? 0}`);
      auditLine.append(k, v);
      auditList.replaceChildren();
      const recent = (audit.recent ?? []).slice(0, 8);
      if (!recent.length) {
        auditList.append(el("span", "pd-empty", "\u8FD8\u6CA1\u6709\u5BA1\u8BA1\u8BB0\u5F55\u3002"));
        return;
      }
      for (const item of recent) {
        const row = el("div", "pd-log-row");
        row.append(
          el("span", "muted", String(item.t ?? "").slice(11, 19) || "\u2014"),
          el("span", void 0, item.actor || "unknown"),
          el("span", void 0, item.action || "?"),
          el("span", "muted", item.entry || item.target || "\u2014")
        );
        auditList.append(row);
      }
      if (audit.chain_ok === false) {
        setMsg(`\u5BA1\u8BA1\u94FE\u5F02\u5E38\uFF1A${(audit.issues ?? []).slice(0, 3).join("\uFF1B")}`, true);
      }
    }
    async function load(force = false) {
      if (busy && !force) return;
      busy = true;
      try {
        const next = await ctx.invoke("state");
        render(next);
      } catch (error) {
        setMsg(`${t.loadFailed}\uFF1A${error instanceof Error ? error.message : String(error)}`, true);
      } finally {
        busy = false;
      }
    }
    async function verify() {
      try {
        const result = await ctx.invoke("verify");
        const message = result?.text || "\u6821\u9A8C\u5B8C\u6210";
        setMsg(message, Boolean(result?.failed));
        ctx.ui.toast(message, result?.failed ? "bad" : "ok");
      } catch (error) {
        setMsg(`\u6821\u9A8C\u5931\u8D25\uFF1A${error instanceof Error ? error.message : String(error)}`, true);
      }
    }
    async function ackDelete(entryId) {
      if (busy) return;
      busy = true;
      try {
        const result = await ctx.invoke(
          "integrity-ack-delete",
          [entryId]
        );
        const message = result?.text || "\u5DF2\u786E\u8BA4\u5220\u9664";
        setMsg(message, Boolean(result?.failed));
        ctx.ui.toast(message, result?.failed ? "bad" : "ok");
        if (!result?.failed) await load(true);
      } catch (error) {
        const message = `\u786E\u8BA4\u5220\u9664\u5931\u8D25\uFF1A${error instanceof Error ? error.message : String(error)}`;
        setMsg(message, true);
        ctx.ui.toast(message, "bad");
      } finally {
        busy = false;
      }
    }
    async function openSite() {
      if (busy) return;
      busy = true;
      try {
        const result = await ctx.invoke("openSite");
        if (result?.ok) {
          const message = t.openSiteOk(result.path || "");
          setMsg(message);
          ctx.ui.toast(message, "ok");
        } else {
          const message = t.openSiteFailed(result?.error || "\u672A\u77E5\u9519\u8BEF");
          setMsg(message, true);
          ctx.ui.toast(message, "bad");
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
          const frame = JSON.parse(raw);
          if (frame.type === "state" && frame.state) render(frame.state);
        } catch {
        }
      }
    });
    ctx.own(handle);
    await load();
  }
};
var bundle = { panels: { diary: panel } };
var diary_default = bundle;
export {
  diary_default as default
};
