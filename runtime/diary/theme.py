#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""静态页与 P2 三区页共用的样式（从 build.py 的 INDEX_TEMPLATE 原样抽出）。

- CSS：静态页完整样式。`build.py` 直接内联到 `<style>`，输出与抽取前逐字节一致。
- CARD_CSS：卡片相关样式（标签 + 卡片），`/static/app.css` 在末尾拼接这一份，
  三区页不另写一套卡片样式。
"""

from __future__ import annotations

CSS = r""":root {
  color-scheme: dark;
  --bg: #0d1017;
  --bg-soft: #121620;
  --panel: #161b25;
  --card: #1a202c;
  --line: #273042;
  --line-soft: #1f2736;
  --text: #e8ebf2;
  --text-soft: #c3cad8;
  --muted: #8b95a8;
  --accent: #7aa2ff;
  --accent-soft: rgba(122, 162, 255, .14);
  --public: #45c46a;
  --defer-bg: rgba(154, 164, 182, .12);
  --radius: 14px;
  --topbar-h: 76px;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  min-height: 100vh;
  background:
    radial-gradient(900px 500px at 15% -10%, rgba(70, 100, 180, .18), transparent 60%),
    radial-gradient(800px 500px at 100% 0%, rgba(120, 70, 160, .12), transparent 55%),
    var(--bg);
  color: var(--text);
  font-family: system-ui, -apple-system, "Segoe UI", "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif;
  font-size: 16px;
  line-height: 1.7;
}
[hidden] { display: none !important; }
button, input { font: inherit; }
button { color: inherit; }
a { color: var(--accent); }

