/* 桌宠日记 · 浏览器筛选/排序纯函数（静态页与三区页共用）。
 *
 * 这个文件只做数据计算，不碰 DOM，所以两种用法都能跑：
 *   - 浏览器：先于页面逻辑加载，挂到 window.DiaryFilter；
 *   - Node：`require("./filter.js")`，供测试直接验证日期范围 / 正倒序。
 *
 * 注意：这里不写死分类枚举。分类顺序由页面数据里的 `kinds`
 * （build.py 从 parser.KINDS 传入）决定，缺失时才从条目里兜底收集。
 */
(function (root, factory) {
  "use strict";
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.DiaryFilter = factory();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  function normalize(value) {
    return String(value || "").normalize("NFKC").toLowerCase();
  }

  function dateOf(entry) {
    return (entry && entry.date) || "未标注日期";
  }

  function shelfOf(entry) {
    return entry && entry.shelf === "private" ? "private" : "public";
  }

  function cmpDate(a, b) {
    if (a === b) return 0;
    if (a === "未标注日期") return 1;
    if (b === "未标注日期") return -1;
    return a < b ? -1 : 1;
  }

  function cmpTime(a, b) {
    if (a === b) return 0;
    if (!a) return 1;
    if (!b) return -1;
    return a < b ? -1 : 1;
  }

  /* item = { entry, index }；bookPos 可选（Map：册 -> 出现顺序）。 */
  function cmpChrono(a, b, bookPos) {
    var byDate = cmpDate(dateOf(a.entry), dateOf(b.entry));
    if (byDate) return byDate;
    var byTime = cmpTime(a.entry.time, b.entry.time);
    if (byTime) return byTime;
    var posA = bookPos && typeof bookPos.get === "function" ? (bookPos.get(a.entry.book) || 0) : 0;
    var posB = bookPos && typeof bookPos.get === "function" ? (bookPos.get(b.entry.book) || 0) : 0;
    if (posA !== posB) return posA - posB;
    return (a.index || 0) - (b.index || 0);
  }

  /* 任一端留空表示不限制；有任一端时，没有日期的条目不算落在范围内。 */
  function inDateRange(value, from, to) {
    var start = String(from || "");
    var end = String(to || "");
    if (!start && !end) return true;
    var date = String(value || "");
    if (!date || date === "未标注日期") return false;
    if (start && date < start) return false;
    if (end && date > end) return false;
    return true;
  }

  function sizeOf(value) {
    if (!value) return 0;
    if (typeof value.size === "number") return value.size;
    if (Array.isArray(value)) return value.length;
    return 0;
  }

  function eachValue(value, callback) {
    if (!value) return;
    if (typeof value.forEach === "function") {
      value.forEach(function (item) { callback(item); });
      return;
    }
    if (Array.isArray(value)) {
      value.forEach(function (item) { callback(item); });
    }
  }

  /* 当前视图条目是否命中所有筛选条件（类型多选仍是 AND）。 */
  function matches(entry, state) {
    state = state || {};
    if (state.shelf && shelfOf(entry) !== state.shelf) return false;
    if (!inDateRange(entry.date, state.dateFrom, state.dateTo)) return false;
    if (state.book && entry.book !== state.book) return false;
    if (state.session &&
        (entry.book !== state.session.book ||
         (entry.date || "未标注日期") !== state.session.date)) {
      return false;
    }
    if (sizeOf(state.kinds)) {
      var kindOk = true;
      eachValue(state.kinds, function (kind) {
        if ((entry.kind || "未分类") !== kind) kindOk = false;
      });
      if (!kindOk) return false;
    }
    if (sizeOf(state.tags)) {
      var tagOk = true;
      eachValue(state.tags, function (tag) {
        if (!entry.tags || entry.tags.indexOf(tag) === -1) tagOk = false;
      });
      if (!tagOk) return false;
    }
    if (state.query) {
      var haystack = normalize(
        (entry.title || "") + "\n" + (entry.heading || "") + "\n" +
        (entry.book_title || "") + "\n" + (entry.body || "")
      );
      if (haystack.indexOf(state.query) === -1) return false;
    }
    return true;
  }

  /* 只按时间排序：order="desc" 最新在前（默认），"asc" 最早在前。 */
  function orderItems(items, order, bookPos) {
    var sorted = items.slice().sort(function (a, b) {
      return cmpChrono(a, b, bookPos);
    });
    if (order !== "asc") sorted.reverse();
    return sorted;
  }

  /* 分类顺序只从页面数据来；数据没给时才按条目出现顺序兜底。 */
  function kindList(data) {
    data = data || {};
    if (Array.isArray(data.kinds) && data.kinds.length) return data.kinds.slice();
    var names = [];
    (data.entries || []).forEach(function (entry) {
      var kind = entry.kind || "未分类";
      if (names.indexOf(kind) === -1) names.push(kind);
    });
    if (names.indexOf("未分类") === -1) names.push("未分类");
    return names;
  }

  return {
    normalize: normalize,
    dateOf: dateOf,
    shelfOf: shelfOf,
    cmpDate: cmpDate,
    cmpTime: cmpTime,
    cmpChrono: cmpChrono,
    inDateRange: inDateRange,
    matches: matches,
    orderItems: orderItems,
    kindList: kindList
  };
});
