#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""日记 markdown 解析器（P1）。

把 Coo 随手写的 markdown 日记解析成结构化条目。设计原则是「宽容」：
格式不规范也要出条目、给 warning，绝不因为标题没时间/没标签就报错或丢条目。

P0.5 在 P0 的字段上新增（旧字段不改名）：
    - 册：book / book_title（文件名里的 slug，显示名查 diary/books.json）
    - 事件类型：kind（标签优先，其次标题关键词，兜底「未分类」）
    - 说话人：speaker（从标题里的称呼识别；分类枚举不再有专门类型）
    - 纯标题：title（去掉时间前缀、标签段和行内 markdown）
    - 开场白：intro（第一个 ## 之前的内容）

P1 新增 / 修正：
    - parse_text / parse_file / parse_directory 支持 books_override，
      库模式下用 index.diary 的 books 覆盖 diary/books.json。

P5.2：删除旧版可见性层。条目不再有 visibility 字段；标题里历史遗留的
可见性标记按普通文本保留，不报错、不做特殊解释。

用法：
    python diary/parser.py <md文件> [--json]
    python diary/parser.py --dir fixtures [--json]

只使用 Python 标准库；不修改输入文件。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 正则：都按「标题行」工作，正文不参与时间/标签的判断
# ---------------------------------------------------------------------------

# 一级标题（文档标题）。允许 "#标题" 这种没空格的写法（真实笔记里偶尔会漏空格）。
H1_RE = re.compile(r"^#(?!#)\s*(.*)$")

# 条目标题：## 或 ###，后面必须有空白或直接接内容（兼容 "##标题"）。
H2H3_RE = re.compile(r"^(#{2,3})(?!#)\s*(.*)$")

# 标题开头的 HH:MM / H:MM。后面不能紧跟数字或冒号，避免把 23:29:30 截成 23:29。
TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})(?![\d:])")

# 标题行里的 #标签。先粗抓，再剥掉紧跟在后面的中文/英文标点。
TAG_RE = re.compile(r"#([^\s#|]+)")
TAG_TRAILING = "，,。.；;：:、!！?？)）]】」』”\"'"
# 清洗纯标题时用：连同标签后面的标点一起吞掉，避免留下孤零零的逗号。
TAG_STRIP_RE = re.compile(r"#[^\s#|]+[" + re.escape(TAG_TRAILING) + r"]*")

# 从文件名开头提取日期。
DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")

# 代码围栏：围栏里的 "##" 不是标题，避免把代码块内容切成条目。
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")

# ---------------------------------------------------------------------------
# P0.5 新增：册 / 事件类型 / 说话人
# ---------------------------------------------------------------------------

# 固定枚举，顺序即页面「类型视图」的展示顺序。
KINDS = ["日常", "心情", "想法", "计划", "健康", "游戏", "交际", "未分类"]
KIND_TAG_VALUES = set(KINDS[:-1])

# 关键词同时命中多个类型时的消歧顺序。这里不是展示顺序，而是「语义更具体者优先」：
# 例如「今天好累，心情很烦」同时命中「心情」和「日常」，心情更具体，排在前面。
# 展示顺序仍以 KINDS 为准。
KIND_TIE_ORDER = ["游戏", "心情", "健康", "交际", "计划", "想法", "日常"]

# kinds.json 缺失或损坏时的兜底关键词表（与交付的 kinds.json 保持一致）。
DEFAULT_KINDS: dict[str, list[str]] = {
    "日常": ["日常", "今天", "天气", "出门", "回家", "收拾", "整理", "待机", "买菜", "做饭", "散步"],
    "心情": ["心情", "开心", "难过", "委屈", "烦", "焦虑", "生气", "感动", "喜欢", "想念", "孤独", "害怕", "紧张", "期待", "触动", "情绪"],
    "想法": ["想法", "思考", "发现", "明白", "理解", "为什么", "感悟", "意识到", "反思", "结论", "推测", "判断"],
    "计划": ["计划", "待办", "打算", "安排", "目标", "下次", "备忘", "清单", "想去做"],
    "健康": ["健康", "睡觉", "失眠", "累", "困", "生病", "头疼", "感冒", "熬夜", "运动", "锻炼", "休息", "精神"],
    "游戏": ["游戏", "通关", "关卡", "存档", "读档", "开荒", "副本", "打怪", "NPC", "联机", "手感", "像素", "开黑", "赢", "输", "卡关", "攻略"],
    "交际": ["聊天", "朋友", "家人", "见面", "约会", "通话", "聚会", "主人", "回复", "商量"],
}

