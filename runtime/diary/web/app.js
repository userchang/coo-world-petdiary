/* 桌宠日记 P2 前端：三区界面 + 竖条贴片。
 * 只用浏览器原生 API；数据来自页面内嵌 JSON、/api/state 和 /api/events(SSE)。
 */
(function () {
  "use strict";

  var F = window.DiaryFilter || null;

  function $(selector, root) {
    return (root || document).querySelector(selector);
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function normalize(value) {
    return F ? F.normalize(value) : String(value || "").normalize("NFKC").toLowerCase();
  }

  function keyOf(book, date, shelf) {
    return String(book || "") + "\u0000" + String(date || "") + "\u0000" + String(shelf || "");
  }

  function esc(value) {
    return String(value === undefined || value === null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function shortTime(value) {
    var text = String(value || "");
    if (text.indexOf("T") >= 0 && text.length >= 19) return text.slice(11, 19);
    return text || "—";
  }

  function parseEmbedded(id) {
    var node = document.getElementById(id);
    if (!node) return {};
    try {
      return JSON.parse(node.textContent || "{}");
    } catch (error) {
      return {};
    }
  }

  /* ======================================================================
   * 三区界面
   * ==================================================================== */

  function initApp() {
    var DATA = parseEmbedded("diary-data");
    var D = derive(DATA);
    var allCards = [];
    var searchTimer = null;
    var fetchTimer = null;
    var source = null;
    var ui = {
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

    function dateOf(item) {
      return item.entry.date || "未标注日期";
    }

    function cmpDate(a, b) {
      return F.cmpDate(a, b);
    }

    function cmpTime(a, b) {
      return F.cmpTime(a, b);
    }

    function cmpChrono(a, b) {
      return F.cmpChrono(a, b, D.bookPos);
    }

    function derive(data) {
      var entries = data.entries || [];
      var books = data.books || [];
      var docs = data.docs || [];
      var bookTitles = new Map();
      var bookPos = new Map();
      var docMap = new Map();
      var bookCounts = new Map();
      var kindCounts = new Map();
      var sessions = [];
      var sessionMap = new Map();

      books.forEach(function (book, index) {
        bookTitles.set(book.book, book.book_title || book.book);
        bookPos.set(book.book, index);
      });
      entries.forEach(function (entry) {
        if (!bookTitles.has(entry.book)) {
          bookTitles.set(entry.book, entry.book_title || entry.book);
        }
      });
      docs.forEach(function (doc) {
        docMap.set(
          keyOf(doc.book, doc.date || "未标注日期", doc.scope || "public"),
          doc
        );
      });

      var items = entries.map(function (entry, index) {
        return { entry: entry, index: index };
      });

      items.forEach(function (item) {
        var entry = item.entry;
        var kind = entry.kind || "未分类";
        var shelf = F.shelfOf(entry);
        bookCounts.set(entry.book, (bookCounts.get(entry.book) || 0) + 1);
        kindCounts.set(kind, (kindCounts.get(kind) || 0) + 1);
        var sessionDate = entry.date || "未标注日期";
        var skey = keyOf(entry.book, sessionDate, shelf);
        if (!sessionMap.has(skey)) {
          var row = {
            key: skey,
            book: entry.book,
            date: sessionDate,
            shelf: shelf,
            count: 0,
            index: sessions.length
          };
          sessionMap.set(skey, row);
          sessions.push(row);
        }
        sessionMap.get(skey).count += 1;
      });

      var sortedSessions = sessions.slice().sort(function (a, b) {
        return cmpDate(a.date, b.date)
          || ((bookPos.get(a.book) || 0) - (bookPos.get(b.book) || 0));
      });
      sortedSessions.forEach(function (row, index) {
        row.order = index;
      });

      return {
        entries: entries,
        items: items,
        books: books,
        docs: docs,
        bookTitles: bookTitles,
        bookPos: bookPos,
        docMap: docMap,
        bookCounts: bookCounts,
        kindCounts: kindCounts,
        sessions: sessions,
        sortedSessions: sortedSessions,
        sessionMap: sessionMap
      };
    }

    function makeFilterButton(label, count, dataset) {
      var button = el("button", "filter-item");
      button.type = "button";
      button.append(el("span", "filter-label", label));
      button.append(el("span", "count", String(count) + " 条"));
      Object.keys(dataset || {}).forEach(function (key) {
        button.dataset[key] = dataset[key];
      });
      return button;
    }

    function kindOrder() {
      return F.kindList(DATA);
    }

    function shelfItems() {
      return D.items.filter(function (item) {
        return F.shelfOf(item.entry) === ui.shelf;
      });
    }

    function countShelf(shelf) {
      var count = 0;
      D.items.forEach(function (item) {
        if (F.shelfOf(item.entry) === shelf) count += 1;
      });
      return count;
    }

    function renderSidebar() {
      var kindList = $("#kind-list");
      if (!kindList) return;

      var active = shelfItems();

      var kindCounts = new Map();
      active.forEach(function (item) {
        var kind = item.entry.kind || "未分类";
        kindCounts.set(kind, (kindCounts.get(kind) || 0) + 1);
      });
      var kindNodes = kindOrder().map(function (kind) {
        return makeFilterButton(kind, kindCounts.get(kind) || 0, { kind: kind });
      });
      kindList.replaceChildren.apply(kindList, kindNodes);

      renderSessionList();
      updateActive();
    }

    function renderSessionList() {
      var sessionList = $("#session-list");
      if (!sessionList) return;
      var shown = D.sortedSessions.filter(function (row) {
        if (row.shelf && row.shelf !== ui.shelf) return false;
        return !ui.book || row.book === ui.book;
      });
      if (!shown.length) {
        sessionList.replaceChildren(el("span", "side-empty", "还没有场次。"));
        return;
      }
      var nodes = shown.map(function (row) {
        var label = (ui.book ? "" : (D.bookTitles.get(row.book) || row.book) + " · ") + row.date;
        return makeFilterButton(label, row.count, {
          book: row.book,
          date: row.date,
          session: row.key
        });
      });
      sessionList.replaceChildren.apply(sessionList, nodes);
    }

    function buildCard(entry) {
      var card = el("article", "entry");
      card.dataset.id = entry.id;
      card.dataset.shelf = F.shelfOf(entry);
      card.dataset.kind = entry.kind || "未分类";
      card.dataset.book = entry.book;
      card.dataset.date = entry.date || "";
      card._entry = entry;

      var list = el("div", "entry-top");
      var time = el("time", "entry-time", entry.time || "—");
      if (entry.time) {
        time.dateTime = entry.time;
      } else {
        time.classList.add("empty-time");
        time.title = "标题没有写时间";
      }
      list.append(time);
      list.append(el("span", "book-tag", entry.book_title || D.bookTitles.get(entry.book) || entry.book));

      var kind = entry.kind || "未分类";
      var kindBadge = el("span", "badge kind", kind);
      kindBadge.dataset.kind = kind;
      list.append(kindBadge);

      if (entry.speaker) {
        var speaker = el("span", "badge speaker", entry.speaker);
        speaker.dataset.speaker = entry.speaker;
        list.append(speaker);
      }

      if (entry.tampered) {
        var tamper = el("span", "badge tamper", "⚠ 被外部修改");
        tamper.title = "这条的指纹和上次登记的对不上；用 admin.py diff 看原话";
        list.append(tamper);
      }

      card.append(list);
      card.append(el("h3", "entry-heading", entry.title || entry.heading || "（无标题）"));

      if (entry.tags && entry.tags.length) {
        var chips = el("div", "entry-chips");
        entry.tags.forEach(function (tag) {
          var chip = el("span", "tag");
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

    function buildTimeView(list) {
      var fragment = document.createDocumentFragment();
      var byDate = new Map();
      list.forEach(function (item) {
        var key = dateOf(item);
        if (!byDate.has(key)) byDate.set(key, []);
        byDate.get(key).push(item);
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
          var sessionDate = item.entry.date || "未标注日期";
          var skey = keyOf(item.entry.book, sessionDate, F.shelfOf(item.entry));
          if (!bySession.has(skey)) bySession.set(skey, []);
          bySession.get(skey).push(item);
        });

        bySession.forEach(function (sessionItems, skey) {
          var entry = sessionItems[0].entry;
          var doc = D.docMap.get(skey) || {};
          var block = el("div", "session-block");
          block.dataset.book = entry.book;
          block.dataset.date = entry.date || "";

          block.append(
            el("div", "session-head", "——《" + (D.bookTitles.get(entry.book) || entry.book) + "》" + dateKey + " ——")
          );

          if (doc.intro) {
            var intro = el("div", "intro-block");
            intro.append(el("div", "intro-label", "开场"));
            intro.append(el("div", "intro-text", doc.intro));
            block.append(intro);
          }

          var listNode = el("div", "session-entries");
          sessionItems.forEach(function (item) {
            listNode.append(buildCard(item.entry));
          });
          block.append(listNode);
          section.append(block);
        });
        fragment.append(section);
      });
      return fragment;
    }

    function renderViews() {
      var timeView = $("#time-view");
      if (!timeView) return;
      var ordered = F.orderItems(shelfItems(), ui.order, D.bookPos);
      timeView.replaceChildren(buildTimeView(ordered));
      allCards = Array.from(document.querySelectorAll("#time-view .entry"));
    }

    function renderStatus() {
      var status = $("#status");
      if (!status) return;
      var counts = DATA.counts || {};
      var progress = DATA.progress || {};
      var library = DATA.library || {};
      var audit = DATA.audit || {};
      var latestBook = progress.latest_book || "";
      var latestTitle = latestBook ? (D.bookTitles.get(latestBook) || latestBook) : "—";

      var cast = (DATA.cast || []).slice(0, 3).map(function (person) {
        return '<div class="cast-card"><div class="cast-top">' +
          '<span class="cast-name">' + esc(person.name) + "</span>" +
          '<span class="cast-status">' + esc(person.status) + "</span></div>" +
          '<div class="cast-note">' + esc(person.note || "（没有简介）") + "</div></div>";
      }).join("") || '<span class="side-empty">还没有 cast/。</span>';

      var unresolved = (DATA.threads || []).filter(function (thread) {
        return thread.status === "未解";
      });
      var threads = unresolved.slice(0, 5).map(function (thread) {
        return '<div class="thread-card"><div class="thread-title">' + esc(thread.title) + "</div>" +
          '<div class="thread-note">' + esc(thread.note || "（没有补充）") + "</div></div>";
      }).join("") || '<span class="side-empty">暂无未解伏笔。</span>';

      var chainOk = audit.chain_ok !== false;
      var chainHtml = chainOk
        ? ""
        : '<div class="audit-warn">⚠ 审计链异常（' + ((audit.issues || []).length) + " 处）</div>";

      var recentRows = (audit.recent || []).map(function (item) {
        return '<div class="audit-row' + (item.external ? " external" : "") + '">' +
          '<span class="audit-time">' + esc(shortTime(item.t)) + "</span>" +
          '<span class="audit-actor">' + esc(item.actor || "unknown") + "</span>" +
          '<span class="audit-action">' + esc(item.action || "?") + "</span>" +
          '<span class="audit-target">' + esc(item.entry || item.target || "—") + "</span>" +
          "</div>";
      }).join("") || '<span class="side-empty">还没有审计记录。</span>';

      var external = audit.external || {};
      var externalCount = Number(external.count || 0);
      var externalEntries = external.entries || [];
      var externalHtml = externalCount
        ? '<div class="kv"><span>次数</span><b>' + externalCount + " 次</b></div>" +
          '<div class="kv"><span>涉及条目</span><b>' + esc(externalEntries.slice(0, 3).join("、")) +
          (externalEntries.length > 3 ? " 等" : "") + "</b></div>" +
          '<div class="kv"><span>最近</span><b>' + esc(shortTime(external.latest)) + "</b></div>"
        : '<span class="side-empty">还没有外部改动记录。</span>';

      var privacyHtml;
      if (library.mode !== "dual") {
        privacyHtml =
          '<p class="side-hint">当前是单本模式。切到双日记后，公开本与私密本会分开存放、一起读取。</p>';
      } else {
        privacyHtml =
          '<div class="kv"><span>公开本</span><b>' + Number(counts.shelf_public || 0) + " 条</b></div>" +
          '<div class="kv"><span>私密本</span><b>' + Number(counts.private || 0) + " 条</b></div>" +
          '<p class="side-hint">私密是分类，不是锁：页面、Coo 工具、serve 与导出都能正常读写私密本。</p>';
      }

      status.innerHTML =
        '<section class="status-block"><h2>进度</h2>' +
        '<div class="kv"><span>库</span><b>' + esc(library.name || "—") + "</b></div>" +
        '<div class="kv"><span>最新</span><b>' + esc(progress.latest_date || "—") + " · " + esc(latestTitle) + "</b></div>" +
        '<div class="kv"><span>当日</span><b>' + Number(progress.today_entries || 0) + " 条</b></div>" +
        '<div class="kv"><span>最后写入</span><b>' + esc(progress.last_write || "—") + "</b></div></section>" +
        '<section class="status-block"><h2>人物</h2>' + cast + "</section>" +
        '<section class="status-block"><h2>未解伏笔</h2>' + threads + "</section>" +
        '<section class="status-block"><h2>审计</h2><div class="audit-line">读过 ' +
        Number(audit.read || 0) +
        " · 外部改动 " + Number(counts.changed || 0) + " · 构建 " + Number(audit.build || 0) +
        "</div>" + chainHtml + "</section>" +
        '<section class="status-block"><h2>最近动作</h2>' + recentRows + "</section>" +
        '<section class="status-block"><h2>谁动过我日记</h2>' + externalHtml + "</section>" +
        '<section class="status-block"><h2>隐私</h2>' + privacyHtml + "</section>";
    }

    function updateWarning() {
      var warning = $("#changed-warning");
      if (!warning) return;
      var changed = Number((DATA.counts || {}).changed || 0);
      warning.hidden = changed === 0;
      warning.textContent = changed ? "⚠ " + changed + " 条被外部修改" : "";
    }

    function updateStats() {
      var stats = $("#stats");
      if (!stats) return;
      var shown = shelfItems().filter(function (item) {
        return entryMatches(item.entry);
      }).length;
      stats.textContent =
        "公开本 " + countShelf("public") + " 条 · " +
        "私密本 " + countShelf("private") + " 条 · " +
        "当前显示 " + shown + " 条";
    }

    function entryMatches(entry) {
      return F.matches(entry, ui);
    }

    function updateShelfSwitch() {
      document.querySelectorAll("#shelf-switch button[data-shelf]").forEach(function (button) {
        var shelf = button.dataset.shelf === "private" ? "private" : "public";
        var active = shelf === ui.shelf;
        button.classList.toggle("active", active);
        button.setAttribute("aria-pressed", active ? "true" : "false");
        var count = button.querySelector(".shelf-count");
        if (count) count.textContent = countShelf(shelf) + " 条";
      });
    }

    function updateActive() {
      var sessionList = $("#session-list");
      var kindList = $("#kind-list");
      if (sessionList) {
        var activeSession = ui.session
          ? keyOf(ui.session.book, ui.session.date, ui.shelf)
          : "";
        sessionList.querySelectorAll(".filter-item").forEach(function (button) {
          button.classList.toggle(
            "active",
            Boolean(activeSession) && button.dataset.session === activeSession
          );
        });
      }
      if (kindList) {
        kindList.querySelectorAll(".filter-item").forEach(function (button) {
          button.classList.toggle("active", ui.kinds.has(button.dataset.kind));
        });
      }
      updateShelfSwitch();
      document.querySelectorAll("#sort-control button[data-order]").forEach(function (button) {
        var active = button.dataset.order === ui.order;
        button.classList.toggle("active", active);
        button.setAttribute("aria-pressed", active ? "true" : "false");
      });
    }

    function resetFilters() {
      ui.book = null;
      ui.session = null;
      ui.kinds.clear();
      ui.tags.clear();
      ui.query = "";
      ui.dateFrom = "";
      ui.dateTo = "";
      var search = $("#search");
      if (search) search.value = "";
      var from = $("#date-from");
      var to = $("#date-to");
      if (from) from.value = "";
      if (to) to.value = "";
    }

    function readDateInputs() {
      var from = $("#date-from");
      var to = $("#date-to");
      ui.dateFrom = from ? from.value || "" : "";
      ui.dateTo = to ? to.value || "" : "";
    }

    function applyFilters() {
      allCards.forEach(function (card) {
        card.hidden = !entryMatches(card._entry);
      });

      document.querySelectorAll("#time-view .session-block").forEach(function (block) {
        var cards = Array.from(block.querySelectorAll(".entry"));
        var visible = cards.filter(function (card) { return !card.hidden; }).length;
        block.hidden = visible === 0;
      });

      document.querySelectorAll("#time-view .day").forEach(function (section) {
        var cards = Array.from(section.querySelectorAll(".entry"));
        var visible = cards.filter(function (card) { return !card.hidden; }).length;
        var count = section.querySelector(".day-count");
        if (count) {
          count.textContent = visible === cards.length
            ? cards.length + " 条"
            : visible + " / " + cards.length + " 条";
        }
        section.hidden = visible === 0;
      });

      var shown = shelfItems().filter(function (item) {
        return entryMatches(item.entry);
      }).length;
      var empty = $("#empty");
      empty.hidden = shown !== 0;
      if (shown === 0) {
        var title = $("#empty-title");
        var hint = $("#empty-hint");
        if (!D.items.length) {
          title.textContent = "还没有日记";
          hint.textContent = "把 YYYY-MM-DD-slug.md 放进库目录，再刷新。";
        } else if (!shelfItems().length) {
          title.textContent = ui.shelf === "private" ? "私密本还没有条目" : "公开本还没有条目";
          hint.textContent = "用页面顶部的「公开本 / 私密日记本」切换看看另一本。";
        } else if (ui.dateFrom || ui.dateTo) {
          title.textContent = "这个日期范围没有条目";
          hint.textContent = "清空起始或结束日期，或换一个范围试试。";
        } else if (ui.kinds.size) {
          title.textContent = "没有符合条件的条目";
          hint.textContent = "类型多选是 AND 关系：条目必须同时属于选中的全部类型。";
        } else {
          title.textContent = "没有符合条件的条目";
          hint.textContent = "换个关键词或取消筛选试试。";
        }
      }
      updateStats();
      updateActive();
    }

    function setData(next) {
      DATA = next || {};
      D = derive(DATA);
      if (ui.shelf !== "private") ui.shelf = "public";
      if (ui.book && !D.bookTitles.has(ui.book)) ui.book = null;
      if (ui.session && !D.sessionMap.has(keyOf(ui.session.book, ui.session.date, ui.shelf))) {
        ui.session = null;
      }
      if (ui.session && ui.book && ui.session.book !== ui.book) ui.session = null;
      renderSidebar();
      renderViews();
      renderStatus();
      updateWarning();
      applyFilters();
    }

    function toggleExpand(button) {
      var card = button.closest(".entry");
      var body = card.querySelector(".body");
      var expanded = body.classList.toggle("expanded");
      body.classList.toggle("clamped", !expanded);
      button.textContent = expanded ? "收起 ▴" : "展开全文 ▾";
      button.setAttribute("aria-expanded", expanded ? "true" : "false");
    }

    document.addEventListener("click", function (event) {
      var shelfButton = event.target.closest("#shelf-switch button[data-shelf]");
      if (shelfButton) {
        var shelf = shelfButton.dataset.shelf === "private" ? "private" : "public";
        if (shelf !== ui.shelf) {
          ui.shelf = shelf;
          resetFilters();
          renderSidebar();
          renderViews();
          applyFilters();
        }
        return;
      }

      var sessionButton = event.target.closest("#session-list button[data-book]");
      if (sessionButton) {
        var next = { book: sessionButton.dataset.book, date: sessionButton.dataset.date };
        var activeKey = keyOf(next.book, next.date, ui.shelf);
        if (ui.session && keyOf(ui.session.book, ui.session.date, ui.shelf) === activeKey) {
          ui.session = null;
        } else {
          ui.session = next;
        }
        applyFilters();
        return;
      }

      var kindButton = event.target.closest("#kind-list button[data-kind]");
      if (kindButton) {
        var kind = kindButton.dataset.kind;
        if (ui.kinds.has(kind)) ui.kinds.delete(kind);
        else ui.kinds.add(kind);
        applyFilters();
        return;
      }

      var sortButton = event.target.closest("#sort-control button[data-order]");
      if (sortButton) {
        ui.order = sortButton.dataset.order === "asc" ? "asc" : "desc";
        renderViews();
        applyFilters();
        return;
      }

      var expandButton = event.target.closest(".entry button.expand");
      if (expandButton) {
        toggleExpand(expandButton);
        return;
      }
    });

    var search = $("#search");
    if (search) {
      search.addEventListener("input", function () {
        window.clearTimeout(searchTimer);
        searchTimer = window.setTimeout(function () {
          ui.query = normalize(search.value.trim());
          applyFilters();
        }, 80);
      });
    }

    var dateFromInput = $("#date-from");
    if (dateFromInput) {
      dateFromInput.addEventListener("input", function () {
        readDateInputs();
        applyFilters();
      });
    }
    var dateToInput = $("#date-to");
    if (dateToInput) {
      dateToInput.addEventListener("input", function () {
        readDateInputs();
        applyFilters();
      });
    }

    function fetchState() {
      window.clearTimeout(fetchTimer);
      fetchTimer = window.setTimeout(function () {
        fetch("/api/state", { cache: "no-store" }).then(function (response) {
          if (!response.ok) return null;
          return response.json();
        }).then(function (value) {
          if (value) setData(value);
        }).catch(function () { /* SSE 会自动重连，这里静默 */ });
      }, 40);
    }

    function startEvents() {
      if (!window.EventSource) {
        window.setInterval(fetchState, 1000);
        return;
      }
      source = new EventSource("/api/events");
      source.addEventListener("state", function (event) {
        try {
          setData(JSON.parse(event.data));
        } catch (error) { /* 坏帧忽略，等下一帧 */ }
      });
      source.onopen = fetchState;
      source.onerror = fetchState;
    }

    setData(DATA);
    fetchState();
    startEvents();
  }

  /* ======================================================================
   * 右侧竖条贴片
   * ==================================================================== */

  function initOverlay() {
    var boot = parseEmbedded("overlay-data");
    var fetchTimer = null;

    function publicEntries(data) {
      return (data.entries || [])
        .filter(function (entry) {
          return (entry.shelf || "public") !== "private";
        })
        .slice(-3);
    }

    function twoLines(body) {
      if (!body) return "（没有正文）";
      return body.split("\n").slice(0, 2).join("\n");
    }

    function buildOverlayEntry(entry) {
      var node = el("article", "ov-entry");
      node.dataset.id = entry.id;
      node.append(el("div", "ov-meta"));
      var meta = node.firstChild;
      meta.append(el("span", "ov-time", entry.time || "—"));
      meta.append(el("span", "ov-book", entry.book_title || entry.book || ""));
      node.append(el("h3", "ov-title", entry.title || entry.heading || "（无标题）"));
      node.append(el("p", "ov-body", twoLines(entry.body)));
      return node;
    }

    function updateOverlayEntry(node, entry) {
      var time = node.querySelector(".ov-time");
      var book = node.querySelector(".ov-book");
      var title = node.querySelector(".ov-title");
      var body = node.querySelector(".ov-body");
      if (time) time.textContent = entry.time || "—";
      if (book) book.textContent = entry.book_title || entry.book || "";
      if (title) title.textContent = entry.title || entry.heading || "（无标题）";
      if (body) body.textContent = twoLines(entry.body);
    }

    function renderEntries(data, animate) {
      var container = $("#ov-entries");
      if (!container) return;
      var entries = publicEntries(data);
      if (!entries.length) {
        container.replaceChildren(el("div", "ov-empty", "暂无公开记录"));
        return;
      }
      var existing = new Map();
      Array.from(container.querySelectorAll(".ov-entry")).forEach(function (node) {
        existing.set(node.dataset.id, node);
      });
      var fragment = document.createDocumentFragment();
      entries.forEach(function (entry) {
        var node = existing.get(entry.id);
        if (node) {
          existing.delete(entry.id);
          updateOverlayEntry(node, entry);
        } else {
          node = buildOverlayEntry(entry);
          if (animate) {
            node.classList.add("is-new");
            window.requestAnimationFrame(function () {
              window.requestAnimationFrame(function () {
                node.classList.remove("is-new");
              });
            });
          }
        }
        fragment.append(node);
      });
      existing.forEach(function (node) { node.remove(); });
      container.replaceChildren(fragment);
    }

    function renderCast(data) {
      var section = $("#ov-cast-section");
      if (!section) return;
      var people = (data.cast || []).slice(0, 3);
      var nodes = people.map(function (person) {
        var card = el("div", "ov-cast-card");
        var name = el("span", "ov-cast-name", person.name || "");
        var status = el("span", "ov-cast-status", person.status || "");
        card.append(name, status);
        card.append(el("div", "ov-cast-note", person.note || ""));
        return card;
      });
      section.replaceChildren.apply(section, nodes);
    }

    function renderThreads(data) {
      var container = $("#ov-threads");
      if (!container) return;
      var unresolved = (data.threads || []).filter(function (thread) {
        return thread.status === "未解";
      });
      if (!unresolved.length) {
        container.replaceChildren(el("div", "ov-threads-empty", "暂无未解伏笔"));
        return;
      }
      var nodes = [el("div", "ov-threads-head", "未解伏笔 ×" + unresolved.length)];
      unresolved.slice(0, 3).forEach(function (thread) {
        var row = el("div", "ov-thread");
        row.append(el("span", "ov-thread-title", thread.title || ""));
        row.append(el("span", "ov-thread-note", thread.note || ""));
        nodes.push(row);
      });
      if (unresolved.length > 3) {
        nodes.push(el("div", "ov-thread-more", "+" + (unresolved.length - 3)));
      }
      container.replaceChildren.apply(container, nodes);
    }

    function renderOverlay(data, animate) {
      renderEntries(data, animate);
      renderCast(data);
      renderThreads(data);
    }

    function fetchOverlay() {
      window.clearTimeout(fetchTimer);
      fetchTimer = window.setTimeout(function () {
        fetch("/api/state", { cache: "no-store" }).then(function (response) {
          if (!response.ok) return null;
          return response.json();
        }).then(function (value) {
          if (value) renderOverlay(value, true);
        }).catch(function () { /* 等 SSE 重连 */ });
      }, 40);
    }

    renderOverlay(boot, false);
    if (!window.EventSource) {
      window.setInterval(fetchOverlay, 1000);
      return;
    }
    var source = new EventSource("/api/events");
    source.addEventListener("state", function (event) {
      try {
        renderOverlay(JSON.parse(event.data), true);
      } catch (error) { /* 坏帧忽略 */ }
    });
    source.onopen = fetchOverlay;
    source.onerror = fetchOverlay;
  }

  if (document.body.dataset.page === "overlay") {
    initOverlay();
  } else {
    initApp();
  }
})();
