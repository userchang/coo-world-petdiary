#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""库、审计账与防篡改检测的共用逻辑（P1）。

这个模块只做四件事，命令行的「人话」交给 diary/admin.py：
1. 读写 `index.diary`（库身份 / 双日记开关 / 册名覆盖）；
2. 维护只追加的 `audit.log.jsonl` 和 sha256 哈希链；
3. 维护 `state/hashes.json`（条目指纹 + 上次看到的内容）；
4. 发现 md 被软件外改动 / 条目消失时，写 `state/last_seen.jsonl` 并记账。

设计取舍：
- `hashes.json` 每个条目存 `{hash, heading, body}`。只存 hash 的话，
  发现被改时拿不到「上次看到的样子」，`diff` 就没法还原原话。
- 检测到篡改后**不覆盖**原指纹，直到后续版本提供「接受改动」；
  这样重复 `verify` / `build` 仍然会报同一个问题，不会把问题洗白。
- 同一份内容只报一次：`last_seen.jsonl` 里记了 `now_heading` / `now_body`，
  重跑时内容没再变就不再追加，也不重复写审计。

只使用 Python 标准库；不改 md 正文。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

# 允许 `python diary/admin.py`、`python diary/build.py` 和 `python -m diary.build` 三种跑法。
sys.path.insert(0, str(Path(__file__).resolve().parent))
from parser import (  # noqa: E402  （同目录模块，必须在 sys.path 调整后导入）
    CONFIG_DIR,
    FENCE_RE,
    H2H3_RE,
    KIND_TAG_VALUES,
    KINDS,
    parse_directory,
    parse_file,
    parse_text,
)

INDEX_NAME = "index.diary"
AUDIT_NAME = "audit.log.jsonl"
STATE_DIR = "state"
HASHES_NAME = "hashes.json"
LAST_SEEN_NAME = "last_seen.jsonl"
BACKUP_DIR = "backup"
ZERO_HASH = "0" * 64

# P3 .diary 容器
ARCHIVE_FORMAT_VERSION = 1
ARCHIVE_PROJECT = "zcdiary"
MANIFEST_NAME = "manifest.json"
ARCHIVE_REQUIRED_FILES = ("index.diary", AUDIT_NAME, f"{STATE_DIR}/{HASHES_NAME}")
CONFLICTS_DIR = "conflicts"


# ---------------------------------------------------------------------------
# 基础读写
# ---------------------------------------------------------------------------


def now_iso() -> str:
    """本地时区的 ISO 时间，带 +08:00 这类偏移。"""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def entry_fingerprint(heading: str, body: str) -> str:
    """条目指纹：sha256(heading + "\\n" + body)。"""
    return sha256_text(str(heading) + "\n" + str(body))


def canonical_json(value: Any) -> str:
    """审计链用的规范化 JSON：key 排序、紧凑分隔、保留中文。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def read_json(path: Path, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return default


def write_json(path: Path, value: Any) -> None:
    """原子写 JSON；排序 key、固定缩进，保证重跑逐字节稳定。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    os.replace(tmp, path)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """读只追加的 jsonl；坏行跳过，不让一行脏数据拖垮整本账。"""
    records: list[dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    value = json.loads(line)
                except ValueError:
                    continue
                if isinstance(value, dict):
                    records.append(value)
    except OSError:
        return []
    return records


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = canonical_json(record) + "\n"
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)


def _books_from_config() -> dict[str, Any]:
    value = read_json(CONFIG_DIR / "books.json", {})
    return value if isinstance(value, dict) else {}


# ---------------------------------------------------------------------------
# 库
# ---------------------------------------------------------------------------


def load_index(root: Path) -> dict[str, Any] | None:
    value = read_json(root / INDEX_NAME, None)
    return value if isinstance(value, dict) else None


def load_library_books(root: Path) -> dict[str, Any]:
    """库里有非空 `books` 就以库为准，否则回落到 diary/books.json。"""
    index = load_index(root) or {}
    books = index.get("books")
    if isinstance(books, dict) and books:
        filtered = {
            key: value
            for key, value in books.items()
            if isinstance(key, str) and isinstance(value, str)
        }
        if filtered:
            return filtered
    return _books_from_config()


