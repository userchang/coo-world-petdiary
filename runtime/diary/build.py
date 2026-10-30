#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""静态日记册构建器（P1）。

读取一个目录里的 markdown 日记，调用 parser.py 解析，生成单文件
`index.html`（CSS / JS / 数据全部内联，无外部依赖，file:// 双击可开）。

P0.5 新增：册 / 场次 / 类型三段筛选，时间排序与类型排序两套视图。
P1 新增：`--root <库目录>` 库模式——先做审计链 + 指纹校验，登记新条目，
把「被外部修改」标到卡片上，并写一条 `via=build` 的 read 审计。
老用法 `--src fixtures --out out/site` 保持原样。

用法：
    python diary/build.py --src fixtures --out out/site
    python diary/build.py --root demo-lib --out out/lib_site

只使用 Python 标准库；fixtures 只读，不修改任何输入文件。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# 允许 `python diary/build.py` 和 `python -m diary.build` 两种跑法。
sys.path.insert(0, str(Path(__file__).resolve().parent))
from parser import KINDS, assemble, parse_directory, parse_file  # noqa: E402  （同目录模块，必须在 sys.path 调整后导入）
import store  # noqa: E402
import theme  # noqa: E402

WEB_DIR = Path(__file__).resolve().parent / "web"


def _collect_files(src: Path) -> list[Path]:
    if src.is_file():
        return [src]
    return sorted(
        (p for p in src.iterdir() if p.is_file() and p.suffix.lower() == ".md"),
        key=lambda p: p.name,
    )