# 标题开头的「时间 / 时间区间」前缀，例如 "23:29 "、"23:33–23:35 "。
# 只在清洗后的 title 里去掉；heading 仍保留原始整行。
TIME_RANGE_PREFIX_RE = re.compile(
    r"^\s*\d{1,2}:\d{2}(?![\d:])(?:\s*[–—\-~～至]\s*\d{1,2}:\d{2}(?![\d:]))?\s*"
)

# 标题里的 "| #标签" 分段。只丢「含标签」的段，普通竖线分隔
#（例如标题本身带 |）尽量保留。
PIPE_SPLIT_RE = re.compile(r"\s*[|｜]\s*")
INLINE_MARKDOWN_RE = re.compile(r"`+|\*\*|__|~~|\*")

# 配置文件和代码放在一起，跟着 diary/ 目录走，不依赖当前工作目录。
CONFIG_DIR = Path(__file__).resolve().parent

# Coo 的名字只按独立单词匹配，避免把 Coopanion 之类的工具名误认成说话人。
COO_RE = re.compile(r"(?i)(?<![A-Za-z])coo(?![A-Za-z])")


def _read_text(path: Path) -> str:
    """读取文本：优先 UTF-8（含 BOM），失败再试 GB18030，最后替换坏字节。

    真实笔记是 UTF-8；这里只是保证「编码不对也不崩」。
    """
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _clean_tags(heading: str) -> list[str]:
    """取出标题里的所有 #标签，按出现顺序去重。"""
    tags: list[str] = []
    for match in TAG_RE.finditer(heading):
        tag = match.group(1).rstrip(TAG_TRAILING).strip()
        if tag and tag not in tags:
            tags.append(tag)
    return tags


def _extract_time(heading: str) -> str | None:
    """只从标题行开头取时间；取不到就是 None，绝不从正文猜。"""
    match = TIME_RE.match(heading)
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    # 统一成两位小时，页面显示更整齐（9:05 -> 09:05）。
    return f"{hour:02d}:{minute:02d}"


def _extract_date(path: Path) -> str | None:
    match = DATE_RE.match(path.name)
    if not match:
        return None
    return "-".join(match.groups())


def _load_config(name: str, fallback: dict[str, Any]) -> dict[str, Any]:
    """读取 diary/ 下的人工可编辑 JSON；缺失或格式坏掉时静默用兜底。

    配置只是「锦上添花」，不能因为用户手滑少个逗号就让整批日记解析失败。
    """
    path = CONFIG_DIR / name
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return fallback
    if not isinstance(data, dict):
        return fallback
    return data


# 主人的习惯称呼：插件按配置传环境变量，其次读 diary/alias.json 的 `alias`，
# 都没有就用「主人」。分类关键词与标题里的说话人识别都用它，代码里不写死人名。
DEFAULT_ALIAS = "主人"
ALIAS_ENV = "PETDIARY_PARTNER_ALIAS"
_alias_cache: str | None = None


def _resolve_alias() -> str:
    """解析习惯称呼；进程内缓存一次，避免每条日记都读盘。"""
    global _alias_cache
    if _alias_cache is None:
        alias = os.environ.get(ALIAS_ENV, "").strip()
        if not alias:
            cfg = _load_config("alias.json", {})
            value = cfg.get("alias") if isinstance(cfg, dict) else None
            if isinstance(value, str):
                alias = value.strip()
        _alias_cache = alias or DEFAULT_ALIAS
    return _alias_cache