/* ---------- 顶部工具条 ---------- */
.topbar {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 12px 28px;
  background: rgba(13, 16, 23, .86);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  border-bottom: 1px solid var(--line-soft);
}
.brand { display: flex; align-items: center; gap: 12px; min-width: 0; }
.logo {
  flex: 0 0 auto;
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border-radius: 11px;
  background: linear-gradient(135deg, #5b7cfa, #9a6bff);
  color: #fff;
  font-size: 18px;
  font-weight: 700;
  box-shadow: 0 6px 18px rgba(91, 124, 250, .28);
}
.brand h1 { margin: 0; font-size: 18px; line-height: 1.3; letter-spacing: .02em; }
.brand p {
  margin: 2px 0 0;
  font-size: 12.5px;
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.tools { display: flex; align-items: center; gap: 12px; flex: 1; justify-content: flex-end; flex-wrap: wrap; }
.sort { display: flex; align-items: center; gap: 8px; white-space: nowrap; }
.sort-label { font-size: 12.5px; color: var(--muted); }
.segment {
  display: inline-flex;
  gap: 2px;
  padding: 3px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 999px;
}
.segment button {
  padding: 4px 12px;
  background: transparent;
  border: 0;
  border-radius: 999px;
  color: var(--muted);
  font-size: 13px;
  cursor: pointer;
  transition: background .15s, color .15s;
}
.segment button:hover { color: var(--text); }
.segment button.active { background: var(--accent-soft); color: #fff; }
.segment button:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
/* 顶层「公开本 / 私密日记本」切换：两个视图互斥，默认公开。 */
.shelf-switch {
  display: inline-flex;
  gap: 3px;
  padding: 3px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 999px;
  white-space: nowrap;
}
.shelf-switch button {
  display: inline-flex;
  align-items: baseline;
  gap: 7px;
  padding: 4px 14px;
  background: transparent;
  border: 0;
  border-radius: 999px;
  color: var(--muted);
  font-size: 13.5px;
  cursor: pointer;
  transition: background .15s, color .15s;
}
.shelf-switch button:hover { color: var(--text); }
.shelf-switch button.active { background: var(--accent-soft); color: #fff; }
.shelf-switch button[data-shelf="private"].active {
  background: rgba(122, 162, 255, .2);
  color: #dfe8ff;
}
.shelf-switch button:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
.shelf-switch .shelf-count { font-size: 11px; color: var(--muted); font-variant-numeric: tabular-nums; }
.shelf-switch button.active .shelf-count { color: #a9c4ff; }
.date-range {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
  font-size: 12.5px;
  color: var(--muted);
}
.date-range input[type="date"] {
  padding: 5px 8px;
  color: var(--text-soft);
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  outline: none;
  font-size: 12.5px;
}
.date-range input[type="date"]:focus { border-color: var(--accent); }
.date-sep { color: var(--muted); }
.search { position: relative; flex: 1; max-width: 330px; min-width: 160px; }
.search input {
  width: 100%;
  padding: 9px 14px 9px 36px;
  color: var(--text);
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 999px;
  outline: none;
  transition: border-color .15s, box-shadow .15s, background .15s;
}
.search input::placeholder { color: #6f7a8e; }
.search input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); background: #171d29; }
.search::before {
  content: "⌕";
  position: absolute;
  left: 13px;
  top: 50%;
  transform: translateY(-52%);
  color: var(--muted);
  font-size: 19px;
  line-height: 1;
  pointer-events: none;
}
.switch {
  display: flex;
  align-items: center;
  gap: 9px;
  font-size: 14px;
  color: var(--text-soft);
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
}
.switch input { position: absolute; opacity: 0; width: 0; height: 0; }
.track {
  position: relative;
  flex: 0 0 auto;
  width: 44px;
  height: 24px;
  border-radius: 999px;
  background: #30394b;
  transition: background .18s;
}
.track::after {
  content: "";
  position: absolute;
  top: 3px;
  left: 3px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, .35);
  transition: transform .18s;
}
.switch input:checked + .track { background: var(--public); }
.switch input:checked + .track::after { transform: translateX(20px); }
.switch input:focus-visible + .track { outline: 2px solid var(--accent); outline-offset: 2px; }
.switch-hint { font-size: 11.5px; color: var(--muted); white-space: nowrap; }

/* ---------- 两栏布局 ---------- */
.layout {
  width: min(1320px, 100%);
  margin: 0 auto;
  padding: 24px 28px 80px;
  display: grid;
  grid-template-columns: 242px minmax(0, 1fr);
  gap: 26px;
  align-items: start;
}
.sidebar {
  position: sticky;
  top: calc(var(--topbar-h) + 16px);
  max-height: calc(100vh - var(--topbar-h) - 32px);
  overflow: auto;
  padding-right: 4px;
  scrollbar-width: thin;
  scrollbar-color: #30394b transparent;
}
.side-block + .side-block { margin-top: 20px; }
.side-block h2 {
  margin: 0 0 8px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: .12em;
  color: var(--muted);
}
#session-list, #kind-list { display: flex; flex-direction: column; gap: 3px; }
.filter-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 10px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 9px;
  text-align: left;
  cursor: pointer;
  color: var(--text-soft);
  font-size: 13.5px;
  transition: background .15s, border-color .15s, color .15s;
}
.filter-item:hover { background: var(--panel); }
.filter-item.active { background: var(--accent-soft); border-color: rgba(122, 162, 255, .35); color: #fff; }
.filter-item .filter-label { min-width: 0; overflow-wrap: anywhere; }
.filter-item .count { font-size: 11.5px; color: var(--muted); font-variant-numeric: tabular-nums; white-space: nowrap; }
.filter-item.active .count { color: #a9c4ff; }
.filter-item[data-kind="未分类"] .filter-label { color: var(--muted); }
#tag-cloud { display: flex; flex-wrap: wrap; gap: 6px; }
.tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 9px;
  background: var(--bg-soft);
  border: 1px solid var(--line);
  border-radius: 999px;
  color: var(--text-soft);
  font-size: 12.5px;
  line-height: 1.6;
  cursor: pointer;
  transition: background .15s, border-color .15s, color .15s;
}
.tag:hover { border-color: #3c4a63; color: #fff; }
.tag.active { background: var(--accent-soft); border-color: var(--accent); color: #cfe0ff; }
.tag .tag-count { color: var(--muted); font-size: 11px; font-variant-numeric: tabular-nums; }
.tag.active .tag-count { color: #a9c4ff; }
.side-empty { font-size: 12.5px; color: var(--muted); line-height: 1.7; }

/* ---------- 时间 / 类型视图 ---------- */
.timeline { min-width: 0; }
.day { scroll-margin-top: calc(var(--topbar-h) + 20px); }
.day + .day { margin-top: 34px; }
.day-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin: 0 0 14px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--line-soft);
}
.day-date { font-size: 21px; font-weight: 650; letter-spacing: .02em; }
.day-count { font-size: 12.5px; color: var(--muted); font-variant-numeric: tabular-nums; }
.session-block { margin-top: 14px; }
.session-head {
  margin: 0 0 10px;
  color: var(--muted);
  font-size: 12.5px;
  letter-spacing: .04em;
}
.session-entries { display: flex; flex-direction: column; gap: 12px; }
.intro-block {
  margin: 0 0 12px;
  padding: 10px 14px;
  background: rgba(255, 255, 255, .022);
  border: 1px dashed var(--line);
  border-radius: 10px;
  color: var(--text-soft);
  font-size: 14px;
  line-height: 1.65;
}
.intro-label { margin-bottom: 3px; color: var(--muted); font-size: 11px; letter-spacing: .12em; }
.intro-text { white-space: pre-wrap; overflow-wrap: anywhere; }

.kind-section + .kind-section { margin-top: 30px; }
.kind-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin: 0 0 12px;
  padding-bottom: 7px;
  border-bottom: 1px solid var(--line-soft);
}
.kind-name { font-size: 18px; font-weight: 650; }
.kind-count { color: var(--muted); font-size: 12.5px; font-variant-numeric: tabular-nums; }
.kind-section[data-kind="未分类"] .kind-name { color: var(--muted); }
.kind-entries { display: flex; flex-direction: column; gap: 12px; }

/* ---------- 卡片 ---------- */
.entry {
  position: relative;
  padding: 16px 18px 14px;
  background: linear-gradient(180deg, var(--card), #181e28);
  border: 1px solid var(--line-soft);
  border-left: 3px solid #3a4356;
  border-radius: var(--radius);
  box-shadow: 0 1px 0 rgba(255, 255, 255, .02);
  transition: border-color .15s, background .15s;
}
.entry:hover { border-color: #313d53; }
.entry-top { display: flex; align-items: center; flex-wrap: wrap; gap: 7px; margin-bottom: 3px; }
.entry-time {
  font-size: 13px;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
  letter-spacing: .04em;
}
.entry-time.empty-time { color: #5f6a7d; }
.book-tag {
  padding: 1px 8px;
  border: 1px solid var(--line);
  border-radius: 6px;
  color: var(--text-soft);
  background: var(--bg-soft);
  font-size: 11.5px;
  line-height: 1.7;
}
.badge {
  display: inline-flex;
  align-items: center;
  padding: 1px 8px;
  border: 1px solid transparent;
  border-radius: 999px;
  font-size: 11.5px;
  line-height: 1.7;
}
.badge.kind { color: #cfe0ff; background: var(--accent-soft); border-color: rgba(122, 162, 255, .26); }
.badge.kind[data-kind="未分类"] { color: #8b95a8; background: var(--defer-bg); border-color: rgba(154, 164, 182, .2); }
.badge.speaker { color: #e7d4ff; background: rgba(192, 132, 252, .1); border-color: rgba(192, 132, 252, .24); }
.badge.speaker::before { content: "说："; color: #b18ad6; }
.badge.tamper { color: #ffd27a; background: rgba(230, 120, 70, .16); border-color: rgba(230, 120, 70, .45); }
.entry-heading {
  margin: 0 0 8px;
  font-size: 17px;
  font-weight: 600;
  line-height: 1.55;
  overflow-wrap: anywhere;
}
.entry-chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 9px; }
.entry-chips .tag { padding: 2px 8px; font-size: 12px; }
.body-wrap { position: relative; }
.body {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
  color: var(--text-soft);
  font-size: 16px;
  line-height: 1.7;
}
.body.clamped {
  max-height: calc(6 * 1.7em);
  overflow: hidden;
  -webkit-mask-image: linear-gradient(to bottom, #000 72%, transparent 100%);
  mask-image: linear-gradient(to bottom, #000 72%, transparent 100%);
}
.body.muted { color: var(--muted); font-style: italic; }
.expand {
  margin-top: 4px;
  padding: 0;
  background: none;
  border: none;
  color: var(--accent);
  font-size: 13px;
  cursor: pointer;
}
.expand:hover { text-decoration: underline; }
.expand:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 4px; }

.empty {
  margin: 40px auto;
  max-width: 540px;
  padding: 40px 24px;
  text-align: center;
  border: 1px dashed var(--line);
  border-radius: var(--radius);
  background: rgba(255, 255, 255, .015);
  color: var(--muted);
}
.empty strong { display: block; margin-bottom: 4px; color: var(--text-soft); font-size: 16px; }
.foot {
  margin-top: 40px;
  padding-top: 14px;
  border-top: 1px solid var(--line-soft);
  color: #667085;
  font-size: 11.5px;
}
.noscript {
  margin: 24px auto;
  max-width: 720px;
  padding: 12px 16px;
  border: 1px solid #6b5b2a;
  border-radius: 10px;
  background: #2a2412;
  color: #ffe08a;
  font-size: 14px;
}

@media (max-width: 980px) {
  .topbar { flex-wrap: wrap; padding: 12px 16px; gap: 10px; }
  .brand { width: 100%; }
  .tools { flex-basis: 100%; }
  .layout { grid-template-columns: 1fr; padding: 18px 16px 60px; gap: 18px; }
  .sidebar {
    position: static;
    max-height: none;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 18px;
  }
  .side-block + .side-block { margin-top: 0; }
}
@media (max-width: 620px) {
  .sidebar { grid-template-columns: 1fr; }
  .search { max-width: none; }
  .switch-hint { display: none; }
  .day-date { font-size: 19px; }
  .entry { padding: 14px 14px 12px; }
}
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  * { transition: none !important; }
}"""

CARD_CSS = r""".tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 9px;
  background: var(--bg-soft);
  border: 1px solid var(--line);
  border-radius: 999px;
  color: var(--text-soft);
  font-size: 12.5px;
  line-height: 1.6;
  cursor: pointer;
  transition: background .15s, border-color .15s, color .15s;
}
.tag:hover { border-color: #3c4a63; color: #fff; }
.tag.active { background: var(--accent-soft); border-color: var(--accent); color: #cfe0ff; }
.tag .tag-count { color: var(--muted); font-size: 11px; font-variant-numeric: tabular-nums; }
.tag.active .tag-count { color: #a9c4ff; }

/* ---------- 卡片 ---------- */
.entry {
  position: relative;
  padding: 16px 18px 14px;
  background: linear-gradient(180deg, var(--card), #181e28);
  border: 1px solid var(--line-soft);
  border-left: 3px solid #3a4356;
  border-radius: var(--radius);
  box-shadow: 0 1px 0 rgba(255, 255, 255, .02);
  transition: border-color .15s, background .15s;
}
.entry:hover { border-color: #313d53; }
.entry-top { display: flex; align-items: center; flex-wrap: wrap; gap: 7px; margin-bottom: 3px; }
.entry-time {
  font-size: 13px;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
  letter-spacing: .04em;
}
.entry-time.empty-time { color: #5f6a7d; }
.book-tag {
  padding: 1px 8px;
  border: 1px solid var(--line);
  border-radius: 6px;
  color: var(--text-soft);
  background: var(--bg-soft);
  font-size: 11.5px;
  line-height: 1.7;
}
.badge {
  display: inline-flex;
  align-items: center;
  padding: 1px 8px;
  border: 1px solid transparent;
  border-radius: 999px;
  font-size: 11.5px;
  line-height: 1.7;
}
.badge.kind { color: #cfe0ff; background: var(--accent-soft); border-color: rgba(122, 162, 255, .26); }
.badge.kind[data-kind="未分类"] { color: #8b95a8; background: var(--defer-bg); border-color: rgba(154, 164, 182, .2); }
.badge.speaker { color: #e7d4ff; background: rgba(192, 132, 252, .1); border-color: rgba(192, 132, 252, .24); }
.badge.speaker::before { content: "说："; color: #b18ad6; }
.badge.tamper { color: #ffd27a; background: rgba(230, 120, 70, .16); border-color: rgba(230, 120, 70, .45); }
.entry-heading {
  margin: 0 0 8px;
  font-size: 17px;
  font-weight: 600;
  line-height: 1.55;
  overflow-wrap: anywhere;
}
.entry-chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 9px; }
.entry-chips .tag { padding: 2px 8px; font-size: 12px; }
.body-wrap { position: relative; }
.body {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
  color: var(--text-soft);
  font-size: 16px;
  line-height: 1.7;
}
.body.clamped {
  max-height: calc(6 * 1.7em);
  overflow: hidden;
  -webkit-mask-image: linear-gradient(to bottom, #000 72%, transparent 100%);
  mask-image: linear-gradient(to bottom, #000 72%, transparent 100%);
}
.body.muted { color: var(--muted); font-style: italic; }
.expand {
  margin-top: 4px;
  padding: 0;
  background: none;
  border: none;
  color: var(--accent);
  font-size: 13px;
  cursor: pointer;
}
.expand:hover { text-decoration: underline; }
.expand:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 4px; }"""

__all__ = ["CSS", "CARD_CSS"]
