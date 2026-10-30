#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""桌宠日记 P2 本地服务：三区界面 + 右侧竖条贴片 + SSE。

用法：
    python diary/serve.py --root <库目录> [--port 8777] [--host 127.0.0.1]

只用标准库：
- `http.server.ThreadingHTTPServer` 提供 6 条路由；
- 后台线程每 400ms 轮询库内关键文件的 (mtime_ns, size)；
- SSE 每个客户端一个 `queue.Queue`，死连接移出列表，不拖累其他连接。

页面读取只走 `store.inspect_library(record=False, register=False)`：
打开页面本身不写审计，本服务只读；只有 `build.py` 写账。
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import queue
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

# 允许 `python diary/serve.py` 和 `python -m diary.serve` 两种跑法。
sys.path.insert(0, str(Path(__file__).resolve().parent))
import parser  # noqa: E402
import store  # noqa: E402
import theme  # noqa: E402

WEB_DIR = Path(__file__).resolve().parent / "web"
KIND_ORDER = parser.KINDS
WATCH_INTERVAL = 0.4
HEARTBEAT_SECONDS = 15


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------


def esc(value: Any) -> str:
    return html_lib.escape("" if value is None else str(value), quote=True)


def json_for_script(value: Any) -> str:
    """放进 <script type="application/json">，防止正文里的 </script> 截断页面。"""
    text = json.dumps(value, ensure_ascii=False, indent=2)
    return (
        text.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def relative_time(timestamp: float | None, now: float | None = None) -> str:
    if timestamp is None:
        return "—"
    now = time.time() if now is None else now
    delta = max(0.0, now - timestamp)
    if delta < 60:
        return "刚刚"
    if delta < 3600:
        return f"{int(delta // 60)} 分钟前"
    if delta < 86400:
        return f"{int(delta // 3600)} 小时前"
    return f"{int(delta // 86400)} 天前"


def _date_key(value: str | None) -> tuple[int, str]:
    if not value:
        return (1, "")
    return (0, value)


def _entry_sort_key(item: tuple[int, dict[str, Any]]) -> tuple[Any, ...]:
    index, entry = item
    date_value = entry.get("date") or ""
    time_value = entry.get("time")
    return (
        _date_key(date_value),
        (1, "") if not time_value else (0, time_value),
        index,
    )


# ---------------------------------------------------------------------------
# 数据解析：库、cast、threads、进度
# ---------------------------------------------------------------------------


def _parse_library_docs(root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """逐文件解析，坏一个只记 warning，不让整个 state 失败。

    文件清单来自 `store.library_sources`：双日记模式下 private/ 与公开本一起读。
    """
    docs: list[dict[str, Any]] = []
    warnings: list[str] = []
    books = store.load_library_books(root)
    try:
        sources = store.library_sources(root)
    except OSError as exc:
        return docs, [f"库目录读取失败：{exc}"]
    for path, relative, namespace in sources:
        try:
            doc = parser.parse_file(
                path,
                books_override=books,
                id_namespace=namespace,
                file_label=relative,
            )
            doc["scope"] = "private" if namespace.startswith("private/") else "public"
            for entry in doc.get("entries", []):
                entry["shelf"] = doc["scope"]
            docs.append(doc)
        except Exception as exc:  # noqa: BLE001  （单文件坏掉不能拖垮整本库）
            warnings.append(f"{relative} 解析失败：{exc}")
    return docs, warnings


def _parse_note_dir(
    root: Path, sub: str, default_status: str
) -> tuple[list[dict[str, Any]], list[str]]:
    """解析 cast/threads：第一行 # 名字，状态行可选，其余第一行非空文本做简介。"""
    items: list[dict[str, Any]] = []
    issues: list[str] = []
    directory = root / sub
    if not directory.is_dir():
        return items, issues
    try:
        files = sorted(
            (p for p in directory.iterdir() if p.is_file() and p.suffix.lower() == ".md"),
            key=lambda p: p.name,
        )
    except OSError:
        return items, [f"{sub}/ 读取失败"]

    for path in files:
        rel = f"{sub}/{path.name}"
        try:
            text = parser._read_text(path)  # noqa: SLF001  （与解析器共用编码兜底）
        except OSError:
            issues.append(f"{rel} 解析失败")
            continue

        lines = text.splitlines()
        first = next((i for i, line in enumerate(lines) if line.strip()), None)
        if first is None:
            issues.append(f"{rel} 解析失败")
            continue
        heading = re.match(r"^\s*#\s+(.+?)\s*$", lines[first])
        if not heading or not heading.group(1).strip():
            issues.append(f"{rel} 解析失败")
            continue

        name = heading.group(1).strip()
        status: str | None = None
        note = ""
        for line in lines[first + 1 :]:
            if not line.strip():
                continue
            state_match = re.match(r"^\s*状态\s*[:：]\s*(.*?)\s*$", line)
            if state_match and status is None:
                status = state_match.group(1).strip() or None
                continue
            if not note:
                note = line.strip()

        if sub == "cast":
            items.append({"name": name, "status": status or default_status, "note": note})
        else:
            items.append(
                {"title": name, "status": status or default_status, "note": note, "file": rel}
            )
    return items, issues


def _latest_mtime(root: Path) -> tuple[float | None, str]:
    latest: float | None = None
    allowed = {path.resolve() for path, _, _ in store.library_sources(root)}
    try:
        for path in root.rglob("*.md"):
            try:
                if not path.is_file() or path.resolve() not in allowed:
                    continue
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if latest is None or mtime > latest:
                latest = mtime
    except OSError:
        return None, "—"
    return latest, relative_time(latest)


def build_state(root: Path, root_label: str | None = None) -> dict[str, Any]:
    """组装 `/api/state` 的完整 JSON；不写审计、不登记指纹。"""
    root = Path(root)
    index = store.load_index(root) or {}
    mode = store.library_mode(root)

    docs, warnings = _parse_library_docs(root)
    check = store.inspect_library(root, record=False, register=False, docs=docs)
    payload = parser.assemble(check["docs"])

    changed_ids = {entry.get("id") for entry in check["changed"]}
    entries: list[dict[str, Any]] = []
    for entry in payload["entries"]:
        item = dict(entry)
        item["tampered"] = item.get("id") in changed_ids
        if not item.get("shelf"):
            item["shelf"] = "public"
        if item.get("kind") not in KIND_ORDER:
            item["kind"] = "未分类"
        entries.append(item)

    books = payload["books"]
    book_count = len(books)
    total = len(entries)
    private_count = sum(1 for entry in entries if entry.get("shelf") == "private")

    progress_docs = [doc for doc in check["docs"] if doc.get("entries")]
    latest_doc = None
    for doc in progress_docs:
        # 日期是 ISO 字符串，直接按字典序取最大；同一天取文件顺序靠后的那本。
        if latest_doc is None or (doc.get("date") or "") >= (latest_doc.get("date") or ""):
            latest_doc = doc
    latest_date = (latest_doc.get("date") or "") if latest_doc else ""
    latest_book = (latest_doc.get("book") or "") if latest_doc else ""
    today_entries = len(latest_doc.get("entries", [])) if latest_doc else 0
    _, last_write = _latest_mtime(root)

    cast, cast_issues = _parse_note_dir(root, "cast", "在场")
    threads, thread_issues = _parse_note_dir(root, "threads", "未解")

    audit_records = store.load_audit(root)
    chain_issues, _ = store.verify_audit(root)
    action_counts = {"read": 0, "edit": 0}
    for record in audit_records:
        action = record.get("action")
        if action in action_counts:
            action_counts[action] += 1
    build_count = sum(1 for record in audit_records if record.get("via") == "build")

    recent_actions: list[dict[str, Any]] = []
    for record in reversed(audit_records):
        recent_actions.append(
            {
                "t": record.get("t"),
                "actor": record.get("actor"),
                "action": record.get("action"),
                "target": record.get("target"),
                "entry": record.get("entry"),
                "via": record.get("via"),
                "note": record.get("note"),
                "external": record.get("actor") == "unknown"
                and record.get("action") == "edit",
            }
        )
        if len(recent_actions) >= 8:
            break

    external_records = [
        record
        for record in audit_records
        if record.get("actor") == "unknown" and record.get("action") == "edit"
    ]
    external_summary = {
        "count": len(external_records),
        "entries": sorted(
            {
                str(record.get("entry") or record.get("target") or "?")
                for record in external_records
            }
        ),
        "latest": external_records[-1].get("t") if external_records else None,
    }

    return {
        "library": {
            "name": index.get("name") or root.name,
            "mode": mode,
            "dual_diary": mode == "dual",
            "root": root_label if root_label is not None else str(root),
        },
        "counts": {
            "total": total,
            "private": private_count,
            "shelf_public": total - (private_count or 0),
            "books": book_count,
            "changed": len(check["changed"]),
        },
        "books": books,
        "kinds": list(KIND_ORDER),
        "docs": [
            {
                "file": doc.get("file", ""),
                "book": doc.get("book", ""),
                "date": doc.get("date"),
                "intro": doc.get("intro", ""),
                "scope": doc.get("scope", "public"),
            }
            for doc in payload["docs"]
        ],
        "entries": entries,
        "audit": {
            "total": len(audit_records),
            "read": action_counts["read"],
            "edit": action_counts["edit"],
            "build": build_count,
            "chain_ok": not chain_issues,
            "issues": list(chain_issues) + list(cast_issues) + list(thread_issues),
            "recent": recent_actions,
            "external": external_summary,
        },
        "cast": cast,
        "threads": threads,
        "progress": {
            "latest_date": latest_date,
            "latest_book": latest_book,
            "last_write": last_write,
            "today_entries": today_entries,
        },
        "warnings": warnings,
        "generated_at": store.now_iso(),
    }


# ---------------------------------------------------------------------------
# 状态缓存 / 文件监听 / SSE 广播
# ---------------------------------------------------------------------------


class StateHub:
    def __init__(self, root: Path, root_label: str):
        self.root = Path(root)
        self.root_label = root_label
        self._lock = threading.RLock()
        self._state: dict[str, Any] | None = None
        self._signature: tuple[Any, ...] | None = None
        self._clients: list[queue.Queue] = []
        self._clients_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _watched_paths(self) -> list[Path]:
        # 只监听本次允许读的 md；开关关着时 private/ 不进监听表。
        paths = [path for path, _, _ in store.library_sources(self.root)]
        for sub in ("cast", "threads"):
            directory = self.root / sub
            if not directory.is_dir():
                continue
            try:
                for path in directory.iterdir():
                    if path.is_file() and path.suffix.lower() == ".md":
                        paths.append(path)
            except OSError:
                pass
        for name in (store.INDEX_NAME, store.AUDIT_NAME, f"{store.STATE_DIR}/{store.HASHES_NAME}"):
            paths.append(self.root / name)
        return paths

    def _snapshot(self) -> tuple[Any, ...]:
        rows: list[tuple[str, int, int]] = []
        for path in sorted(self._watched_paths(), key=lambda p: str(p).lower()):
            try:
                rel = path.relative_to(self.root).as_posix()
            except ValueError:
                rel = str(path)
            try:
                stat = path.stat()
                rows.append((rel, stat.st_mtime_ns, stat.st_size))
            except OSError:
                rows.append((rel, -1, -1))
        return tuple(rows)

    def refresh(self, force: bool = False) -> tuple[dict[str, Any], bool]:
        signature = self._snapshot()
        with self._lock:
            if not force and self._state is not None and signature == self._signature:
                return self._state, False
            state = build_state(self.root, self.root_label)
            self._state = state
            self._signature = signature
            return state, True

    def get_state(self) -> dict[str, Any]:
        state, changed = self.refresh()
        if changed:
            self.notify(state)
        else:
            # 文件没变时也把「12 分钟前」这类相对时间刷新一下，别一直停在旧值。
            _, last_write = _latest_mtime(self.root)
            with self._lock:
                state["progress"]["last_write"] = last_write
        return state

    def add_client(self, client: queue.Queue) -> None:
        with self._clients_lock:
            self._clients.append(client)

    def remove_client(self, client: queue.Queue) -> None:
        with self._clients_lock:
            try:
                self._clients.remove(client)
            except ValueError:
                pass

    def notify(self, state: dict[str, Any]) -> None:
        with self._clients_lock:
            clients = list(self._clients)
        for client in clients:
            try:
                client.put_nowait(state)
            except queue.Full:
                # 慢客户端只保留最新一帧，绝不阻塞广播。
                try:
                    client.get_nowait()
                except queue.Empty:
                    pass
                try:
                    client.put_nowait(state)
                except queue.Full:
                    pass

    def _watch(self) -> None:
        while not self._stop.wait(WATCH_INTERVAL):
            try:
                state, changed = self.refresh()
                if changed:
                    self.notify(state)
            except Exception as exc:  # noqa: BLE001  （监听线程不能因为一次解析失败退出）
                print(f"监听警告：{exc}", file=sys.stderr)

    def start(self) -> None:
        self.get_state()
        self._thread = threading.Thread(target=self._watch, name="diary-watch", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)


# ---------------------------------------------------------------------------
# HTML 渲染
# ---------------------------------------------------------------------------


def _book_title(state: dict[str, Any], book: str) -> str:
    for record in state.get("books", []):
        if record.get("book") == book:
            return record.get("book_title") or book
    return book or "未命名"


def _session_rows(state: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for position, entry in enumerate(state.get("entries", [])):
        book = entry.get("book") or ""
        date_value = entry.get("date") or "未标注日期"
        key = (book, date_value)
        if key not in index:
            index[key] = {
                "book": book,
                "date": date_value,
                "count": 0,
                "items": [],
            }
            rows.append(index[key])
        row = index[key]
        row["count"] += 1
        row["items"].append((position, entry))

    order = {
        record.get("book"): i for i, record in enumerate(state.get("books", []))
    }
    rows.sort(key=lambda row: (_date_key(row["date"]), order.get(row["book"], 999)))
    return rows


def _doc_map(state: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (doc.get("book") or "", doc.get("date") or ""): doc
        for doc in state.get("docs", [])
    }


def render_card(state: dict[str, Any], entry: dict[str, Any]) -> str:
    kind = entry.get("kind") or "未分类"
    time_value = entry.get("time")
    title = entry.get("title") or entry.get("heading") or "（无标题）"
    book_title = entry.get("book_title") or _book_title(state, entry.get("book") or "")
    body = entry.get("body") or ""
    body_html_class = "body muted" if not body else "body"
    body_text = body if body else "（这条没有正文）"
    clamped = bool(body) and len(body.split("\n")) > 6
    if clamped:
        body_html_class += " clamped"

    top: list[str] = []
    time_class = "entry-time" if time_value else "entry-time empty-time"
    top.append(
        f'<time class="{time_class}" datetime="{esc(time_value or "")}">'
        f'{esc(time_value or "—")}</time>'
    )
    top.append(f'<span class="book-tag">{esc(book_title)}</span>')
    top.append(
        f'<span class="badge kind" data-kind="{esc(kind)}">{esc(kind)}</span>'
    )
    if entry.get("speaker"):
        top.append(
            f'<span class="badge speaker" data-speaker="{esc(entry.get("speaker"))}">'
            f'{esc(entry.get("speaker"))}</span>'
        )
    if entry.get("tampered"):
        top.append(
            '<span class="badge tamper" title="指纹和上次登记的对不上；用 admin.py diff 看原话">'
            "⚠ 被外部修改</span>"
        )

    tags_html = ""
    tags = entry.get("tags") or []
    if tags:
        chips = "".join(
            f'<span class="tag"><span class="tag-name">#{esc(tag)}</span></span>'
            for tag in tags
        )
        tags_html = f'<div class="entry-chips">{chips}</div>'

    expand = (
        '<button type="button" class="expand" aria-expanded="false">展开全文 ▾</button>'
        if clamped
        else ""
    )

    return (
        f'<article class="entry" data-id="{esc(entry.get("id"))}" '
        f'data-kind="{esc(kind)}" '
        f'data-shelf="{esc(entry.get("shelf") or "public")}" '
        f'data-book="{esc(entry.get("book"))}" data-date="{esc(entry.get("date") or "")}">'
        f'<div class="entry-top">{"".join(top)}</div>'
        f'<h3 class="entry-heading">{esc(title)}</h3>'
        f"{tags_html}"
        f'<div class="body-wrap"><div class="{body_html_class}">{esc(body_text)}</div></div>'
        f"{expand}"
        "</article>"
    )


def render_sidebar(state: dict[str, Any]) -> str:
    entries = state.get("entries", [])
    # 默认公开本：服务端先渲染公开本；私密本由前端顶部开关切换后再渲染。
    active = [
        entry for entry in entries
        if (entry.get("shelf") or "public") != "private"
    ]

    session_buttons: list[str] = []
    for row in _session_rows(dict(state, entries=active)):
        label = f"{_book_title(state, row['book'])} · {row['date']}"
        session_buttons.append(
            f'<button type="button" class="filter-item" data-book="{esc(row["book"])}" '
            f'data-date="{esc(row["date"])}">'
            f'<span class="filter-label">{esc(label)}</span>'
            f'<span class="count">{row["count"]} 条</span></button>'
        )
    if not session_buttons:
        session_buttons.append('<span class="side-empty">还没有场次。</span>')

    kind_counts = {kind: 0 for kind in KIND_ORDER}
    for entry in active:
        kind = entry.get("kind") or "未分类"
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
    kind_buttons = "".join(
        f'<button type="button" class="filter-item" data-kind="{esc(kind)}">'
        f'<span class="filter-label">{esc(kind)}</span>'
        f'<span class="count">{kind_counts.get(kind, 0)} 条</span></button>'
        for kind in KIND_ORDER
    )

    return (
        '<section class="side-block"><h2>场次</h2>'
        f'<nav id="session-list" aria-label="场次列表">{"".join(session_buttons)}</nav></section>'
        '<section class="side-block"><h2>类型</h2>'
        f'<nav id="kind-list" aria-label="类型列表">{kind_buttons}</nav></section>'
        '<section class="side-block"><h2>筛选</h2>'
        '<p class="side-hint">类型多选是 AND；排序只有时间正序 / 倒序。'
        "公开本与私密本分开放，点页面顶部的「公开本 / 私密日记本」切换。</p></section>"
    )


def render_timeline(state: dict[str, Any]) -> str:
    entries = [
        entry for entry in state.get("entries", [])
        if (entry.get("shelf") or "public") != "private"
    ]
    if not entries:
        return (
            '<div class="empty-state"><strong>还没有日记</strong>'
            "<span>把 YYYY-MM-DD-slug.md 放进库目录，再刷新。</span></div>"
        )

    rows = _session_rows(dict(state, entries=entries))
    docs = _doc_map(state)
    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_date.setdefault(row["date"], []).append(row)

    sections: list[str] = []
    for date_value in sorted(by_date, key=_date_key):
        date_rows = by_date[date_value]
        count = sum(row["count"] for row in date_rows)
        blocks: list[str] = []
        for row in date_rows:
            doc = docs.get((row["book"], "" if row["date"] == "未标注日期" else row["date"]), {})
            intro = doc.get("intro") or ""
            intro_html = ""
            if intro:
                intro_html = (
                    '<div class="intro-block"><div class="intro-label">开场</div>'
                    f'<div class="intro-text">{esc(intro)}</div></div>'
                )
            cards = "".join(
                render_card(state, entry)
                for _, entry in sorted(row["items"], key=_entry_sort_key)
            )
            blocks.append(
                f'<div class="session-block" data-book="{esc(row["book"])}" '
                f'data-date="{esc(row["date"])}">'
                f'<div class="session-head">——《{esc(_book_title(state, row["book"]))}》'
                f'{esc(row["date"])} ——</div>{intro_html}'
                f'<div class="session-entries">{cards}</div></div>'
            )
        sections.append(
            f'<section class="day" data-date="{esc(date_value)}">'
            f'<div class="day-head"><span class="day-date">{esc(date_value)}</span>'
            f'<span class="day-count">{count} 条</span></div>'
            f'{"".join(blocks)}</section>'
        )
    return "".join(sections)


def _short_time(value: Any) -> str:
    text = str(value or "")
    if "T" in text and len(text) >= 19:
        return text[11:19]
    return text or "—"


def render_status(state: dict[str, Any]) -> str:
    counts = state.get("counts", {})
    progress = state.get("progress", {})
    library = state.get("library", {})
    audit = state.get("audit", {})
    latest_date = progress.get("latest_date") or "—"
    latest_book = progress.get("latest_book") or ""
    latest_title = _book_title(state, latest_book) if latest_book else "—"

    cast_cards = "".join(
        f'<div class="cast-card"><div class="cast-top"><span class="cast-name">{esc(person.get("name"))}</span>'
        f'<span class="cast-status">{esc(person.get("status"))}</span></div>'
        f'<div class="cast-note">{esc(person.get("note") or "（没有简介）")}</div></div>'
        for person in state.get("cast", [])[:3]
    ) or '<span class="side-empty">还没有 cast/。</span>'

    unresolved = [thread for thread in state.get("threads", []) if thread.get("status") == "未解"]
    thread_cards = "".join(
        f'<div class="thread-card"><div class="thread-title">{esc(thread.get("title"))}</div>'
        f'<div class="thread-note">{esc(thread.get("note") or "（没有补充）")}</div></div>'
        for thread in unresolved[:5]
    ) or '<span class="side-empty">暂无未解伏笔。</span>'

    audit_line = (
        f'读过 {int(audit.get("read") or 0)} · '
        f'外部改动 {int(counts.get("changed") or 0)} · 构建 {int(audit.get("build") or 0)}'
    )
    chain_ok = bool(audit.get("chain_ok", True))
    chain_html = (
        ""
        if chain_ok
        else f'<div class="audit-warn">⚠ 审计链异常（{len(audit.get("issues") or [])} 处）</div>'
    )

    recent_rows = "".join(
        '<div class="audit-row{external}">'
        '<span class="audit-time">{time}</span>'
        '<span class="audit-actor">{actor}</span>'
        '<span class="audit-action">{action}</span>'
        '<span class="audit-target">{target}</span>'
        "</div>".format(
            external=" external" if item.get("external") else "",
            time=esc(_short_time(item.get("t"))),
            actor=esc(item.get("actor") or "unknown"),
            action=esc(item.get("action") or "?"),
            target=esc(item.get("entry") or item.get("target") or "—"),
        )
        for item in (audit.get("recent") or [])
    ) or '<span class="side-empty">还没有审计记录。</span>'

    external = audit.get("external") or {}
    external_count = int(external.get("count") or 0)
    external_entries = external.get("entries") or []
    if external_count:
        external_html = (
            f'<div class="kv"><span>次数</span><b>{external_count} 次</b></div>'
            f'<div class="kv"><span>涉及条目</span><b>{esc("、".join(external_entries[:3]))}'
            f'{" 等" if len(external_entries) > 3 else ""}</b></div>'
            f'<div class="kv"><span>最近</span><b>{esc(_short_time(external.get("latest")))}</b></div>'
        )
    else:
        external_html = '<span class="side-empty">还没有外部改动记录。</span>'

    mode = library.get("mode") or "single"
    private_count = int(counts.get("private") or 0)
    if mode != "dual":
        privacy_html = (
            '<p class="side-hint">当前是单本模式。切到双日记后，'
            "公开本与私密本会分开存放、一起读取。</p>"
        )
    else:
        privacy_html = (
            f'<div class="kv"><span>公开本</span>'
            f'<b>{int(counts.get("shelf_public") or 0)} 条</b></div>'
            f'<div class="kv"><span>私密本</span><b>{private_count} 条</b></div>'
            '<p class="side-hint">私密是分类，不是锁：页面、Coo 工具、'
            "serve 与导出都能正常读写私密本。</p>"
        )

    return (
        '<section class="status-block"><h2>进度</h2>'
        f'<div class="kv"><span>库</span><b>{esc(library.get("name") or "—")}</b></div>'
        f'<div class="kv"><span>最新</span><b>{esc(latest_date)} · {esc(latest_title)}</b></div>'
        f'<div class="kv"><span>当日</span><b>{int(progress.get("today_entries") or 0)} 条</b></div>'
        f'<div class="kv"><span>最后写入</span><b>{esc(progress.get("last_write") or "—")}</b></div>'
        "</section>"
        f'<section class="status-block"><h2>人物</h2>{cast_cards}</section>'
        f'<section class="status-block"><h2>未解伏笔</h2>{thread_cards}</section>'
        f'<section class="status-block"><h2>审计</h2><div class="audit-line">{audit_line}</div>'
        f"{chain_html}</section>"
        f'<section class="status-block"><h2>最近动作</h2>{recent_rows}</section>'
        f'<section class="status-block"><h2>谁动过我日记</h2>{external_html}</section>'
        f'<section class="status-block"><h2>隐私</h2>{privacy_html}</section>'
    )


def _overlay_public(state: dict[str, Any]) -> list[dict[str, Any]]:
    """最近 3 条可上贴片的条目：整个公开本，按库内条目顺序取末尾。

    私密本是硬红线：shelf=private 的条目任何情况下都被排除。
    """
    pool = [
        entry
        for entry in state.get("entries", [])
        if (entry.get("shelf") or "public") != "private"
    ]
    return pool[-3:]


def _overlay_entry_html(entry: dict[str, Any], state: dict[str, Any]) -> str:
    body = entry.get("body") or ""
    first_two = "\n".join(body.split("\n")[:2]) if body else "（没有正文）"
    return (
        f'<article class="ov-entry" data-id="{esc(entry.get("id"))}">'
        f'<div class="ov-meta"><span class="ov-time">{esc(entry.get("time") or "—")}</span>'
        f'<span class="ov-book">{esc(entry.get("book_title") or _book_title(state, entry.get("book") or ""))}</span></div>'
        f'<h3 class="ov-title">{esc(entry.get("title") or entry.get("heading") or "（无标题）")}</h3>'
        f'<p class="ov-body">{esc(first_two)}</p></article>'
    )


def _overlay_entries_html(state: dict[str, Any]) -> str:
    public = _overlay_public(state)
    if not public:
        return '<div class="ov-empty">暂无公开记录</div>'
    return "".join(_overlay_entry_html(entry, state) for entry in public)


def _overlay_cast_html(state: dict[str, Any]) -> str:
    people = state.get("cast", [])[:3]
    if not people:
        return ""
    return "".join(
        f'<div class="ov-cast-card"><span class="ov-cast-name">{esc(person.get("name"))}</span>'
        f'<span class="ov-cast-status">{esc(person.get("status"))}</span>'
        f'<div class="ov-cast-note">{esc(person.get("note") or "")}</div></div>'
        for person in people
    )


def _overlay_threads_html(state: dict[str, Any]) -> str:
    unresolved = [thread for thread in state.get("threads", []) if thread.get("status") == "未解"]
    if not unresolved:
        return '<div class="ov-threads-empty">暂无未解伏笔</div>'
    head = f'<div class="ov-threads-head">未解伏笔 ×{len(unresolved)}</div>'
    shown = "".join(
        f'<div class="ov-thread"><span class="ov-thread-title">{esc(thread.get("title"))}</span>'
        f'<span class="ov-thread-note">{esc(thread.get("note") or "")}</span></div>'
        for thread in unresolved[:3]
    )
    more = (
        f'<div class="ov-thread-more">+{len(unresolved) - 3}</div>'
        if len(unresolved) > 3
        else ""
    )
    return head + shown + more


def render_overlay_page(state: dict[str, Any]) -> str:
    public = _overlay_public(state)
    entries_label = "最近 3 条 · 公开"
    overlay_payload = {
        "entries": public,
        "cast": state.get("cast", [])[:3],
        "threads": [t for t in state.get("threads", []) if t.get("status") == "未解"],
        "generated_at": state.get("generated_at"),
    }
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<title>桌宠日记 · 贴片</title>
<link rel="icon" href="data:,">
<link rel="stylesheet" href="/static/app.css">
</head>
<body data-page="overlay">
<div id="overlay" class="overlay">
  <section class="ov-section ov-entries-section">
    <div class="ov-label">{entries_label}</div>
    <div id="ov-entries" class="ov-entries">{_overlay_entries_html(state)}</div>
  </section>
  <section class="ov-section ov-cast-section" id="ov-cast-section">
    {_overlay_cast_html(state)}
  </section>
  <section class="ov-section ov-threads-section">
    <div id="ov-threads">{_overlay_threads_html(state)}</div>
  </section>
</div>
<script type="application/json" id="overlay-data">{json_for_script(overlay_payload)}</script>
<script src="/static/app.js"></script>
</body>
</html>
"""


def render_app_page(state: dict[str, Any]) -> str:
    counts = state.get("counts", {})
    library = state.get("library", {})
    public_count = int(counts.get("shelf_public") or 0)
    private_count = int(counts.get("private") or 0)
    stats = (
        f"公开本 {public_count} 条 · 私密本 {private_count} 条 · "
        f"当前显示 {public_count} 条"
    )
    changed = int(counts.get("changed") or 0)
    warning = (
        f'<div class="changed-warning" id="changed-warning">⚠ {changed} 条被外部修改</div>'
        if changed
        else '<div class="changed-warning" id="changed-warning" hidden></div>'
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<title>桌宠日记 · 三区</title>
<link rel="icon" href="data:,">
<link rel="stylesheet" href="/static/app.css">
</head>
<body data-page="app">
<header class="app-topbar">
  <div class="brand"><div class="logo" aria-hidden="true">日</div>
    <div><h1>桌宠日记</h1><p id="subtitle">{esc(state.get("library", {}).get("name") or "—")} · 公开 / 私密两本{"" if state.get("library", {}).get("mode") == "dual" else "（单本）"}</p></div>
  </div>
  <div class="topbar-stats" id="stats">{stats}</div>
</header>
<div class="app-layout">
  <aside class="app-sidebar" aria-label="筛选">{render_sidebar(state)}</aside>
  <main class="app-main">
    <div class="app-toolbar">
      <div class="shelf-switch" id="shelf-switch" role="group" aria-label="日记本切换">
        <button type="button" data-shelf="public" class="active" aria-pressed="true">
          <span class="shelf-name">公开本</span><span class="shelf-count">{public_count} 条</span>
        </button>
        <button type="button" data-shelf="private" aria-pressed="false">
          <span class="shelf-name">私密日记本</span><span class="shelf-count">{private_count} 条</span>
        </button>
      </div>
      <div class="sort"><span class="sort-label">排序</span>
        <div class="segment" id="sort-control" role="group" aria-label="时间排序方向">
          <button type="button" data-order="desc" class="active" aria-pressed="true">倒序</button>
          <button type="button" data-order="asc" aria-pressed="false">正序</button>
        </div>
      </div>
      <div class="date-range">
        <span class="sort-label">日期</span>
        <input id="date-from" type="date" aria-label="起始日期">
        <span class="date-sep">至</span>
        <input id="date-to" type="date" aria-label="结束日期">
      </div>
      <label class="search"><input id="search" type="search" placeholder="搜索标题或正文…" autocomplete="off" spellcheck="false" aria-label="搜索标题或正文"></label>
    </div>
    {warning}
    <div id="empty" class="empty" hidden>
      <strong id="empty-title">没有符合条件的条目</strong>
      <span id="empty-hint">换个关键词或取消筛选试试。</span>
    </div>
    <div id="time-view">{render_timeline(state)}</div>
    <footer class="foot">桌宠日记 · 数据源：markdown · 本地只读服务 · 公开本与私密本分开存放</footer>
  </main>
  <aside class="app-status" id="status" aria-label="状态栏">{render_status(state)}</aside>
</div>
<script type="application/json" id="diary-data">{json_for_script(state)}</script>
<script src="/static/filter.js"></script>
<script src="/static/app.js"></script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


class DiaryServer(ThreadingHTTPServer):
    daemon_threads = True
    # Windows 上 SO_REUSEADDR 会让已被占用的端口也能绑上；这里必须关掉，
    # 否则「端口被占 → 退出码 1」的验收会变成假成功。
    allow_reuse_address = False


class DiaryHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "DiaryP2/1.0"

    # ---- 基础响应 ----

    def _send_bytes(self, code: int, data: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

    def _send_text(self, code: int, text: str, content_type: str = "text/plain; charset=utf-8") -> None:
        self._send_bytes(code, text.encode("utf-8"), content_type)

    def _send_json(self, code: int, value: Any) -> None:
        data = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
        self._send_bytes(code, data, "application/json; charset=utf-8")

    def _not_found(self) -> None:
        self._send_text(404, "404 没有这个页面\n")

    # ---- GET ----

    def do_GET(self) -> None:  # noqa: N802 （BaseHTTPRequestHandler 的约定）
        path = urlsplit(self.path).path
        hub: StateHub = self.server.hub  # type: ignore[attr-defined]
        site = self.server.site  # type: ignore[attr-defined]

        if path == "/":
            self._send_text(200, render_app_page(hub.get_state()), "text/html; charset=utf-8")
            return
        if path == "/overlay":
            self._send_text(200, render_overlay_page(hub.get_state()), "text/html; charset=utf-8")
            return
        if path == "/api/state":
            self._send_json(200, hub.get_state())
            return
        if path == "/api/events":
            self._stream_events(hub)
            return
        if path == "/healthz":
            state = hub.get_state()
            self._send_json(200, {"ok": True, "entries": len(state.get("entries", []))})
            return
        if path == "/static/app.css":
            self._send_bytes(200, site["css"], "text/css; charset=utf-8")
            return
        if path == "/static/app.js":
            self._send_bytes(200, site["js"], "application/javascript; charset=utf-8")
            return
        if path == "/static/filter.js":
            self._send_bytes(200, site["filter_js"], "application/javascript; charset=utf-8")
            return
        self._not_found()

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    # ---- SSE ----

    def _stream_events(self, hub: StateHub) -> None:
        client: queue.Queue = queue.Queue(maxsize=8)
        hub.add_client(client)
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-transform")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()

            # 首帧：当前完整 state；紧跟着 retry，断线后 1 秒重连。
            self._write_sse_state(hub.get_state())
            self.wfile.write(b"retry: 1000\n\n")
            self.wfile.flush()

            while not hub._stop.is_set():  # noqa: SLF001
                try:
                    state = client.get(timeout=HEARTBEAT_SECONDS)
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    continue
                self._write_sse_state(state)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            hub.remove_client(client)
            self.close_connection = True

    def _write_sse_state(self, state: dict[str, Any]) -> None:
        data = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.wfile.write(f"event: state\ndata: {data}\n\n".encode("utf-8"))
        self.wfile.flush()

    # ---- 日志 ----

    def log_message(self, fmt: str, *args: Any) -> None:
        # 本地服务只留一行简短日志，不打印 traceback。
        print(f"[{self.log_date_time_string()}] {fmt % args}", file=sys.stderr)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def _load_site() -> dict[str, bytes]:
    css_path = WEB_DIR / "app.css"
    js_path = WEB_DIR / "app.js"
    filter_path = WEB_DIR / "filter.js"
    css = css_path.read_text(encoding="utf-8")
    # 三区页与贴片共用静态页的卡片样式，不另写一套。
    css = css.rstrip() + "\n\n/* ---------- 卡片：来自 theme.CARD_CSS，与静态页共用 ---------- */\n"
    css += theme.CARD_CSS + "\n"
    return {
        "css": css.encode("utf-8"),
        "js": js_path.read_bytes(),
        "filter_js": filter_path.read_bytes(),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    arg_parser = argparse.ArgumentParser(
        description="桌宠日记 P2 本地服务（三区界面 + 贴片 + SSE，仅标准库）。"
    )
    arg_parser.add_argument("--root", required=True, help="库目录（必须含 index.diary）")
    arg_parser.add_argument("--port", type=int, default=8777, help="监听端口（默认 8777）")
    arg_parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认仅本机）")
    return arg_parser


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
        sys.stderr.reconfigure(encoding="utf-8", newline="\n")
    except (AttributeError, OSError):
        pass

    args = build_arg_parser().parse_args(argv)
    root = Path(args.root)

    if not (root / store.INDEX_NAME).exists():
        print(
            f"错误：{root} 里没有 {store.INDEX_NAME}，请先跑 admin.py init",
            file=sys.stderr,
        )
        return 1
    index = store.load_index(root)
    if index is None:
        print(f"错误：{root / store.INDEX_NAME} 不是合法的 JSON", file=sys.stderr)
        return 1

    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(f"警告：正在监听 {args.host}，同网段的其他机器也能访问这个日记库。", file=sys.stderr)

    try:
        site = _load_site()
    except OSError as exc:
        print(f"错误：前端资源读取失败：{exc}", file=sys.stderr)
        return 1

    try:
        server = DiaryServer((args.host, args.port), DiaryHandler)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 10048 or getattr(exc, "errno", None) == 98:
            print(f"错误：端口 {args.port} 已被占用，请换一个 --port", file=sys.stderr)
        else:
            print(f"错误：启动失败：{exc}（试试换一个 --port）", file=sys.stderr)
        return 1

    server.site = site  # type: ignore[attr-defined]
    try:
        server.hub = StateHub(root, args.root)  # type: ignore[attr-defined]
        server.hub.start()  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001  （启动失败给人话，不喷 traceback）
        print(f"错误：读取库失败：{exc}", file=sys.stderr)
        server.server_close()
        return 1

    state = server.hub.get_state()  # type: ignore[attr-defined]
    # flush=True：启动信息要能在 `> log.txt` / 后台运行时立刻看到，否则被块缓冲吞掉。
    print(f"库：{state['library']['name']}（{state['library']['root']}）", flush=True)
    print(f"条目：{state['counts']['total']}", flush=True)
    if int(state["counts"]["total"]) > 500:
        print(
            f"提示：条目已 {state['counts']['total']} 条，日常建议用服务模式，单文件当快照用。",
            flush=True,
        )
    print(f"界面：http://{args.host}:{args.port}/", flush=True)
    print(f"贴片：http://{args.host}:{args.port}/overlay", flush=True)
    print("按 Ctrl+C 停止。", flush=True)

    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        server.hub.stop()  # type: ignore[attr-defined]
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