def _apply_alias(kinds: dict[str, Any]) -> dict[str, Any]:
    """把习惯称呼并进「交际」关键词，让标题里出现它时也能归到交际。"""
    alias = _resolve_alias()
    if alias == DEFAULT_ALIAS:
        return kinds
    merged = {name: list(words) for name, words in kinds.items() if isinstance(words, list)}
    if len(merged) != len(kinds):  # 配置里有非列表项，原样交回去。
        return kinds
    social = merged.setdefault("交际", [])
    if alias not in social:
        social.append(alias)
    return merged


def _book_from_path(path: Path, books: dict[str, Any]) -> tuple[str, str]:
    """从文件名 `<日期>-<slug>.md` 取册。

    只有日期没有 slug（`2026-10-19.md`）→ book=default、book_title=未命名。
    没有日期前缀时退化为整个文件名当 slug，保证不同文件不会糊成一本。
    未登记的 slug 直接用 slug 当显示名，不报错。
    """
    stem = path.stem
    date_match = DATE_RE.match(stem)
    if date_match:
        slug = stem[date_match.end() :].lstrip("-_ ").strip()
        book = slug or "default"
    else:
        book = stem.strip("-_ ") or "default"

    if book == "default":
        return "default", "未命名"

    title = books.get(book)
    if not isinstance(title, str) or not title.strip():
        title = book
    return book, title


def _clean_title(heading: str) -> str:
    """把标题行清成纯标题：去时间前缀、去标签分段、去行内 markdown。

    标签不要求用 `|` 分隔：`## 23:41 移花宫·初入 #日常` 也要清成
    `移花宫·初入`，不能把整条标题都当成标签段丢掉。

    历史标题里如果还带着旧版可见性标记，这里不特殊处理：它只是普通文本，
    会原样留在纯标题里。
    """
    title = TIME_RANGE_PREFIX_RE.sub("", heading, count=1)

    kept: list[str] = []
    for part in PIPE_SPLIT_RE.split(title):
        piece = part.strip()
        if not piece:
            continue
        # 去掉这段里的 #标签；如果去掉后什么都不剩，说明它只是标签段。
        cleaned = TAG_STRIP_RE.sub("", piece).strip()
        if not cleaned:
            continue
        kept.append(cleaned)

    title = " | ".join(kept)
    title = INLINE_MARKDOWN_RE.sub("", title)
    title = re.sub(r"[ \t]+", " ", title).strip()
    return title


def _classify_kind(title: str, tags: list[str], kinds: dict[str, Any]) -> str:
    """判定事件类型：标签优先，其次标题关键词，最后「未分类」。"""
    for tag in tags:
        if tag in KIND_TAG_VALUES:
            return tag

    scores: dict[str, int] = {}
    for kind in KINDS[:-1]:
        words = kinds.get(kind)
        if not isinstance(words, list):
            continue
        matched = {word for word in words if isinstance(word, str) and word and word in title}
        if matched:
            scores[kind] = len(matched)

    if not scores:
        return "未分类"

    best = max(scores.values())
    for kind in KIND_TIE_ORDER:
        if scores.get(kind) == best:
            return kind
    for kind in KINDS[:-1]:  # 理论上不会走到这里，留着防御未来改配置。
        if scores.get(kind) == best:
            return kind
    return "未分类"


def _detect_speaker(title: str) -> str | None:
    """从标题里的称呼识别说话人；分类不再限制这一字段。"""
    alias = _resolve_alias()
    for word in (alias, "我问他", "我说", "他让我"):
        if word in title:
            return alias
    for word in ("观众", "弹幕", "有人刷"):
        if word in title:
            return "观众"
    if "她问我" in title or "她提醒" in title or COO_RE.search(title):
        return "coo"
    return None


def _trim_blank_edges(lines: list[str]) -> list[str]:
    """去掉正文首尾的空行，但保留中间的空行与所有缩进。"""
    start, end = 0, len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return lines[start:end]