def iter_entries(docs: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [entry for doc in docs for entry in doc.get("entries", [])]


def library_mode(root: Path) -> str:
    """`index.diary` 的册形态：`dual` 或 `single`。

    兼容 P1–P3：没有 `mode` 时看旧的 `dual_diary` 布尔值。
    """
    index = load_index(root) or {}
    mode = index.get("mode")
    if mode in ("dual", "single"):
        return str(mode)
    return "dual" if index.get("dual_diary") is True else "single"


def _markdown_sources(
    root: Path,
    scope: str = "all",
) -> list[tuple[Path, str, str]]:
    """返回本次要读取的 ``(绝对路径, 相对路径, 条目 id 命名空间)``。

    私密只是分类，不是锁：双日记模式下 ``scope=all`` / ``private`` 都会读
    ``private/``，只有显式 ``scope=public`` 才排除私密本。
    """
    root = Path(root)
    sources: list[tuple[Path, str, str]] = []
    if not root.is_dir():
        return sources
    mode = library_mode(root)
    want_private_only = scope == "private"
    try:
        root_files = sorted(
            (p for p in root.iterdir() if p.is_file() and p.suffix.lower() == ".md"),
            key=lambda p: p.name,
        )
    except OSError:
        return sources
    if not want_private_only:
        for path in root_files:
            sources.append((path, path.name, ""))
    if mode == "dual" and scope != "private":
        public_dir = root / "public"
        if public_dir.is_dir():
            try:
                for path in sorted(
                    (p for p in public_dir.iterdir() if p.is_file() and p.suffix.lower() == ".md"),
                    key=lambda p: p.name,
                ):
                    sources.append((path, f"public/{path.name}", "public/"))
            except OSError:
                pass
    if mode == "dual" and scope in ("all", "private"):
        private_dir = root / "private"
        if private_dir.is_dir():
            try:
                for path in sorted(
                    (p for p in private_dir.iterdir() if p.is_file() and p.suffix.lower() == ".md"),
                    key=lambda p: p.name,
                ):
                    sources.append((path, f"private/{path.name}", "private/"))
            except OSError:
                pass
    return sources


def library_sources(
    root: Path,
    scope: str = "all",
) -> list[tuple[Path, str, str]]:
    """公开的 source 列表入口，供 serve 逐个文件做容错解析。"""
    return _markdown_sources(root, scope)


def parse_library(
    root: Path,
    scope: str = "all",
) -> list[dict[str, Any]]:
    """按分类解析库：public 只看公开本，all / private 会读私密本。"""
    books = load_library_books(root)
    docs: list[dict[str, Any]] = []
    for path, relative, namespace in _markdown_sources(root, scope):
        doc = parse_file(
            path,
            books_override=books,
            id_namespace=namespace,
            file_label=relative,
        )
        doc["scope"] = "private" if namespace.startswith("private/") else "public"
        for entry in doc.get("entries", []):
            entry["shelf"] = doc["scope"]
        docs.append(doc)
    return docs


def set_library_mode(root: Path, mode: str) -> dict[str, Any]:
    """只改 `index.diary` 的册形态；不移动、不合并任何 md。"""
    root = Path(root)
    if mode not in ("dual", "single"):
        return {"ok": False, "code": 2, "reason": "mode 只能是 dual 或 single"}
    index = load_index(root)
    if index is None:
        return {"ok": False, "code": 2, "reason": f"{root} 里没有合法的 {INDEX_NAME}"}
    previous = library_mode(root)
    index["mode"] = mode
    index["dual_diary"] = mode == "dual"
    try:
        write_json(root / INDEX_NAME, index)
        for name in ("public", "private"):
            (root / name).mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return {"ok": False, "code": 1, "reason": f"写 index.diary 失败：{exc}"}
    return {
        "ok": True,
        "code": 0,
        "mode": mode,
        "previous": previous,
        "reason": (
            "已切到双日记；库根旧 md 视作 public，不自动搬迁"
            if mode == "dual" and previous != "dual"
            else ""
        ),
    }


# ---------------------------------------------------------------------------
# 审计账 / 哈希链
# ---------------------------------------------------------------------------


def audit_path(root: Path) -> Path:
    return root / AUDIT_NAME


def _audit_records_and_raw(root: Path) -> list[tuple[int, str, dict[str, Any] | None]]:
    path = audit_path(root)
    rows: list[tuple[int, str, dict[str, Any] | None]] = []
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            for index, line in enumerate(handle, start=1):
                raw = line.rstrip("\r\n")
                if not raw.strip():
                    rows.append((index, raw, None))
                    continue
                try:
                    value = json.loads(raw)
                except ValueError:
                    rows.append((index, raw, None))
                    continue
                rows.append((index, raw, value if isinstance(value, dict) else None))
    except OSError:
        return []
    return rows


def _last_chain(root: Path) -> tuple[int, str]:
    seq = 0
    prev = ZERO_HASH
    for _, _, record in _audit_records_and_raw(root):
        if not record:
            continue
        value = record.get("seq")
        if isinstance(value, int) and value > seq:
            seq = value
        self_hash = record.get("self_hash")
        if isinstance(self_hash, str) and re.fullmatch(r"[0-9a-f]{64}", self_hash):
            prev = self_hash
    return seq, prev


def append_audit(
    root: Path,
    *,
    actor: str,
    action: str,
    target: str,
    entry: str | None = None,
    from_value: str | None = None,
    to_value: str | None = None,
    via: str = "cli",
    note: str | None = None,
) -> dict[str, Any]:
    """追加一条审计。只追加、不读改；self_hash 覆盖去掉 self_hash 的全部字段。"""
    seq, prev_hash = _last_chain(root)
    record: dict[str, Any] = {
        "seq": seq + 1,
        "t": now_iso(),
        "actor": actor,
        "action": action,
        "target": target,
        "entry": entry,
        "via": via,
        "prev_hash": prev_hash,
    }
    if from_value is not None:
        record["from"] = from_value
    if to_value is not None:
        record["to"] = to_value
    if note:
        record["note"] = note
    record["self_hash"] = sha256_text(prev_hash + "|" + canonical_json(record))
    append_jsonl(audit_path(root), record)
    return record


def load_audit(root: Path) -> list[dict[str, Any]]:
    return [record for _, _, record in _audit_records_and_raw(root) if record]


def verify_audit(root: Path) -> tuple[list[str], int]:
    """重算整条链。返回 (问题清单, 记录条数)；不自动修。"""
    issues: list[str] = []
    prev_hash = ZERO_HASH
    expected_seq = 1
    count = 0

    for index, raw, record in _audit_records_and_raw(root):
        if record is None:
            issues.append(f"第 {index} 条（seq=?）不是合法 JSON，可能是被改")
            continue

        count += 1
        seq = record.get("seq")
        seq_text = seq if isinstance(seq, int) else "?"

        if not isinstance(seq, int) or seq != expected_seq:
            issues.append(
                f"第 {index} 条（seq={seq_text}）序号不连续（期望 {expected_seq}），"
                "可能是被删或改"
            )

        if record.get("prev_hash") != prev_hash:
            issues.append(
                f"第 {index} 条（seq={seq_text}）对不上，可能是被删或改"
            )

        payload = {key: value for key, value in record.items() if key != "self_hash"}
        computed = sha256_text(str(record.get("prev_hash", "")) + "|" + canonical_json(payload))
        if record.get("self_hash") != computed:
            issues.append(
                f"第 {index} 条（seq={seq_text}）自身哈希对不上，可能是被改"
            )

        current = record.get("self_hash")
        if isinstance(current, str):
            prev_hash = current
        expected_seq = (seq if isinstance(seq, int) else index) + 1

    return issues, count


# ---------------------------------------------------------------------------
# 指纹 / 防篡改
# ---------------------------------------------------------------------------


def hashes_path(root: Path) -> Path:
    return root / STATE_DIR / HASHES_NAME


def last_seen_path(root: Path) -> Path:
    return root / STATE_DIR / LAST_SEEN_NAME


def load_hashes(root: Path) -> dict[str, dict[str, Any]]:
    """读指纹表；兼容早期只存 hash 字符串的格式。"""
    value = read_json(hashes_path(root), {})
    if not isinstance(value, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for entry_id, record in value.items():
        if not isinstance(entry_id, str):
            continue
        if isinstance(record, str):
            result[entry_id] = {"hash": record, "heading": None, "body": None}
        elif isinstance(record, dict) and isinstance(record.get("hash"), str):
            result[entry_id] = {
                "hash": record["hash"],
                "heading": record.get("heading"),
                "body": record.get("body"),
            }
    return result


def load_last_seen(root: Path) -> list[dict[str, Any]]:
    return read_jsonl(last_seen_path(root))


def _latest_record(records: list[dict[str, Any]], entry_id: str) -> dict[str, Any] | None:
    for record in reversed(records):
        if record.get("entry") == entry_id:
            return record
    return None


def _target_of(entry_id: str) -> str:
    stem = entry_id.rsplit("#", 1)[0]
    return stem + ".md"


def _report_change(
    root: Path,
    records: list[dict[str, Any]],
    entry: dict[str, Any],
    baseline: dict[str, Any],
) -> dict[str, Any]:
    """内容变了：留一份「上次看到的样子」，并记一条 unknown/edit。

    同一份当前内容重复检查时不再追加/记账，避免 build/verify 刷屏。
    """
    entry_id = entry["id"]
    heading = entry.get("heading", "")
    body = entry.get("body", "")
    latest = _latest_record(records, entry_id)

    if (
        latest is not None
        and latest.get("now_heading") == heading
        and latest.get("now_body") == body
    ):
        return latest

    if latest is not None and latest.get("now_heading") is not None:
        old_heading = latest.get("now_heading")
        old_body = latest.get("now_body")
    else:
        old_heading = baseline.get("heading")
        old_body = baseline.get("body")

    record = {
        "entry": entry_id,
        "old_heading": old_heading,
        "old_body": old_body,
        "seen_at": now_iso(),
        "now_heading": heading,
        "now_body": body,
    }
    append_jsonl(last_seen_path(root), record)
    records.append(record)
    append_audit(
        root,
        actor="unknown",
        action="edit",
        target=_target_of(entry_id),
        entry=entry_id,
        via="cli",
        note="哈希不匹配",
    )
    return record


def _report_missing(
    root: Path,
    records: list[dict[str, Any]],
    entry_id: str,
    baseline: dict[str, Any],
) -> dict[str, Any]:
    """hashes 里有、md 里没有：报条目消失，同一状态只记一次。"""
    latest = _latest_record(records, entry_id)
    if latest is not None and latest.get("now_heading") is None:
        return latest

    if latest is not None and latest.get("now_heading") is not None:
        old_heading = latest.get("now_heading")
        old_body = latest.get("now_body")
    else:
        old_heading = baseline.get("heading")
        old_body = baseline.get("body")

    record = {
        "entry": entry_id,
        "old_heading": old_heading,
        "old_body": old_body,
        "seen_at": now_iso(),
        "now_heading": None,
        "now_body": None,
    }
    append_jsonl(last_seen_path(root), record)
    records.append(record)
    append_audit(
        root,
        actor="unknown",
        action="edit",
        target=_target_of(entry_id),
        entry=entry_id,
        via="cli",
        note="条目消失",
    )
    return record


def inspect_library(
    root: Path,
    *,
    record: bool = True,
    register: bool = True,
    docs: list[dict[str, Any]] | None = None,
    scope: str = "all",
) -> dict[str, Any]:
    """库校验：链 + 指纹。

    返回 docs / entries / changed / missing / new / chain_issues。
    `record=True` 时会把变化写进 last_seen 和审计；`build` 与 `verify` 都走这里。
    `docs` 可选：调用方已经做过容错解析时可直接传入，避免重复读盘。

    私密只是分类：双日记模式下 private/ 始终参与校验；单本模式不读
    private/，因此旧指纹也不判定为「消失」。
    """
    if docs is None:
        docs = parse_library(root, scope=scope)
    entries = iter_entries(docs)
    hashes = load_hashes(root)
    last_seen = load_last_seen(root)
    private_visible = library_mode(root) == "dual" and scope != "public"

    changed: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    new_ids: list[str] = []
    present: set[str] = set()

    for entry in entries:
        entry_id = entry["id"]
        present.add(entry_id)
        fingerprint = entry_fingerprint(entry.get("heading", ""), entry.get("body", ""))
        baseline = hashes.get(entry_id)

        if baseline is None:
            hashes[entry_id] = {
                "hash": fingerprint,
                "heading": entry.get("heading", ""),
                "body": entry.get("body", ""),
            }
            new_ids.append(entry_id)
            continue

        if baseline.get("hash") == fingerprint:
            continue

        changed.append(entry)
        if record:
            _report_change(root, last_seen, entry, baseline)

    for entry_id, baseline in sorted(hashes.items()):
        if entry_id in present:
            continue
        # 单本模式或 scope=public 时 private/ 根本没读；不能据此判定消失。
        if entry_id.startswith("private/") and not private_visible:
            continue
        missing.append(
            {
                "entry": entry_id,
                "old_heading": baseline.get("heading"),
                "old_body": baseline.get("body"),
            }
        )
        if record:
            _report_missing(root, last_seen, entry_id, baseline)

    if register:
        write_json(hashes_path(root), hashes)

    chain_issues, audit_count = verify_audit(root)
    return {
        "docs": docs,
        "entries": entries,
        "hashes": hashes,
        "changed": changed,
        "missing": missing,
        "new_ids": new_ids,
        "chain_issues": chain_issues,
        "audit_count": audit_count,
    }


# ---------------------------------------------------------------------------
# 条目定位辅助
# ---------------------------------------------------------------------------


def heading_line_index(text: str, ordinal: int) -> int | None:
    """按解析器同样的围栏规则，找第 ordinal（1 起）个条目标题所在行号。"""
    lines = text.splitlines()
    fence: str | None = None
    count = 0
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
        if H2H3_RE.match(line):
            count += 1
            if count == ordinal:
                return index
    return None


# ---------------------------------------------------------------------------
# P4：唯一写入入口 append / 只读摘要
# ---------------------------------------------------------------------------


def _book_slug(value: str) -> str:
    """册名落文件名前做最小清洗；禁止路径分隔符与空名。"""
    text = str(value or "").strip()
    text = re.sub(r"[\\/:*?\"<>|]+", "-", text)
    text = re.sub(r"\s+", "-", text).strip(" .-")
    return text


def _count_entry_headings(text: str) -> int:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    fence: str | None = None
    count = 0
    for line in lines:
        fence_match = FENCE_RE.match(line)
        if fence_match:
            marker = fence_match.group(1)[0]
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            continue
        if fence is None and H2H3_RE.match(line):
            count += 1
    return count


def append_entry(
    root: Path,
    *,
    book: str,
    time: str,
    title: str,
    body: str,
    kind: str | None = None,
    private: bool = False,
    actor: str = "coo",
    via: str = "tool",
    date_value: str | None = None,
) -> dict[str, Any]:
    """唯一写入入口：查重 → 选 public/private → 追加 md → 更新指纹 → 审计。

    返回 ``{ok, entry, path, audit_seq, heading, code, reason, hint}``。
    World、面板和 CLI 都只调用这里，不自己拼 md。
    """
    root = Path(root)
    result: dict[str, Any] = {
        "ok": False,
        "code": 1,
        "reason": "",
        "hint": "",
        "entry": None,
        "path": None,
        "audit_seq": None,
    }
    if not root.is_dir() or load_index(root) is None:
        result.update(
            reason="桌宠日记还没初始化，先跑 admin.py init",
            hint=f"库根：{root}",
            code=2,
        )
        return result

    book_text = str(book or "").strip()
    time_text = str(time or "").strip()
    title_text = str(title or "").strip()
    body_text = str(body or "").replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
    kind_text = str(kind).strip() if kind not in (None, "") else None
    date_text = str(date_value or datetime.now().strftime("%Y-%m-%d")).strip()

    if not book_text or not title_text or not body_text:
        result.update(reason="book / title / body 都不能为空", code=2)
        return result
    if not re.fullmatch(r"\d{1,2}:\d{2}", time_text):
        result.update(reason="time 必须是 HH:MM", code=2)
        return result
    hour, minute = (int(part) for part in time_text.split(":"))
    if hour > 23 or minute > 59:
        result.update(reason="time 不是有效时刻", code=2)
        return result
    time_text = f"{hour:02d}:{minute:02d}"
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_text):
        result.update(reason="date 必须是 YYYY-MM-DD", code=2)
        return result
    if kind_text is not None and kind_text not in KIND_TAG_VALUES:
        allowed = " / ".join(KINDS[:-1])
        result.update(reason=f"kind 只能是 {allowed}（不写算未分类）", code=2)
        return result
    if any(re.match(r"^\s*#{2,3}\s", line) for line in body_text.split("\n")):
        result.update(
            reason="正文里不能出现二级/三级标题，否则会被拆成新条目",
            hint="把 `##` 换成普通文字或缩进；正文只写这一段的内容。",
            code=2,
        )
        return result

    slug = _book_slug(book_text)
    if not slug:
        result.update(reason="book 清洗后为空，请换一个短名字", code=2)
        return result

    if private:
        # 私密是分类，不是锁：写私密本时若还是单本，切到双日记即可，
        # 不移动、不合并库根旧 md（与 admin.py mode --set dual 行为一致）。
        if library_mode(root) != "dual":
            switched = set_library_mode(root, "dual")
            if not switched.get("ok"):
                result.update(
                    reason=switched.get("reason") or "切到双日记失败",
                    code=int(switched.get("code") or 1),
                )
                return result
        prefix = "private/"
        namespace = "private/"
    elif library_mode(root) == "dual":
        prefix = "public/"
        namespace = "public/"
    else:
        prefix = ""
        namespace = ""

    # 幂等：同册、同日期、同时间、同标题已存在就拒绝。
    target_key = (slug, date_text, time_text, title_text)
    for entry in iter_entries(parse_library(root)):
        if (
            str(entry.get("book") or ""),
            str(entry.get("date") or ""),
            str(entry.get("time") or ""),
            str(entry.get("title") or ""),
        ) == target_key:
            result.update(
                reason=f"这篇已经写过了：{entry.get('id')}",
                hint="同册同时间同标题不会重复落盘；换时间或标题再写。",
                entry=entry.get("id"),
                path=entry.get("file") or entry.get("path"),
            )
            return result

    relative = f"{prefix}{date_text}-{slug}.md"
    target = root.joinpath(*PurePosixPath(relative).parts)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_text(f"# {book_text}\n", encoding="utf-8", newline="\n")
        heading = f"{time_text} {title_text.replace('|', '｜')}"
        if kind_text:
            heading += f" #{kind_text}"
        block = f"## {heading}\n\n{body_text}"
        _append_blocks(target, [block])
    except OSError as exc:
        result.update(reason=f"写日记失败：{exc}", code=1)
        return result

    target_text = _decode_bytes(target.read_bytes())
    target_doc = parse_text(
        target_text,
        target.name,
        books_override=load_library_books(root),
        id_namespace=namespace,
        file_label=relative,
    )
    entry = target_doc["entries"][-1] if target_doc.get("entries") else None
    if entry is None:
        result.update(reason="写入后解析不到条目，已停止更新指纹", code=1)
        return result
    entry_id = entry["id"]

    try:
        hashes = load_hashes(root)
        hashes[entry_id] = {
            "hash": entry_fingerprint(entry.get("heading", ""), entry.get("body", "")),
            "heading": entry.get("heading", ""),
            "body": entry.get("body", ""),
        }
        write_json(hashes_path(root), hashes)
    except OSError as exc:
        result.update(reason=f"更新条目指纹失败：{exc}", code=1)
        return result

    try:
        audit = append_audit(
            root,
            actor=actor,
            action="append",
            target=relative,
            entry=entry_id,
            via=via,
            note=kind_text or None,
        )
    except OSError as exc:
        result.update(reason=f"写审计失败：{exc}", code=1)
        return result

    result.update(
        ok=True,
        code=0,
        entry=entry_id,
        path=relative,
        audit_seq=audit.get("seq"),
        heading=heading,
        private=bool(private),
    )
    return result


def delete_entry(
    root: Path,
    entry_id: str,
    *,
    actor: str = "human",
    via: str = "cli",
    note: str | None = None,
) -> dict[str, Any]:
    """删除一条日记：整段移除 md、清掉指纹、写 last_seen 墓碑和 delete 审计。

    条目在 md 里找不到、但基线里还有指纹时，进入「纯基线清理」模式：
    不动 md，只移除残留指纹并留审计；md 与基线都不存在时报错。
    这样库外直接被删掉的条目，可以经面板/CLI 确认后恢复 verify 正常。
    """
    root = Path(root)
    entry_text = str(entry_id or "").strip()
    result: dict[str, Any] = {
        "ok": False,
        "code": 1,
        "reason": "",
        "entry": entry_text,
        "mode": None,
        "path": None,
        "heading": None,
        "audit_seq": None,
        "hash_removed": False,
        "last_seen_added": False,
        "backup": None,
    }

    if not root.is_dir():
        result.update(reason=f"库目录不存在：{root}", code=2)
        return result
    if not entry_text:
        result.update(reason="entry_id 不能为空", code=2)
        return result

    docs = parse_library(root, scope="all")
    found: tuple[dict[str, Any], dict[str, Any]] | None = None
    for doc in docs:
        for entry in doc.get("entries", []):
            if entry.get("id") == entry_text:
                found = (doc, entry)
                break
        if found is not None:
            break

    hashes = load_hashes(root)
    baseline = hashes.get(entry_text)
    if found is None and baseline is None:
        result.update(reason=f"找不到条目：{entry_text}", code=2)
        return result

    doc, entry = found if found is not None else (None, None)
    old_entries = list(doc.get("entries", [])) if doc is not None else []
    heading = (
        str(entry.get("heading") or "")
        if entry is not None
        else str((baseline or {}).get("heading") or "")
    )
    body = (
        str(entry.get("body") or "")
        if entry is not None
        else str((baseline or {}).get("body") or "")
    )
    relative = str(doc.get("file") or "") if doc is not None else _target_of(entry_text)
    result.update(mode="deleted" if doc is not None else "baseline", path=relative, heading=heading)

    try:
        ordinal = int(entry_text.rsplit("#", 1)[1])
    except (IndexError, ValueError):
        result.update(reason=f"条目 id 不合法：{entry_text}", code=2)
        return result

    # 删除前先摘下被删条目的基线；后面若移位，再把它移给新的序号。
    if baseline is not None:
        hashes.pop(entry_text, None)

    # 1) 有条目就整段移除；先备份原文件。
    if doc is not None and entry is not None:
        source = root.joinpath(*PurePosixPath(relative).parts)
        try:
            text, encoding = _read_source_text(source)
        except OSError as exc:
            result.update(reason=f"读取失败：{exc}", code=1)
            return result
        lines = text.splitlines(keepends=True)
        start = heading_line_index(text, ordinal)
        if start is None:
            result.update(reason=f"在 {relative} 里定位不到第 {ordinal} 个标题", code=1)
            return result
        end = heading_line_index(text, ordinal + 1)
        if end is None:
            end = len(lines)
        del lines[start:end]
        new_text = "".join(lines)
        if new_text and not new_text.endswith(("\n", "\r")):
            new_text += "\n"
        try:
            backup = _backup_before_write(root, source)
        except OSError as exc:
            result.update(reason=f"备份失败：{exc}", code=1)
            return result
        result["backup"] = str(backup) if backup else None
        try:
            source.write_bytes(new_text.encode(encoding))
        except OSError as exc:
            result.update(reason=f"写回失败：{exc}", code=1)
            return result

        # 删除后同文件后面的条目序号会前移；把基线一并挪到新 id，
        # 否则 verify 会把后面所有条目误报成「消失 + 新增」。
        namespace = "private/" if relative.startswith("private/") else (
            "public/" if relative.startswith("public/") else ""
        )
        try:
            fresh_doc = parse_file(
                source,
                books_override=load_library_books(root),
                id_namespace=namespace,
                file_label=relative,
            )
        except OSError as exc:
            result.update(reason=f"删除后重新解析失败：{exc}", code=1)
            return result
        fresh_entries = fresh_doc.get("entries", [])
        for old_entry in old_entries:
            try:
                old_ordinal = int(str(old_entry.get("id", "")).rsplit("#", 1)[1])
            except (IndexError, ValueError):
                continue
            if old_ordinal <= ordinal:
                continue
            new_index = old_ordinal - 2
            if new_index < 0 or new_index >= len(fresh_entries):
                continue
            old_id = old_entry.get("id")
            new_id = fresh_entries[new_index].get("id")
            if old_id in hashes and new_id:
                hashes[new_id] = hashes.pop(old_id)

    # 2) 指纹：有就删/移位后写回；没有也算正常。
    if baseline is not None:
        try:
            _backup_before_write(root, hashes_path(root))
            write_json(hashes_path(root), hashes)
        except OSError as exc:
            result.update(reason=f"更新条目指纹失败：{exc}", code=1)
            return result
        result["hash_removed"] = True

    # 3) last_seen：写一条墓碑；如果最近一条已经是「消失」，不重复追加。
    records = load_last_seen(root)
    latest = _latest_record(records, entry_text)
    if not (latest is not None and latest.get("now_heading") is None):
        old_heading = heading or (baseline or {}).get("heading")
        old_body = body or (baseline or {}).get("body")
        try:
            append_jsonl(
                last_seen_path(root),
                {
                    "entry": entry_text,
                    "old_heading": old_heading,
                    "old_body": old_body,
                    "seen_at": now_iso(),
                    "now_heading": None,
                    "now_body": None,
                },
            )
        except OSError as exc:
            result.update(reason=f"更新 last_seen 失败：{exc}", code=1)
            return result
        result["last_seen_added"] = True

    # 4) 审计：删除是留痕操作，不物理抹掉这条记录。
    try:
        audit = append_audit(
            root,
            actor=actor,
            action="delete",
            target=relative,
            entry=entry_text,
            from_value=heading or None,
            via=via,
            note=note,
        )
    except OSError as exc:
        result.update(reason=f"写审计失败：{exc}", code=1)
        return result

    result.update(ok=True, code=0, audit_seq=audit.get("seq"))
    return result


def _read_source_text(path: Path) -> tuple[str, str]:
    """读 md 并记住编码，删除写回时保持原编码（默认 UTF-8）。"""
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig"), "utf-8-sig"
    for encoding in ("utf-8", "gb18030"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8"


def read_summary(
    root: Path,
    *,
    scope: str = "public",
    limit: int = 5,
    book: str | None = None,
) -> dict[str, Any]:
    """`diary_read` 的数据面：只读，不写审计；scope=all 连私密本一起看。"""
    root = Path(root)
    if scope not in ("public", "all"):
        return {"ok": False, "code": 2, "reason": "scope 只能是 public 或 all"}
    try:
        limit_value = max(1, min(50, int(limit)))
    except (TypeError, ValueError):
        return {"ok": False, "code": 2, "reason": "limit 必须是 1–50 的整数"}
    if not root.is_dir() or load_index(root) is None:
        return {
            "ok": False,
            "code": 2,
            "reason": "桌宠日记还没初始化，先跑 admin.py init",
        }

    effective_scope = scope
    docs = parse_library(root, scope=effective_scope)
    entries = iter_entries(docs)
    book_filter = str(book).strip() if book is not None else ""
    if book_filter:
        entries = [entry for entry in entries if entry.get("book") == book_filter]
    today_text = datetime.now().strftime("%Y-%m-%d")
    today_entries = [entry for entry in entries if entry.get("date") == today_text]

    counts: dict[str, int] = {}
    for entry in entries:
        book = str(entry.get("book") or "default")
        counts[book] = counts.get(book, 0) + 1

    recent = []
    for entry in reversed(entries[-limit:]):
        recent.append(
            {
                "id": entry.get("id"),
                "book": entry.get("book"),
                "date": entry.get("date"),
                "time": entry.get("time"),
                "title": entry.get("title"),
                "kind": entry.get("kind"),
                "shelf": "private" if entry.get("shelf") == "private" else "public",
                "body": str(entry.get("body") or "")[:240],
            }
        )

    payload: dict[str, Any] = {
        "ok": True,
        "code": 0,
        "scope": effective_scope,
        "today": {"date": today_text, "count": len(today_entries)},
        "counts": counts,
        "total": len(entries),
        "entries": recent,
        "mode": library_mode(root),
        "private_count": sum(1 for entry in entries if entry.get("shelf") == "private"),
    }
    return payload


# ---------------------------------------------------------------------------
# P3：.diary 单文件容器（zip）导出 / 导入
# ---------------------------------------------------------------------------

# 说明：
# - 包内路径一律相对库根、用 `/`；不写任何绝对路径。
# - manifest.json 的 file_count 统计「内容文件」，不含 manifest 自己；
#   manifest.files 列出的也是内容文件。
# - 导入先校验 format_version / entry_digest / 归档内 verify，再动本地文件。
# - 所有对本地 md 的写入都经过本模块，且写前备份到 state/backup/。


def _archive_result(ok: bool, code: int, reason: str = "", **extra: Any) -> dict[str, Any]:
    value: dict[str, Any] = {"ok": ok, "code": code, "reason": reason}
    value.update(extra)
    return value


def _decode_bytes(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _jsonl_from_bytes(raw: bytes) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in _decode_bytes(raw).splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def _safe_archive_name(name: str) -> bool:
    if not name or "\x00" in name or "\\" in name:
        return False
    if name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        return False
    parts = PurePosixPath(name).parts
    if not parts:
        return False
    return all(part not in ("", ".", "..") for part in parts)


def _archive_allowed(name: str) -> bool:
    if name == MANIFEST_NAME or name in ARCHIVE_REQUIRED_FILES:
        return True
    if "/" not in name and name.endswith(".md"):
        return True
    return any(
        name.startswith(prefix) and name.endswith(".md")
        for prefix in ("cast/", "threads/", "public/", "private/")
    )


def _archive_parse(files: dict[str, bytes]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None]:
    """解析包内日记 md：库根 + public/ + private/，各用自己的 id 命名空间。"""
    books: dict[str, Any] | None = None
    index_raw = files.get(INDEX_NAME)
    if index_raw:
        try:
            index_value = json.loads(_decode_bytes(index_raw))
        except ValueError:
            return [], [], "index.diary 不是合法 JSON"
        if isinstance(index_value, dict) and isinstance(index_value.get("books"), dict):
            books = index_value["books"] or None

    docs: list[dict[str, Any]] = []
    for name in sorted(files):
        if not name.endswith(".md"):
            continue
        if "/" not in name:
            namespace = ""
        elif name.startswith("public/"):
            namespace = "public/"
        elif name.startswith("private/"):
            namespace = "private/"
        else:
            continue
        try:
            doc = parse_text(
                _decode_bytes(files[name]),
                name.rsplit("/", 1)[-1],
                books_override=books,
                id_namespace=namespace,
                file_label=name,
            )
            doc["scope"] = "private" if namespace.startswith("private/") else "public"
            for entry in doc.get("entries", []):
                entry["shelf"] = doc["scope"]
            docs.append(doc)
        except Exception as exc:  # noqa: BLE001
            return [], [], f"{name} 解析失败：{exc}"
    return docs, iter_entries(docs), None


def archive_entry_digest(entries: Iterable[dict[str, Any]]) -> str:
    """条目集合的 sha256：只取内容字段，按 id 排序后规范化 JSON。"""
    payload: list[dict[str, Any]] = []
    for entry in sorted(entries, key=lambda item: str(item.get("id", ""))):
        payload.append(
            {
                "id": entry.get("id", ""),
                "book": entry.get("book", ""),
                "date": entry.get("date") or "",
                "heading": entry.get("heading", ""),
                "body": entry.get("body", ""),
            }
        )
    return sha256_text(canonical_json(payload))


def _archive_chain_head(files: dict[str, bytes]) -> str:
    records = _jsonl_from_bytes(files.get(AUDIT_NAME, b""))
    for record in reversed(records):
        value = record.get("self_hash")
        if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value):
            return value
    return ZERO_HASH


def _read_archive(path: Path) -> tuple[dict[str, bytes] | None, str | None]:
    try:
        with zipfile.ZipFile(path, "r") as archive:
            files: dict[str, bytes] = {}
            for info in archive.infolist():
                if info.is_dir():
                    continue
                name = info.filename
                if not _safe_archive_name(name):
                    return None, f"包内路径不安全：{name}"
                if not _archive_allowed(name):
                    return None, f"包内有未知文件：{name}"
                if name in files:
                    return None, f"包内文件重复：{name}"
                files[name] = archive.read(info)
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        return None, f"读不了 .diary 包：{exc}"
    return files, None


def _extract_archive(files: dict[str, bytes], destination: Path) -> None:
    for name, data in files.items():
        if name == MANIFEST_NAME:
            continue
        target = destination.joinpath(*PurePosixPath(name).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def _verify_archive(files: dict[str, bytes]) -> list[str]:
    """把包解到临时目录，用现成的 inspect_library 做一次只读 verify。

    不用 TemporaryDirectory：Windows 上它退出时会 chmod 临时目录，某些沙箱/ACL
    环境会拒绝；这里用 mkdtemp + rmtree(ignore_errors=True)，清理失败不影响校验结果。
    """
    # 不要 mkdtemp：它在 Windows 上建 0700 目录，沙箱令牌可能写不进去。
    # 用普通 mkdir 继承上级 ACL。
    temporary = Path(tempfile.gettempdir()) / f"diary-import-{os.getpid()}-{uuid.uuid4().hex}"
    temporary.mkdir(parents=True, exist_ok=False)
    try:
        try:
            _extract_archive(files, temporary)
            result = inspect_library(temporary, record=False, register=False)
        except Exception as exc:  # noqa: BLE001
            return [f"校验失败：{exc}"]

        issues: list[str] = []
        if result["chain_issues"]:
            issues.extend(f"审计链：{item}" for item in result["chain_issues"][:5])
        if result["changed"]:
            issues.extend(
                f"指纹不匹配：{entry.get('id')}" for entry in result["changed"][:5]
            )
        if result["missing"]:
            issues.extend(
                f"条目消失：{item.get('entry')}" for item in result["missing"][:5]
            )
        return issues
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def _safe_parse_library(root: Path) -> list[dict[str, Any]]:
    """导入时容错解析本地库：单个文件坏掉不影响其余文件。"""
    books = load_library_books(root)
    docs: list[dict[str, Any]] = []
    for path, relative, namespace in _markdown_sources(root):
        try:
            doc = parse_file(
                path,
                books_override=books,
                id_namespace=namespace,
                file_label=relative,
            )
            doc["scope"] = "private" if namespace.startswith("private/") else "public"
            for entry in doc.get("entries", []):
                entry["shelf"] = doc["scope"]
            docs.append(doc)
        except Exception:  # noqa: BLE001
            continue
    return docs


def _backup_before_write(root: Path, source: Path) -> Path | None:
    """动已有文件前先复制到 state/backup/。新文件返回 None。"""
    if not source.exists():
        return None
    backup_dir = root / STATE_DIR / BACKUP_DIR
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = backup_dir / f"{source.name}.{stamp}.bak"
    shutil.copy2(source, backup)
    return backup


def _write_new_file(root: Path, relative: str, data: bytes) -> Path:
    target = root.joinpath(*PurePosixPath(relative).parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def _entry_block(text: str, ordinal: int) -> str | None:
    """从原文里切出第 ordinal 条（标题到下一个标题前），保留正文原样。"""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    start = heading_line_index(text, ordinal)
    if start is None:
        return None
    end = heading_line_index(text, ordinal + 1)
    if end is None:
        end = len(lines)
    block = lines[start:end]
    while block and not block[-1].strip():
        block.pop()
    return "\n".join(block)


def _append_blocks(path: Path, blocks: Iterable[str]) -> None:
    """只在文件末尾追加，已有字节一个不动。"""
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        encoding = "utf-8"
    else:
        encoding = "utf-8"
        for candidate in ("utf-8", "gb18030"):
            try:
                raw.decode(candidate)
                encoding = candidate
                break
            except UnicodeDecodeError:
                continue
    parts: list[bytes] = []
    if raw and not raw.endswith(b"\n"):
        parts.append(b"\n")
    first = True
    for block in blocks:
        if raw or not first:
            parts.append(b"\n")
        parts.append(block.encode(encoding, errors="replace"))
        parts.append(b"\n")
        first = False
    path.write_bytes(raw + b"".join(parts))


def _append_raw_audit(root: Path, raw: bytes) -> int:
    """把源审计记录原样追加到本地空审计；返回记录条数。"""
    if not raw.strip():
        return 0
    path = audit_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = raw.replace(b"\r\n", b"\n").rstrip(b"\n") + b"\n"
    with open(path, "ab") as handle:
        handle.write(payload)
    return len(_jsonl_from_bytes(raw))


def _natural_key(entry: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(entry.get("book") or ""),
        str(entry.get("date") or ""),
        str(entry.get("time") or ""),
        str(entry.get("title") or entry.get("heading") or ""),
    )


def export_library(root: Path, out_path: Path) -> dict[str, Any]:
    """把一个库打成 .diary（zip）。双日记模式下公开本与私密本都导出。"""
    root = Path(root)
    out_path = Path(out_path)
    if not root.is_dir():
        return _archive_result(False, 2, f"库目录不存在：{root}")
    if load_index(root) is None:
        return _archive_result(False, 2, f"{root} 里没有合法的 {INDEX_NAME}")

    mode = library_mode(root)
    files: dict[str, bytes] = {}
    try:
        for path in sorted(root.glob("*.md")):
            if path.is_file():
                files[path.name] = path.read_bytes()
        if mode == "dual":
            for path in sorted((root / "public").glob("*.md")):
                if path.is_file():
                    files[f"public/{path.name}"] = path.read_bytes()
        for sub in ("cast", "threads"):
            directory = root / sub
            if not directory.is_dir():
                continue
            for path in sorted(directory.rglob("*.md")):
                if path.is_file():
                    files[path.relative_to(root).as_posix()] = path.read_bytes()
        for name in ARCHIVE_REQUIRED_FILES:
            path = root / name
            if path.is_file():
                files[name] = path.read_bytes()
            elif name == AUDIT_NAME:
                files[name] = b""
            elif name == f"{STATE_DIR}/{HASHES_NAME}":
                files[name] = b"{}\n"
            else:
                return _archive_result(False, 2, f"库缺少 {name}")

        if mode == "dual":
            directory = root / "private"
            if directory.is_dir():
                for path in sorted(directory.glob("*.md")):
                    if path.is_file():
                        files[path.relative_to(root).as_posix()] = path.read_bytes()
    except OSError as exc:
        return _archive_result(False, 1, f"读取库失败：{exc}")

    docs, entries, parse_error = _archive_parse(files)
    if parse_error:
        return _archive_result(False, 1, parse_error)

    index = load_index(root) or {}
    manifest = {
        "format_version": ARCHIVE_FORMAT_VERSION,
        "project": ARCHIVE_PROJECT,
        "exported_at": now_iso(),
        "entry_count": len(entries),
        "file_count": len(files),
        "chain_head": _archive_chain_head(files),
        "entry_digest": archive_entry_digest(entries),
        "files": sorted(files),
        "library": {
            "name": index.get("name") or root.name,
            "mode": mode,
            "dual_diary": mode == "dual",
        },
    }
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for name in sorted(files):
                archive.writestr(name, files[name])
            archive.writestr(MANIFEST_NAME, manifest_bytes)
    except (OSError, zipfile.BadZipFile) as exc:
        return _archive_result(False, 1, f"写 .diary 失败：{exc}")

    return _archive_result(
        True,
        0,
        "",
        out=str(out_path),
        entry_count=len(entries),
        file_count=len(files),
        chain_head=manifest["chain_head"],
        entry_digest=manifest["entry_digest"],
    )


def import_library(root: Path, archive_path: Path) -> dict[str, Any]:
    """校验并导入 .diary；本地较新者胜，冲突写 state/conflicts/<时间>/。"""
    root = Path(root)
    archive_path = Path(archive_path)
    if not archive_path.is_file():
        return _archive_result(False, 2, f"找不到 .diary 文件：{archive_path}")
    if root.exists() and not root.is_dir():
        return _archive_result(False, 2, f"库根不是目录：{root}")

    files, read_error = _read_archive(archive_path)
    if read_error or files is None:
        return _archive_result(False, 1, read_error or "读包失败")

    manifest_raw = files.get(MANIFEST_NAME)
    if not manifest_raw:
        return _archive_result(False, 1, "包里没有 manifest.json")
    try:
        manifest = json.loads(_decode_bytes(manifest_raw))
    except ValueError as exc:
        return _archive_result(False, 1, f"manifest.json 不是合法 JSON：{exc}")
    if not isinstance(manifest, dict):
        return _archive_result(False, 1, "manifest.json 必须是 JSON 对象")
    if manifest.get("format_version") != ARCHIVE_FORMAT_VERSION:
        return _archive_result(
            False,
            1,
            f"不认识的 format_version：{manifest.get('format_version')}（只支持 {ARCHIVE_FORMAT_VERSION}）",
        )
    if manifest.get("project") != ARCHIVE_PROJECT:
        return _archive_result(
            False, 1, f"project 不是 {ARCHIVE_PROJECT}：{manifest.get('project')}"
        )

    missing = [name for name in ARCHIVE_REQUIRED_FILES if name not in files]
    if missing:
        return _archive_result(False, 1, "包里缺文件：" + "、".join(missing))

    payload_names = {name for name in files if name != MANIFEST_NAME}
    if manifest.get("file_count") != len(payload_names):
        return _archive_result(
            False,
            1,
            f"manifest.file_count={manifest.get('file_count')}，实际 {len(payload_names)}",
        )
    listed = manifest.get("files")
    if isinstance(listed, list) and set(str(item) for item in listed) != payload_names:
        return _archive_result(False, 1, "manifest.files 与实际文件列表不一致")

    docs, entries, parse_error = _archive_parse(files)
    if parse_error:
        return _archive_result(False, 1, parse_error)
    if manifest.get("entry_count") != len(entries):
        return _archive_result(
            False,
            1,
            f"manifest.entry_count={manifest.get('entry_count')}，实际 {len(entries)}",
        )

    digest = archive_entry_digest(entries)
    if manifest.get("entry_digest") != digest:
        return _archive_result(
            False,
            1,
            f"entry_digest 对不上（manifest={manifest.get('entry_digest')}，实际={digest}）",
        )

    chain_head = _archive_chain_head(files)
    if manifest.get("chain_head") != chain_head:
        return _archive_result(
            False,
            1,
            f"chain_head 对不上（manifest={manifest.get('chain_head')}，实际={chain_head}）",
        )

    verify_issues = _verify_archive(files)
    if verify_issues:
        return _archive_result(False, 1, "verify 不通过：" + "；".join(verify_issues))

    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _archive_result(False, 2, f"建库目录失败：{exc}")

    local_docs = _safe_parse_library(root)
    local_entries = iter_entries(local_docs)
    local_audit = load_audit(root)
    local_hashes = load_hashes(root)
    local_index = load_index(root)
    audit_file = audit_path(root)
    empty_branch = (
        len(local_entries) == 0
        and len(local_audit) == 0
        and (not audit_file.exists() or audit_file.stat().st_size == 0)
    )

    archive_docs_by_file = {doc["file"]: doc for doc in docs}
    archive_ids = {entry.get("id") for entry in entries}
    reconcile_ids: set[str] = set()
    added_entries: list[str] = []
    added_files: list[str] = []
    conflicts: list[dict[str, Any]] = []
    conflict_files_written: set[str] = set()
    changed = False

    exported_at = str(manifest.get("exported_at") or "")
    stamp = re.sub(r"[^0-9]", "", exported_at)[:14] or datetime.now().strftime("%Y%m%d%H%M%S")
    conflict_dir = root / STATE_DIR / CONFLICTS_DIR / f"{stamp}-{digest[:8]}"

    def record_conflict(relative: str, data: bytes, detail: dict[str, Any]) -> bool:
        nonlocal changed
        conflict_path = conflict_dir.joinpath(*PurePosixPath(relative).parts)
        wrote = False
        if not conflict_path.exists():
            conflict_path.parent.mkdir(parents=True, exist_ok=True)
            conflict_path.write_bytes(data)
            changed = True
            wrote = True
        conflict_files_written.add(relative)
        item = dict(detail)
        item["conflict_file"] = conflict_path.relative_to(root).as_posix()
        item["new_file"] = wrote
        conflicts.append(item)
        return wrote

    # 1) 顶层 md 与 public/：缺的整份复制；已有的逐条合并。
    for relative in sorted(
        name
        for name in files
        if name.endswith(".md") and ("/" not in name or name.startswith("public/"))
    ):
        data = files[relative]
        local_path = root / relative
        incoming_doc = archive_docs_by_file.get(relative)
        if incoming_doc is None:
            continue
        if not local_path.exists():
            _write_new_file(root, relative, data)
            added_files.append(relative)
            changed = True
            for entry in incoming_doc["entries"]:
                reconcile_ids.add(entry["id"])
                added_entries.append(entry["id"])
            continue

        if local_path.read_bytes() == data:
            for entry in incoming_doc["entries"]:
                reconcile_ids.add(entry["id"])
            continue

        local_doc = next(
            (doc for doc in local_docs if doc.get("file") == relative), None
        )
        if local_doc is None:
            record_conflict(
                relative,
                data,
                {"file": relative, "kind": "file", "reason": "本地文件无法解析"},
            )
            continue

        local_by_id = {entry.get("id"): entry for entry in local_doc["entries"]}
        local_by_natural = {_natural_key(entry): entry for entry in local_doc["entries"]}
        incoming_text = _decode_bytes(data)
        blocks: list[str] = []

        for entry in incoming_doc["entries"]:
            local_match = local_by_id.get(entry.get("id"))
            if local_match is None:
                local_match = local_by_natural.get(_natural_key(entry))
            if local_match is None:
                try:
                    ordinal = int(str(entry.get("id", "")).rsplit("#", 1)[1])
                except (IndexError, ValueError):
                    ordinal = 0
                block = _entry_block(incoming_text, ordinal) if ordinal else None
                if block is None:
                    block = "## " + str(entry.get("heading") or "") + "\n\n" + str(entry.get("body") or "")
                blocks.append(block)
                added_entries.append(entry.get("id"))
                reconcile_ids.add(entry.get("id"))
                continue

            reconcile_ids.add(local_match.get("id"))
            if entry.get("body") != local_match.get("body"):
                record_conflict(
                    relative,
                    data,
                    {
                        "file": relative,
                        "kind": "entry",
                        "entry": local_match.get("id"),
                        "title": local_match.get("title") or local_match.get("heading"),
                        "local_sha": entry_fingerprint(
                            local_match.get("heading", ""), local_match.get("body", "")
                        ),
                        "incoming_sha": entry_fingerprint(
                            entry.get("heading", ""), entry.get("body", "")
                        ),
                    },
                )

        if blocks:
            _backup_before_write(root, local_path)
            _append_blocks(local_path, blocks)
            changed = True

    # 2) cast / threads / private：缺的复制，冲突的保留本地并写外来版本。
    for relative in sorted(
        name
        for name in files
        if name.startswith(("cast/", "threads/", "private/")) and name.endswith(".md")
    ):
        data = files[relative]
        local_path = root / relative
        if not local_path.exists():
            _write_new_file(root, relative, data)
            added_files.append(relative)
            changed = True
            continue
        if local_path.read_bytes() == data:
            continue
        record_conflict(relative, data, {"file": relative, "kind": "file"})

    # 3) index.diary：本地已有就保留本地名字/开关，只补缺的册名。
    index_path = root / INDEX_NAME
    archive_index_raw = files[INDEX_NAME]
    try:
        archive_index = json.loads(_decode_bytes(archive_index_raw))
    except ValueError:
        return _archive_result(False, 1, "包内 index.diary 不是合法 JSON")
    if not isinstance(archive_index, dict):
        return _archive_result(False, 1, "包内 index.diary 必须是 JSON 对象")

    if local_index is None:
        _backup_before_write(root, index_path)
        index_path.write_bytes(archive_index_raw if archive_index_raw.endswith(b"\n") else archive_index_raw + b"\n")
        changed = True
    else:
        merged_index = dict(local_index)
        local_books = merged_index.get("books")
        if not isinstance(local_books, dict):
            local_books = {}
        archive_books = archive_index.get("books")
        if isinstance(archive_books, dict):
            for key, value in archive_books.items():
                if key not in local_books:
                    local_books[key] = value
        if local_books:
            merged_index["books"] = local_books
        if merged_index != local_index:
            _backup_before_write(root, index_path)
            write_json(index_path, merged_index)
            changed = True

    # 4) 指纹：包内涉及的条目按「本地现在的内容」重新登记基线。
    local_docs_now = _safe_parse_library(root)
    local_entries_now = iter_entries(local_docs_now)
    hashes = dict(local_hashes)
    old_hash_ids = set(local_hashes)
    hashes_changed = False
    for entry in local_entries_now:
        entry_id = entry.get("id")
        if (
            entry_id not in reconcile_ids
            and entry_id not in archive_ids
            and entry_id in old_hash_ids
        ):
            continue
        baseline = {
            "hash": entry_fingerprint(entry.get("heading", ""), entry.get("body", "")),
            "heading": entry.get("heading", ""),
            "body": entry.get("body", ""),
        }
        if hashes.get(entry_id) != baseline:
            hashes[entry_id] = baseline
            hashes_changed = True
    if hashes_changed:
        _backup_before_write(root, hashes_path(root))
        write_json(hashes_path(root), hashes)
        changed = True

    # 5) 审计：空库首次导入原样接上源审计；否则只记一条 import。
    audit_added = 0
    if empty_branch:
        source_audit = files.get(AUDIT_NAME, b"")
        audit_added = _append_raw_audit(root, source_audit)
        if audit_added:
            changed = True
    elif changed:
        try:
            append_audit(
                root,
                actor="human",
                action="import",
                target="*",
                entry=None,
                via="import",
                note=(
                    f"导入 {archive_path.name}：新增 {len(added_entries)} 条，"
                    f"冲突 {len(conflicts)} 条，文件 {len(added_files)} 个"
                ),
            )
            audit_added = 1
        except OSError as exc:
            return _archive_result(False, 1, f"写审计失败：{exc}")

    return _archive_result(
        True,
        0,
        "" if changed else "无变化（幂等）",
        added_entries=added_entries,
        added_files=added_files,
        conflicts=conflicts,
        conflict_dir=str(conflict_dir) if conflict_dir.exists() else "",
        audit_added=audit_added,
        changed=changed,
    )


__all__ = [
    "INDEX_NAME",
    "AUDIT_NAME",
    "STATE_DIR",
    "HASHES_NAME",
    "LAST_SEEN_NAME",
    "BACKUP_DIR",
    "ZERO_HASH",
    "now_iso",
    "sha256_text",
    "entry_fingerprint",
    "canonical_json",
    "read_json",
    "write_json",
    "read_jsonl",
    "append_jsonl",
    "load_index",
    "load_library_books",
    "library_mode",
    "library_sources",
    "set_library_mode",
    "iter_entries",
    "parse_library",
    "append_entry",
    "read_summary",
    "append_audit",
    "load_audit",
    "verify_audit",
    "load_hashes",
    "load_last_seen",
    "inspect_library",
    "heading_line_index",
    "parse_file",
    "delete_entry",
    "ARCHIVE_FORMAT_VERSION",
    "ARCHIVE_PROJECT",
    "MANIFEST_NAME",
    "CONFLICTS_DIR",
    "archive_entry_digest",
    "export_library",
    "import_library",
]