def _json_for_script(value: Any) -> str:
    """把 JSON 放进 <script type="application/json">，避免正文里的 </script> 截断页面。"""
    text = json.dumps(value, ensure_ascii=False, indent=2)
    return (
        text.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _default_out_dir() -> Path:
    """缺省落到包里的 `dist/`（相对插件根目录推导）。"""
    return Path(__file__).resolve().parent.parent.parent / "coo-world-petdiary" / "dist"


def _render(payload: dict[str, Any]) -> str:
    entries = payload["entries"]
    total = len(entries)
    public_count = sum(1 for entry in entries if entry.get("shelf") != "private")
    private_count = total - public_count
    book_count = len(payload["books"])
    library = payload.get("library") or {}
    scope = library.get("scope") or ("public" if library.get("mode") == "dual" else "all")

    # 默认视图只显示公开本；私密本的数据仍在页内，点顶部开关才切过去。
    if private_count:
        stats = (
            f"公开本 {public_count} 条 · 私密本 {private_count} 条 · "
            f"当前显示 {public_count} 条"
        )
        shelf_note = f"公开本 {public_count} 条 / 私密本 {private_count} 条"
        foot = (
            "桌宠日记 · 数据源：markdown · 单文件静态页面，无外部依赖 · "
            "公开本与私密本都收录，默认只显示公开本"
        )
    else:
        stats = f"共 {total} 条 · 当前显示 {total} 条"
        shelf_note = f"公开本 {public_count} 条"
        foot = (
            "桌宠日记 · 数据源：markdown · 单文件静态页面，无外部依赖 · 只收录公开本"
            if scope == "public"
            else "桌宠日记 · 数据源：markdown · 单文件静态页面，无外部依赖"
        )
    subtitle = f"静态快照 · {book_count} 本册 / {total} 条记录 · {shelf_note}"
    library_name = payload.get("library_name")
    if library_name:
        subtitle = f"{library_name} · {subtitle}"

    filter_js = (WEB_DIR / "filter.js").read_text(encoding="utf-8")
    html = INDEX_TEMPLATE.replace("@@CSS@@", theme.CSS)
    html = html.replace("@@FILTER_JS@@", filter_js)
    # 先换元信息，最后塞数据：避免正文里恰好出现 "@@STATS@@" 之类被二次替换。
    html = html.replace("@@STATS@@", stats)
    html = html.replace("@@SUBTITLE@@", subtitle)
    html = html.replace("@@FOOT@@", foot)
    html = html.replace("@@DATA@@", _json_for_script(payload))
    return html


def main(argv: list[str] | None = None) -> int:
    arg_parser = argparse.ArgumentParser(
        description="把 markdown 日记目录构建成单文件静态页面（P1，仅标准库）。"
    )
    arg_parser.add_argument("--src", default="fixtures", help="markdown 所在目录（默认 fixtures）")
    arg_parser.add_argument(
        "--out",
        help="输出目录；缺省落到 coo-world-petdiary/dist（仍可显式指定）",
    )
    arg_parser.add_argument(
        "--root",
        help="库目录（含 index.diary）；给了就按库模式做校验、登记指纹并写 build 审计",
    )
    arg_parser.add_argument(
        "--scope",
        choices=["public", "all"],
        default="public",
        help="库模式下取数范围：public=只出公开本（分享页，默认）；all=全库含私密本（本地浏览用）",
    )
    args = arg_parser.parse_args(argv)

    src = Path(args.src)
    out_dir = Path(args.out) if args.out else _default_out_dir()
    library_name: str | None = None
    library_mode = bool(args.root)
    library_meta: dict[str, Any] = {
        "mode": "single",
        "dual_diary": False,
    }

    try:
        if library_mode:
            root = Path(args.root)
            if not root.is_dir():
                print(f"错误：库目录不存在：{root}", file=sys.stderr)
                return 1
            index = store.load_index(root)
            if index is None:
                print(
                    f"错误：{root} 里没有 {store.INDEX_NAME}，请先跑 admin.py init",
                    file=sys.stderr,
                )
                return 1
            library_name = index.get("name")
            library_meta = {
                "mode": store.library_mode(root),
                "dual_diary": store.library_mode(root) == "dual",
                "scope": args.scope,
            }

            # public=分享页只出公开本（private/ 不进解析，硬排除）；
            # all=本地浏览页，全库含私密本。
            check = store.inspect_library(
                root, record=True, register=True, scope=args.scope
            )
            if check["chain_issues"]:
                print(f"库校验：审计链有 {len(check['chain_issues'])} 个问题（详见 admin.py verify）")
            if check["changed"]:
                print(f"库校验：{len(check['changed'])} 条被外部修改，页面会带 ⚠ 标记")
            if check["missing"]:
                print(f"库校验：{len(check['missing'])} 条在 hashes 里有、md 里已消失")

            # 直接在条目字典上打标记，assemble 后前端就能渲染 ⚠。
            for entry in check["changed"]:
                entry["tampered"] = True
            docs = check["docs"]
            src = root
        else:
            if not src.exists():
                print(f"错误：来源不存在：{src}", file=sys.stderr)
                return 1
            if src.is_file():
                docs = [parse_file(src)]
            else:
                docs = parse_directory(src)

        payload = assemble(docs)
        payload["library"] = library_meta
        # 分类枚举与顺序只认 parser.KINDS；页面不再自带第二份枚举。
        payload["kinds"] = list(KINDS)
        for entry in payload["entries"]:
            entry.setdefault("shelf", "public")
            # 落不到新枚举的历史分类统一按「未分类」处理，不重写历史 md。
            if entry.get("kind") not in KINDS:
                entry["kind"] = "未分类"
        entries = payload["entries"]
        private_count = sum(1 for entry in entries if entry.get("shelf") == "private")
        payload["counts"] = {
            "total": len(entries),
            "public": len(entries) - private_count,
            "private": private_count,
        }
        if library_name:
            payload["library_name"] = library_name

        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "index.html"
        with open(out_file, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(_render(payload))

        # 一次构建只记一条 read，避免刷屏；写在页面成功落盘之后。
        if library_mode:
            store.append_audit(
                Path(args.root),
                actor="coo",
                action="read",
                target="*",
                entry=None,
                via="build",
            )
    except OSError as exc:
        print(f"错误：构建失败：{exc}", file=sys.stderr)
        return 1

    total = len(payload["entries"])
    counts = payload.get("counts") or {}
    print(f"已生成：{out_file}")
    print(
        f"来源：{src}（{len(payload['books'])} 本册 / {len(payload['docs'])} 个文件，"
        f"{total} 条；公开本 {counts.get('public', total)} 条、"
        f"私密本 {counts.get('private', 0)} 条）"
    )
    if total > 500:
        print(
            f"提示：条目已 {total} 条，日常建议用服务模式，单文件当快照用。"
        )
    return 0


INDEX_TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<title>桌宠日记 · 静态日记册</title>
<style>
@@CSS@@
</style>
</head>
<body>

<header class="topbar">
  <div class="brand">
    <div class="logo" aria-hidden="true">日</div>
    <div>
      <h1>桌宠日记</h1>
      <p>@@SUBTITLE@@</p>
    </div>
  </div>
  <div class="tools">
    <div class="shelf-switch" id="shelf-switch" role="group" aria-label="日记本切换">
      <button type="button" data-shelf="public" class="active" aria-pressed="true">
        <span class="shelf-name">公开本</span>
        <span class="shelf-count">0 条</span>
      </button>
      <button type="button" data-shelf="private" aria-pressed="false">
        <span class="shelf-name">私密日记本</span>
        <span class="shelf-count">0 条</span>
      </button>
    </div>
    <div class="sort">
      <span class="sort-label">排序</span>
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
    <label class="search">
      <input id="search" type="search" placeholder="搜索标题或正文…" autocomplete="off" spellcheck="false" aria-label="搜索标题或正文">
    </label>
    <span class="switch-hint" id="stats">@@STATS@@</span>
  </div>
</header>

<div class="layout">
  <aside class="sidebar" aria-label="筛选">
    <section class="side-block">
      <h2>场次</h2>
      <nav id="session-list" aria-label="场次列表"></nav>
    </section>
    <section class="side-block">
      <h2>类型</h2>
      <nav id="kind-list" aria-label="类型列表"></nav>
    </section>
    <section class="side-block">
      <h2>标签</h2>
      <div id="tag-cloud" aria-label="标签云"></div>
    </section>
  </aside>

  <main class="timeline">
    <noscript><div class="noscript">这个页面需要 JavaScript 才能筛选和展开正文；请用浏览器直接打开 index.html。</div></noscript>
    <div id="empty" class="empty" hidden>
      <strong id="empty-title">没有符合条件的条目</strong>
      <span id="empty-hint">换个关键词或取消筛选试试。</span>
    </div>
    <div id="time-view"></div>
    <footer class="foot">@@FOOT@@</footer>
  </main>
</div>

<script type="application/json" id="diary-data">@@DATA@@</script>
<script>@@FILTER_JS@@</script>
<script>
(function () {
  "use strict";

  var F = window.DiaryFilter;
  var DATA = JSON.parse(document.getElementById("diary-data").textContent);
  var entries = DATA.entries || [];
  var docs = DATA.docs || [];
  var books = DATA.books || [];
  var KIND_ORDER = F.kindList(DATA);

  function keyOf(book, date, shelf) {
    return String(book || "") + "\u0000" + String(date || "") + "\u0000" + String(shelf || "");
  }

  var docMap = new Map();
  docs.forEach(function (doc) {
    docMap.set(keyOf(doc.book, doc.date, doc.scope || "public"), doc);
  });

  var bookTitles = new Map();
  var bookPos = new Map();
  books.forEach(function (book, index) {
    bookTitles.set(book.book, book.book_title || book.book);
    bookPos.set(book.book, index);
  });
  entries.forEach(function (entry) {
    if (!bookTitles.has(entry.book)) {
      bookTitles.set(entry.book, entry.book_title || entry.book);
    }
  });

  var items = entries.map(function (entry, index) {
    var doc = docMap.get(keyOf(entry.book, entry.date, F.shelfOf(entry))) || {};
    return { entry: entry, index: index, doc: doc };
  });

  var state = {
    shelf: "public",
    order: "desc",
    book: null,
    session: null,
    kinds: new Set(),
    tags: new Set(),
    query: "",
    dateFrom: "",
    dateTo: ""
  };

  var sessionList = document.getElementById("session-list");
  var kindList = document.getElementById("kind-list");
  var tagCloud = document.getElementById("tag-cloud");
  var timeView = document.getElementById("time-view");
  var search = document.getElementById("search");
  var dateFromInput = document.getElementById("date-from");
  var dateToInput = document.getElementById("date-to");

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function shelfItems() {
    return items.filter(function (item) {
      return F.shelfOf(item.entry) === state.shelf;
    });
  }

  function countShelf(shelf) {
    var count = 0;
    items.forEach(function (item) {
      if (F.shelfOf(item.entry) === shelf) count += 1;
    });
    return count;
  }

  /* ---------- 左侧筛选器 ---------- */
  function makeFilterButton(label, count, datasetName, value) {
    var button = el("button", "filter-item");
    button.type = "button";
    button.append(el("span", "filter-label", label));
    button.append(el("span", "count", String(count) + " 条"));
    if (datasetName) button.dataset[datasetName] = value;
    return button;
  }

  function sessionRows() {
    var active = shelfItems();
    var rows = [];
    var index = new Map();
    active.forEach(function (item) {
      var date = F.dateOf(item.entry);
      var skey = keyOf(item.entry.book, date);
      if (!index.has(skey)) {
        var row = {
          key: skey,
          book: item.entry.book,
          date: date,
          count: 0,
          time: item.entry.time || ""
        };
        index.set(skey, row);
        rows.push(row);
      }
      var row = index.get(skey);
      row.count += 1;
      var time = item.entry.time || "";
      if (time && (!row.time || time < row.time)) row.time = time;
    });
    rows.sort(function (a, b) {
      return F.cmpDate(a.date, b.date) || F.cmpTime(a.time, b.time);
    });
    return rows;
  }

  function renderSessionList() {
    var rows = sessionRows();
    sessionList.innerHTML = "";
    if (!rows.length) {
      sessionList.append(el("span", "side-empty", "还没有场次。"));
      return;
    }
    rows.forEach(function (row) {
      var label = (state.book ? "" : (bookTitles.get(row.book) || row.book) + " · ") + row.date;
      var button = makeFilterButton(label, row.count, "session", row.key);
      button.dataset.book = row.book;
      button.dataset.date = row.date;
      sessionList.append(button);
    });
  }

  function renderKindList() {
    var active = shelfItems();
    var counts = new Map();
    active.forEach(function (item) {
      var kind = item.entry.kind || "未分类";
      counts.set(kind, (counts.get(kind) || 0) + 1);
    });
    kindList.innerHTML = "";
    KIND_ORDER.forEach(function (kind) {
      kindList.append(makeFilterButton(kind, counts.get(kind) || 0, "kind", kind));
    });
  }

  function renderTagCloud() {
    var active = shelfItems();
    var counts = new Map();
    active.forEach(function (item) {
      (item.entry.tags || []).forEach(function (tag) {
        counts.set(tag, (counts.get(tag) || 0) + 1);
      });
    });
    tagCloud.innerHTML = "";
    if (!counts.size) {
      tagCloud.append(el("span", "side-empty", "还没有标签。标题里写 #标签，就会出现在这里。"));
      return;
    }
    Array.from(counts.keys())
      .sort(function (a, b) {
        return (counts.get(b) - counts.get(a)) || a.localeCompare(b, "zh");
      })
      .forEach(function (tag) {
        var button = el("button", "tag");
        button.type = "button";
        button.dataset.tag = tag;
        button.title = "筛选 #" + tag;
        button.append(el("span", "tag-name", "#" + tag));
        button.append(el("span", "tag-count", String(counts.get(tag))));
        tagCloud.append(button);
      });
  }

  function renderSidebar() {
    renderSessionList();
    renderKindList();
    renderTagCloud();
  }

  function updateShelfSwitch() {
    document.querySelectorAll("#shelf-switch button[data-shelf]").forEach(function (button) {
      var shelf = button.dataset.shelf === "private" ? "private" : "public";
      var active = shelf === state.shelf;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
      var count = button.querySelector(".shelf-count");
      if (count) count.textContent = countShelf(shelf) + " 条";
    });
  }

  /* ---------- 卡片 ---------- */
  function buildCard(item) {
    var entry = item.entry;
    var card = el("article", "entry");
    card.dataset.id = entry.id;
    card.dataset.shelf = F.shelfOf(entry);
    card.dataset.kind = entry.kind || "未分类";
    card.dataset.book = entry.book;
    card.dataset.date = entry.date || "";
    card._entry = entry;

    var top = el("div", "entry-top");
    var time = el("time", "entry-time", entry.time || "—");
    if (entry.time) {
      time.dateTime = entry.time;
    } else {
      time.classList.add("empty-time");
      time.title = "标题没有写时间";
    }
    top.append(time);

    top.append(el("span", "book-tag", entry.book_title || bookTitles.get(entry.book) || entry.book));

    var kindBadge = el("span", "badge kind", entry.kind || "未分类");
    kindBadge.dataset.kind = entry.kind || "未分类";
    top.append(kindBadge);

    if (entry.speaker) {
      var speaker = el("span", "badge speaker", entry.speaker);
      speaker.dataset.speaker = entry.speaker;
      top.append(speaker);
    }

    if (entry.tampered) {
      var tamper = el("span", "badge tamper", "⚠ 被外部修改");
      tamper.title = "这条的指纹和上次登记的对不上；用 admin.py diff 看原话";
      top.append(tamper);
    }
    card.append(top);

    card.append(el("h3", "entry-heading", entry.title || entry.heading || "（无标题）"));

    if (entry.tags && entry.tags.length) {
      var chips = el("div", "entry-chips");
      entry.tags.forEach(function (tag) {
        var chip = el("button", "tag");
        chip.type = "button";
        chip.dataset.tag = tag;
        chip.title = "筛选 #" + tag;
        chip.append(el("span", "tag-name", "#" + tag));
        chips.append(chip);
      });
      card.append(chips);
    }

    var wrap = el("div", "body-wrap");
    var body = el("div", "body");
    if (entry.body) {
      body.textContent = entry.body;
      if (entry.body.split("\n").length > 6) body.classList.add("clamped");
    } else {
      body.textContent = "（这条没有正文）";
      body.classList.add("muted");
    }
    wrap.append(body);
    card.append(wrap);

    if (body.classList.contains("clamped")) {
      var expand = el("button", "expand", "展开全文 ▾");
      expand.type = "button";
      expand.setAttribute("aria-expanded", "false");
      card.append(expand);
    }
    return card;
  }

  /* ---------- 时间视图（只按时间正序 / 倒序） ---------- */
  function renderTimeline(matched) {
    timeView.innerHTML = "";
    if (!matched.length) return;
    var sorted = F.orderItems(matched, state.order, bookPos);
    var byDate = new Map();
    sorted.forEach(function (item) {
      var date = F.dateOf(item.entry);
      if (!byDate.has(date)) byDate.set(date, []);
      byDate.get(date).push(item);
    });

    byDate.forEach(function (dateItems, dateKey) {
      var section = el("section", "day");
      section.dataset.date = dateKey;

      var head = el("div", "day-head");
      head.append(el("span", "day-date", dateKey));
      head.append(el("span", "day-count", dateItems.length + " 条"));
      section.append(head);

      var bySession = new Map();
      dateItems.forEach(function (item) {
        var skey = keyOf(item.entry.book, F.dateOf(item.entry));
        if (!bySession.has(skey)) bySession.set(skey, []);
        bySession.get(skey).push(item);
      });

      bySession.forEach(function (sessionItems, skey) {
        var entry = sessionItems[0].entry;
        var doc = docMap.get(keyOf(entry.book, F.dateOf(entry), F.shelfOf(entry))) || {};
        var block = el("div", "session-block");
        block.dataset.book = entry.book;
        block.dataset.date = entry.date || "";

        block.append(
          el("div", "session-head", "——《" + (bookTitles.get(entry.book) || entry.book) + "》" + dateKey + " ——")
        );

        if (doc.intro) {
          var intro = el("div", "intro-block");
          intro.append(el("div", "intro-label", "开场"));
          intro.append(el("div", "intro-text", doc.intro));
          block.append(intro);
        }

        var list = el("div", "session-entries");
        sessionItems.forEach(function (item) {
          list.append(buildCard(item));
        });
        block.append(list);
        section.append(block);
      });

      timeView.append(section);
    });
  }

  function matchedItems() {
    return shelfItems().filter(function (item) {
      return F.matches(item.entry, state);
    });
  }

  function updateStats(shown) {
    document.getElementById("stats").textContent =
      "公开本 " + countShelf("public") + " 条 · " +
      "私密本 " + countShelf("private") + " 条 · " +
      "当前显示 " + shown + " 条";
  }

  function updateEmpty(shown) {
    var empty = document.getElementById("empty");
    empty.hidden = shown !== 0;
    if (shown !== 0) return;

    var title = document.getElementById("empty-title");
    var hint = document.getElementById("empty-hint");
    if (!items.length) {
      title.textContent = "还没有日记";
      hint.textContent = "把 YYYY-MM-DD-slug.md 放进来源目录，再重跑 build.py。";
    } else if (!shelfItems().length) {
      title.textContent = state.shelf === "private" ? "私密本还没有条目" : "公开本还没有条目";
      hint.textContent = "用页面顶部的「公开本 / 私密日记本」切换看看另一本。";
    } else if (state.dateFrom || state.dateTo) {
      title.textContent = "这个日期范围没有条目";
      hint.textContent = "清空起始或结束日期，或换一个范围试试。";
    } else if (state.kinds.size) {
      title.textContent = "没有符合条件的条目";
      hint.textContent = "类型多选是 AND 关系：条目必须同时属于选中的全部类型。";
    } else {
      title.textContent = "没有符合条件的条目";
      hint.textContent = "换个关键词或取消筛选试试。";
    }
  }

  function updateActive() {
    var activeSession = state.session ? keyOf(state.session.book, state.session.date) : "";
    sessionList.querySelectorAll(".filter-item").forEach(function (button) {
      button.classList.toggle("active", Boolean(activeSession) && button.dataset.session === activeSession);
    });
    kindList.querySelectorAll(".filter-item").forEach(function (button) {
      button.classList.toggle("active", state.kinds.has(button.dataset.kind));
    });
    tagCloud.querySelectorAll("button[data-tag]").forEach(function (button) {
      button.classList.toggle("active", state.tags.has(button.dataset.tag));
    });
    document.querySelectorAll(".entry-chips button[data-tag]").forEach(function (button) {
      button.classList.toggle("active", state.tags.has(button.dataset.tag));
    });
    document.querySelectorAll("#sort-control button[data-order]").forEach(function (button) {
      var active = button.dataset.order === state.order;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  function applyFilters() {
    var matched = matchedItems();
    renderTimeline(matched);
    updateStats(matched.length);
    updateEmpty(matched.length);
    updateActive();
    requestAnimationFrame(setupExpanders);
  }

  /* ---------- 展开 / 收起 ---------- */
  function setupExpanders() {
    Array.from(document.querySelectorAll("#time-view .entry")).forEach(function (card) {
      if (card.hidden) return;
      var body = card.querySelector(".body");
      if (!body || body.classList.contains("muted")) return;
      if (!body.classList.contains("clamped") && body.scrollHeight <= body.clientHeight + 1) return;
      if (!body.classList.contains("clamped")) {
        body.classList.add("clamped");
      }
      var button = card.querySelector(".expand");
      if (!button) {
        button = el("button", "expand", "展开全文 ▾");
        button.type = "button";
        button.setAttribute("aria-expanded", "false");
        card.append(button);
      }
    });
  }

  function resetFilters() {
    state.book = null;
    state.session = null;
    state.kinds.clear();
    state.tags.clear();
    state.query = "";
    state.dateFrom = "";
    state.dateTo = "";
    if (search) search.value = "";
    if (dateFromInput) dateFromInput.value = "";
    if (dateToInput) dateToInput.value = "";
  }

  function readDateInputs() {
    state.dateFrom = dateFromInput ? dateFromInput.value || "" : "";
    state.dateTo = dateToInput ? dateToInput.value || "" : "";
  }

  /* ---------- 交互 ---------- */
  var searchTimer = null;
  if (search) {
    search.addEventListener("input", function () {
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(function () {
        state.query = F.normalize(search.value.trim());
        applyFilters();
      }, 80);
    });
  }

  if (dateFromInput) {
    dateFromInput.addEventListener("input", function () {
      readDateInputs();
      applyFilters();
    });
  }
  if (dateToInput) {
    dateToInput.addEventListener("input", function () {
      readDateInputs();
      applyFilters();
    });
  }

  document.getElementById("sort-control").addEventListener("click", function (event) {
    var button = event.target.closest("button[data-order]");
    if (!button) return;
    state.order = button.dataset.order === "asc" ? "asc" : "desc";
    applyFilters();
  });

  document.getElementById("shelf-switch").addEventListener("click", function (event) {
    var button = event.target.closest("button[data-shelf]");
    if (!button) return;
    var shelf = button.dataset.shelf === "private" ? "private" : "public";
    if (shelf === state.shelf) return;
    state.shelf = shelf;
    resetFilters();
    renderSidebar();
    updateShelfSwitch();
    applyFilters();
  });

  sessionList.addEventListener("click", function (event) {
    var button = event.target.closest("button[data-session]");
    if (!button) return;
    var next = { book: button.dataset.book, date: button.dataset.date };
    var current = state.session ? keyOf(state.session.book, state.session.date) : "";
    state.session = current === keyOf(next.book, next.date) ? null : next;
    applyFilters();
  });

  kindList.addEventListener("click", function (event) {
    var button = event.target.closest("button[data-kind]");
    if (!button) return;
    var kind = button.dataset.kind;
    if (state.kinds.has(kind)) {
      state.kinds.delete(kind);
    } else {
      state.kinds.add(kind);
    }
    applyFilters();
  });

  document.addEventListener("click", function (event) {
    var button = event.target.closest("button[data-tag]");
    if (!button) return;
    var tag = button.dataset.tag;
    if (state.tags.has(tag)) {
      state.tags.delete(tag);
    } else {
      state.tags.add(tag);
    }
    applyFilters();
  });

  timeView.addEventListener("click", function (event) {
    var button = event.target.closest("button.expand");
    if (button) toggleExpand(button);
  });

  function toggleExpand(button) {
    var card = button.closest(".entry");
    var body = card.querySelector(".body");
    var expanded = body.classList.toggle("expanded");
    body.classList.toggle("clamped", !expanded);
    button.textContent = expanded ? "收起 ▴" : "展开全文 ▾";
    button.setAttribute("aria-expanded", expanded ? "true" : "false");
  }

  renderSidebar();
  updateShelfSwitch();
  applyFilters();
})();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