def parse_text(
    text: str,
    filename: str,
    books_override: dict[str, Any] | None = None,
    *,
    id_namespace: str = "",
    file_label: str | None = None,
) -> dict[str, Any]:
    """把一段 markdown 文本解析成一条文件级记录（schema=2 的 doc 层）。

    单独抽出来便于测试；parse_file 只是读文件后调用它。
    返回值保留 P0 的 file/date/doc_title/entries 字段，新增 book/book_title/intro；
    真正的 schema 2 外层结构由 assemble() 组装。

    P1 新增 ``books_override``：库模式用 `index.diary` 里的 `books` 覆盖
    `diary/books.json`；传 None 时保持 P0.5 的老行为。

    P4 新增 ``id_namespace`` / ``file_label``：双日记里 private 与 public 的
    同名文件需要不同的条目 id（``private/2026-10-22-daily#1``），而 ``file``
    要保留相对库根的路径，供审计定位。
    """
    path = Path(filename)
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if books_override is None or not isinstance(books_override, dict):
        books = _load_config("books.json", {})
    else:
        books = books_override
    kinds = _apply_alias(_load_config("kinds.json", DEFAULT_KINDS))

    # 先标出哪些行是「真正的标题」：代码围栏里的 # 不算。
    heading_at: list[tuple[int, str]] = []
    doc_title = ""
    doc_title_index: int | None = None
    fence: str | None = None
    for index, line in enumerate(lines):
        fence_match = FENCE_RE.match(line)
        if fence_match:
            marker = fence_match.group(1)[0]
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            continue
        if fence is not None:
            continue

        if doc_title_index is None:
            h1 = H1_RE.match(line)
            if h1:
                doc_title = h1.group(1).strip()
                doc_title_index = index
                continue

        h2h3 = H2H3_RE.match(line)
        if h2h3:
            heading_at.append((index, h2h3.group(2).strip()))

    # 开场白：第一个 ## 之前、一级标题之后的内容。没有内容就是空串。
    first_heading = heading_at[0][0] if heading_at else len(lines)
    intro_start = (doc_title_index + 1) if doc_title_index is not None else 0
    intro_lines = _trim_blank_edges(lines[intro_start:first_heading])
    intro = "\n".join(intro_lines)

    book, book_title = _book_from_path(path, books)
    date_value = _extract_date(path)
    entries: list[dict[str, Any]] = []
    stem = path.stem
    for order, (line_index, heading) in enumerate(heading_at, start=1):
        next_index = heading_at[order][0] if order < len(heading_at) else len(lines)
        body_lines = _trim_blank_edges(lines[line_index + 1 : next_index])
        body = "\n".join(body_lines)

        time_value = _extract_time(heading)
        tags = _clean_tags(heading)
        title = _clean_title(heading)
        kind = _classify_kind(title, tags, kinds)
        speaker = _detect_speaker(title)

        warnings: list[str] = []
        if time_value is None and not tags:
            warnings.append("标题未带时间/标签")
        if kind == "未分类":
            # 判不出类型也要保留条目，只给一条 warning。
            warnings.append("未能判定类型")

        entries.append(
            {
                "id": f"{id_namespace}{stem}#{order}",
                "book": book,
                "book_title": book_title,
                "date": date_value,
                "heading": heading,
                "title": title,
                "time": time_value,
                "kind": kind,
                "speaker": speaker,
                "tags": tags,
                "body": body,
                "warnings": warnings,
            }
        )

    return {
        "schema": 2,
        "file": file_label or path.name,
        "book": book,
        "book_title": book_title,
        "date": date_value,
        "doc_title": doc_title,
        "intro": intro,
        "entries": entries,
    }


def assemble(docs: list[dict[str, Any]]) -> dict[str, Any]:
    """把若干文件级记录组装成 schema 2：books / docs / entries。

    - books 按文件首次出现顺序排列，dates 升序、去重；
    - docs 只保留文件级元信息（条目在顶层 entries，避免重复）；
    - entries 按文件顺序、文件内顺序拼接，重跑稳定。
    """
    books: list[dict[str, Any]] = []
    book_index: dict[str, int] = {}
    for doc in docs:
        book = doc["book"]
        if book not in book_index:
            book_index[book] = len(books)
            books.append(
                {
                    "book": book,
                    "book_title": doc["book_title"],
                    "dates": set(),
                    "entry_count": 0,
                }
            )
        record = books[book_index[book]]
        if doc.get("date"):
            record["dates"].add(doc["date"])
        record["entry_count"] += len(doc["entries"])

    for record in books:
        record["dates"] = sorted(record["dates"])

    final_docs = [
        {
            "file": doc["file"],
            "book": doc["book"],
            "date": doc["date"],
            "doc_title": doc["doc_title"],
            "intro": doc["intro"],
            **({"scope": doc["scope"]} if doc.get("scope") else {}),
        }
        for doc in docs
    ]
    entries = [entry for doc in docs for entry in doc["entries"]]

    return {
        "schema": 2,
        "books": books,
        "docs": final_docs,
        "entries": entries,
    }


def parse_file(
    path: str | Path,
    books_override: dict[str, Any] | None = None,
    *,
    id_namespace: str = "",
    file_label: str | None = None,
) -> dict[str, Any]:
    """解析单个 markdown 文件；P4 可指定条目 id 命名空间与相对路径标签。"""
    file_path = Path(path)
    return parse_text(
        _read_text(file_path),
        file_path.name,
        books_override=books_override,
        id_namespace=id_namespace,
        file_label=file_label,
    )


def parse_directory(
    directory: str | Path,
    books_override: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """解析目录内所有 .md，按文件名排序；跳过子目录。"""
    directory_path = Path(directory)
    files = sorted(
        (p for p in directory_path.iterdir() if p.is_file() and p.suffix.lower() == ".md"),
        key=lambda p: p.name,
    )
    return [parse_file(p, books_override=books_override) for p in files]


# ---------------------------------------------------------------------------
# 命令行
# ---------------------------------------------------------------------------


def _print_human(doc: dict[str, Any]) -> None:
    print(f"文件：{doc['file']}")
    print(f"册：{doc['book_title']}（{doc['book']}）")
    print(f"日期：{doc['date'] or '（文件名里没有日期）'}")
    print(f"标题：{doc['doc_title'] or '（没有一级标题）'}")
    if doc.get("intro"):
        print(f"开场：{doc['intro'].splitlines()[0]}（共 {len(doc['intro'].splitlines())} 行）")
    print(f"条目：{len(doc['entries'])} 条")
    for entry in doc["entries"]:
        time_text = entry["time"] or "—"
        tags_text = " ".join(f"#{tag}" for tag in entry["tags"]) or "（无标签）"
        speaker_text = f"  speaker={entry['speaker']}" if entry["speaker"] else ""
        print()
        print(
            f"[{entry['id']}] {time_text}  {entry['heading']}  "
            f"[{entry['kind']}] {tags_text}{speaker_text}"
        )
        if entry["title"] != entry["heading"]:
            print(f"  title: {entry['title']}")
        for warning in entry["warnings"]:
            print(f"  ⚠ {warning}")
        if entry["body"]:
            for line in entry["body"].split("\n"):
                print(f"  {line}")


def _dump_json(value: Any) -> None:
    # ensure_ascii=False 保留中文；newline="\n" 让重跑输出逐字节稳定。
    try:
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    except (AttributeError, OSError):
        pass
    json.dump(value, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="把 markdown 日记解析成条目 JSON（P0.5，仅标准库）。",
    )
    parser.add_argument("file", nargs="?", help="单个 .md 文件路径")
    parser.add_argument("--dir", dest="directory", help="解析整个目录（按文件名排序）")
    parser.add_argument("--json", action="store_true", help="输出 JSON（默认输出人类可读摘要）")
    args = parser.parse_args(argv)

    if bool(args.file) == bool(args.directory):
        parser.error("请给出一个 md 文件，或用 --dir 给出一个目录（二选一）")

    try:
        if args.directory:
            docs = parse_directory(args.directory)
        else:
            docs = [parse_file(args.file)]
    except OSError as exc:
        print(f"错误：读取失败：{exc}", file=sys.stderr)
        return 1

    if args.json:
        # P0.5：单文件也包一层同样的 schema 2 结构，books/docs 只含该文件。
        _dump_json(assemble(docs))
    else:
        for doc in docs:
            _print_human(doc)
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
