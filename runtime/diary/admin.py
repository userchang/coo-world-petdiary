#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""桌宠日记 P1 管理命令。

用法：
    python diary/admin.py init   --root <库目录> [--name 名字]
    python diary/admin.py append --root <库目录> --book daily --time 21:10 \
        --title "…" --body "…" [--kind 日常] [--private] [--json]
    python diary/admin.py read   --root <库目录> [--scope public|all] [--limit 5] [--json]
    python diary/admin.py mode   --root <库目录> --set dual|single [--json]
    python diary/admin.py log    --root <库目录> [--since 24h|7d|all]
    python diary/admin.py diff   --root <库目录> --entry <id>
    python diary/admin.py verify --root <库目录> [--json]
    python diary/admin.py delete --root <库目录> --entry <id> [--json]
    python diary/admin.py state  --root <库目录> [--json]
    python diary/admin.py export --root <库目录> --out <文件.diary> [--json]
    python diary/admin.py import --file <文件.diary> --root <库目录>

P4 的 append 是唯一写入入口；World 与前端都不拼 md。`--json` 只输出一行 JSON
（stdout），日志/人话走 stderr，方便 bridge 进程解析。

原则：
- 审计只追加，永不删改；`verify` 只报断链，不自动修。
- `append` 只往文件末尾追加，不覆盖已有正文。
- 只用标准库。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import store  # noqa: E402


def _emit_json(value: Any) -> None:
    """bridge 只认 stdout 的一行 JSON；任何多余日志都不许混进来。"""
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")), flush=True)


def _json_mode(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "json", False))


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    root = Path(args.root)
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"错误：建库目录失败：{exc}", file=sys.stderr)
        return 1

    index_path = root / store.INDEX_NAME
    index = store.load_index(root)
    created = index is None

    if created:
        books = store.load_library_books(root)  # 库还没建时回落到 diary/books.json
        index = {
            "version": 1,
            "name": args.name or root.name or "我的日记",
            "created_at": store.now_iso(),
            "mode": "single",
            "dual_diary": False,
            "books": books,
        }
        store.write_json(index_path, index)

    state_dir = root / store.STATE_DIR
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / store.BACKUP_DIR).mkdir(parents=True, exist_ok=True)

    audit = root / store.AUDIT_NAME
    if not audit.exists():
        with open(audit, "w", encoding="utf-8", newline="\n"):
            pass

    hashes = state_dir / store.HASHES_NAME
    if not hashes.exists():
        store.write_json(hashes, {})

    last_seen = state_dir / store.LAST_SEEN_NAME
    if not last_seen.exists():
        with open(last_seen, "w", encoding="utf-8", newline="\n"):
            pass

    if created:
        print(f"已建库：{root.resolve()}")
    else:
        print(f"库已存在，保留现有 index / 审计：{root.resolve()}")
    print(f"  身份：{index_path}")
    print(f"  审计：{audit}")
    print(f"  状态：{state_dir}")
    return 0


# ---------------------------------------------------------------------------
# 条目查找（diff 等只读命令共用）
# ---------------------------------------------------------------------------


def _find_entry(docs: list[dict[str, Any]], entry_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    for doc in docs:
        for entry in doc.get("entries", []):
            if entry.get("id") == entry_id:
                return doc, entry
    return None


# ---------------------------------------------------------------------------
# P4：append / read / mode / state
# ---------------------------------------------------------------------------


def cmd_append(args: argparse.Namespace) -> int:
    result = store.append_entry(
        Path(args.root),
        book=args.book,
        time=args.time,
        title=args.title,
        body=args.body,
        kind=args.kind,
        private=bool(args.private),
        actor="coo",
        via="tool",
        date_value=args.date,
    )
    if not result.get("ok"):
        if _json_mode(args):
            _emit_json(
                {
                    "ok": False,
                    "error": result.get("reason") or "append 失败",
                    "hint": result.get("hint") or "",
                    "code": int(result.get("code") or 1),
                }
            )
        else:
            print(f"错误：{result.get('reason') or 'append 失败'}", file=sys.stderr)
            if result.get("hint"):
                print(f"提示：{result['hint']}", file=sys.stderr)
        return int(result.get("code") or 1)

    if _json_mode(args):
        _emit_json(
            {
                "ok": True,
                "code": 0,
                "entry": result.get("entry"),
                "path": result.get("path"),
                "audit_seq": result.get("audit_seq"),
                "heading": result.get("heading"),
                "private": result.get("private", False),
            }
        )
        return 0
    print(f"已写入：{result.get('entry')}（{result.get('path')}）")
    print(f"  标题：{result.get('heading')}")
    print(f"  审计：seq={result.get('audit_seq')}")
    return 0


def cmd_read(args: argparse.Namespace) -> int:
    result = store.read_summary(
        Path(args.root),
        scope=args.scope,
        limit=args.limit,
        book=args.book,
    )
    if not result.get("ok"):
        if _json_mode(args):
            _emit_json(
                {
                    "ok": False,
                    "error": result.get("reason") or "read 失败",
                    "hint": "",
                    "code": int(result.get("code") or 1),
                }
            )
        else:
            print(f"错误：{result.get('reason') or 'read 失败'}", file=sys.stderr)
        return int(result.get("code") or 1)

    if _json_mode(args):
        _emit_json(result)
        return 0
    today = result.get("today") or {}
    print(f"今天：{today.get('count', 0)} 条（{today.get('date')}）")
    print(f"合计：{result.get('total', 0)} 条；范围：{result.get('scope')}")
    for entry in result.get("entries") or []:
        print(
            f"- {entry.get('date')} {entry.get('time') or '—'} "
            f"{entry.get('title')} [{entry.get('kind')}]"
        )
    return 0


def cmd_mode(args: argparse.Namespace) -> int:
    result = store.set_library_mode(Path(args.root), args.set)
    if _json_mode(args):
        _emit_json({**result, "ok": bool(result.get("ok"))})
    elif result.get("ok"):
        print(f"mode：{result.get('previous')} → {result.get('mode')}")
        if result.get("reason"):
            print(f"  {result['reason']}")
    else:
        print(f"错误：{result.get('reason') or '切换失败'}", file=sys.stderr)
    return int(result.get("code") or 0)


def cmd_state(args: argparse.Namespace) -> int:
    root = Path(args.root)
    try:
        # 复用三区页的 state 组装，避免面板与网页两套统计口径。
        from serve import build_state  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        if _json_mode(args):
            _emit_json({"ok": False, "error": f"载入 state 失败：{exc}", "hint": "", "code": 1})
        else:
            print(f"错误：载入 state 失败：{exc}", file=sys.stderr)
        return 1
    state = build_state(root, str(root))
    if _json_mode(args):
        _emit_json({"ok": True, "code": 0, "state": state})
        return 0
    print(f"库：{state['library']['name']}")
    print(f"条目：{state['counts']['total']}")
    print(
        f"mode：{state['library'].get('mode')}；"
        f"私密本：{int(state['counts'].get('private') or 0)} 条"
    )
    return 0


# ---------------------------------------------------------------------------
# log
# ---------------------------------------------------------------------------


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


def _window_label(since: str) -> str:
    return {"24h": "过去 24 小时", "7d": "过去 7 天", "all": "全部记录"}[since]


def cmd_log(args: argparse.Namespace) -> int:
    root = Path(args.root)
    records = store.load_audit(root)
    now = datetime.now().astimezone()

    if args.since == "all":
        selected = records
    else:
        delta = timedelta(hours=24) if args.since == "24h" else timedelta(days=7)
        cutoff = now - delta
        selected = []
        for record in records:
            timestamp = _parse_time(record.get("t"))
            if timestamp is not None and timestamp >= cutoff:
                selected.append(record)

    label = _window_label(args.since)
    if not selected:
        if args.since == "all":
            print("还没有任何记录。")
        else:
            print(f"{label}没人动过。")
        return 0

    reads = sum(1 for record in selected if record.get("action") == "read")
    external = [
        record
        for record in selected
        if record.get("action") == "edit" and record.get("actor") == "unknown"
    ]
    external_entries = {
        record.get("entry") or record.get("target") or "?" for record in external
    }

    parts: list[str] = []
    if reads:
        parts.append(f"有人读过 {reads} 次")
    if external:
        parts.append(f"改了 {len(external_entries)} 条（软件外）")
    if not parts:
        parts.append(f"有 {len(selected)} 条其它记录")

    print(f"{label}：" + "、".join(parts) + "。")
    return 0


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------


def cmd_diff(args: argparse.Namespace) -> int:
    root = Path(args.root)
    if not root.is_dir():
        print(f"错误：库目录不存在：{root}", file=sys.stderr)
        return 2

    docs = store.parse_library(root)
    found = _find_entry(docs, args.entry)
    if found is None:
        print(f"错误：找不到条目：{args.entry}", file=sys.stderr)
        return 2
    _, entry = found

    current_heading = entry.get("heading", "")
    current_body = entry.get("body", "")
    current_hash = store.entry_fingerprint(current_heading, current_body)

    hashes = store.load_hashes(root)
    baseline = hashes.get(args.entry)
    if baseline is not None and baseline.get("hash") == current_hash:
        print(f"没被改过：{args.entry}")
        return 0

    records = store.load_last_seen(root)
    latest = None
    for record in reversed(records):
        if record.get("entry") == args.entry:
            latest = record
            break

    if latest is not None:
        if (
            latest.get("now_heading") == current_heading
            and latest.get("now_body") == current_body
        ):
            old_heading = latest.get("old_heading")
            old_body = latest.get("old_body")
        elif latest.get("now_heading") is not None:
            old_heading = latest.get("now_heading")
            old_body = latest.get("now_body")
        else:
            old_heading = latest.get("old_heading")
            old_body = latest.get("old_body")
    elif baseline is not None:
        old_heading = baseline.get("heading")
        old_body = baseline.get("body")
    else:
        print(f"没被改过：{args.entry}（还没有登记过指纹）")
        return 0

    if old_heading == current_heading and old_body == current_body:
        print(f"没被改过：{args.entry}")
        return 0

    time_text = entry.get("time") or ""
    print(f"{time_text} 这条原话：" if time_text else f"{args.entry} 这条原话：")
    print(f"  标题：{old_heading if old_heading is not None else '（没有留下标题）'}")
    print(f"  正文：{old_body if old_body else '（空）'}")
    print("→ 现在：")
    print(f"  标题：{current_heading}")
    print(f"  正文：{current_body if current_body else '（空）'}")
    print("（改动来自软件外）")
    return 0


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------


def cmd_verify(args: argparse.Namespace) -> int:
    root = Path(args.root)
    if not root.is_dir():
        print(f"错误：库目录不存在：{root}", file=sys.stderr)
        return 1

    index = store.load_index(root)
    if index is None:
        print(f"提示：{root} 里没有 {store.INDEX_NAME}，仍按单日记目录检查。")

    result = store.inspect_library(root, record=True, register=True)
    issues: list[str] = []

    issues.extend(result["chain_issues"])
    for entry in result["changed"]:
        issues.append(f"⚠ {entry['id']} 被外部修改（哈希不匹配）")
    for item in result["missing"]:
        issues.append(f"⚠ {item['entry']} 条目消失")

    audit_count = result["audit_count"]
    fingerprint_count = len(result["hashes"])
    new_count = len(result["new_ids"])

    if _json_mode(args):
        _emit_json(
            {
                "ok": not issues,
                "code": 0 if not issues else 1,
                "issues": issues,
                "audit_count": audit_count,
                "fingerprint_count": fingerprint_count,
                "new_count": new_count,
                "summary": (
                    f"正常 {audit_count} 条审计 / {fingerprint_count} 条指纹"
                    if not issues
                    else f"发现 {len(issues)} 个问题"
                ),
            }
        )
        return 0 if not issues else 1

    if issues:
        print(
            f"verify：发现 {len(issues)} 个问题"
            f"（审计链 {audit_count} 条；指纹 {fingerprint_count} 条）"
        )
        for issue in issues:
            print(f"- {issue}")
        return 1

    extra = f"，新增登记 {new_count} 条" if new_count else ""
    print(
        f"verify：正常（审计链 {audit_count} 条；"
        f"指纹 {fingerprint_count} 条{extra}）"
    )
    return 0


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


def cmd_delete(args: argparse.Namespace) -> int:
    result = store.delete_entry(
        Path(args.root),
        args.entry,
        actor="human",
        via="cli",
    )
    if _json_mode(args):
        payload: dict[str, Any] = {
            "ok": bool(result.get("ok")),
            "code": int(result.get("code") or (0 if result.get("ok") else 1)),
            "entry": result.get("entry"),
            "mode": result.get("mode"),
            "path": result.get("path"),
            "heading": result.get("heading"),
            "audit_seq": result.get("audit_seq"),
            "hash_removed": bool(result.get("hash_removed")),
            "last_seen_added": bool(result.get("last_seen_added")),
            "backup": result.get("backup"),
        }
        if not result.get("ok"):
            payload["error"] = result.get("reason") or "删除失败"
            payload["hint"] = ""
        _emit_json(payload)
        return int(payload["code"])

    if not result.get("ok"):
        print(f"错误：{result.get('reason') or '删除失败'}", file=sys.stderr)
        return int(result.get("code") or 1)

    if result.get("mode") == "baseline":
        print(f"已清理基线残留：{result.get('entry')}")
        print("  md 里本来就没有这条，只移除残留指纹并留删除审计。")
    else:
        print(f"已删除：{result.get('entry')}（{result.get('heading') or '无标题'}）")
        print(f"  文件：{result.get('path')}")
    print(
        "  指纹：已移除" if result.get("hash_removed") else "  指纹：本来就不在基线里"
    )
    print(f"  审计：seq={result.get('audit_seq')}（action=delete）")
    return 0


# ---------------------------------------------------------------------------
# export / import（.diary 单文件容器）
# ---------------------------------------------------------------------------


def cmd_export(args: argparse.Namespace) -> int:
    result = store.export_library(Path(args.root), Path(args.out))
    if not result.get("ok"):
        if _json_mode(args):
            _emit_json(
                {
                    "ok": False,
                    "error": result.get("reason") or "导出失败",
                    "hint": "",
                    "code": int(result.get("code") or 1),
                }
            )
        else:
            print(f"错误：{result.get('reason') or '导出失败'}", file=sys.stderr)
        return int(result.get("code") or 1)

    if _json_mode(args):
        _emit_json({**result, "ok": True, "code": 0})
        return 0

    print(f"已导出：{result['out']}")
    print(f"  条目：{result['entry_count']}；内容文件：{result['file_count']}")
    print(f"  entry_digest：{result['entry_digest']}")
    print(f"  chain_head：{result['chain_head']}")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    result = store.import_library(Path(args.root), Path(args.file))
    if not result.get("ok"):
        print(f"错误：{result.get('reason') or '导入失败'}", file=sys.stderr)
        return int(result.get("code") or 1)

    print(f"导入完成：{args.file} → {args.root}")
    if result.get("reason"):
        print(f"  {result['reason']}")
    print(
        f"  新增条目：{len(result.get('added_entries') or [])}；"
        f"新增文件：{len(result.get('added_files') or [])}；"
        f"审计新增：{int(result.get('audit_added') or 0)}"
    )
    conflicts = result.get("conflicts") or []
    if conflicts:
        print(f"  冲突：{len(conflicts)}（本地保留，外来版本已存档）")
        for item in conflicts:
            if item.get("kind") == "entry":
                label = f"{item.get('entry')}（{item.get('title') or '无标题'}）"
            else:
                label = item.get("file") or "?"
            suffix = "" if item.get("new_file") else "（此前已存档）"
            print(f"    - {label} → {item.get('conflict_file')}{suffix}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="桌宠日记 P1 管理命令（库 / 审计 / 防篡改，仅标准库）。"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="建库：index.diary / audit.log.jsonl / state/")
    init_parser.add_argument("--root", default=".", help="库目录（默认当前目录）")
    init_parser.add_argument("--name", help="库名字")
    init_parser.set_defaults(func=cmd_init)

    append_parser = subparsers.add_parser("append", help="唯一写入入口：追加一条日记")
    append_parser.add_argument("--root", required=True, help="库目录")
    append_parser.add_argument("--book", required=True, help="短册名，例如 daily")
    append_parser.add_argument("--time", required=True, help="HH:MM")
    append_parser.add_argument("--title", required=True, help="条目标题")
    append_parser.add_argument("--body", required=True, help="正文")
    append_parser.add_argument("--kind", help="分类：" + " / ".join(store.KINDS[:-1]) + "（不写算未分类）")
    append_parser.add_argument("--private", action="store_true", help="写 private/（私密本）")
    append_parser.add_argument("--date", help="覆盖日期（默认今天，测试用）")
    append_parser.add_argument("--json", action="store_true", help="只输出一行 JSON")
    append_parser.set_defaults(func=cmd_append)

    read_parser = subparsers.add_parser("read", help="只读摘要：最近条目 / 今天 / 各册计数")
    read_parser.add_argument("--root", required=True, help="库目录")
    read_parser.add_argument("--scope", default="public", choices=["public", "all"])
    read_parser.add_argument("--limit", type=int, default=5)
    read_parser.add_argument("--book", help="只看某一册")
    read_parser.add_argument("--json", action="store_true")
    read_parser.set_defaults(func=cmd_read)

    mode_parser = subparsers.add_parser("mode", help="只改 index.diary 的册形态（不搬文件）")
    mode_parser.add_argument("--root", required=True, help="库目录")
    mode_parser.add_argument("--set", required=True, choices=["dual", "single"])
    mode_parser.add_argument("--json", action="store_true")
    mode_parser.set_defaults(func=cmd_mode)

    state_parser = subparsers.add_parser("state", help="输出三区页同口径的 state JSON")
    state_parser.add_argument("--root", required=True, help="库目录")
    state_parser.add_argument("--json", action="store_true")
    state_parser.set_defaults(func=cmd_state)

    log_parser = subparsers.add_parser("log", help="人话摘要：谁动过、改了几条")
    log_parser.add_argument("--root", default=".", help="库目录")
    log_parser.add_argument("--since", default="24h", choices=["24h", "7d", "all"], help="时间窗口")
    log_parser.set_defaults(func=cmd_log)

    diff_parser = subparsers.add_parser("diff", help="看某条「上次看到的样子 / 现在」")
    diff_parser.add_argument("--root", default=".", help="库目录")
    diff_parser.add_argument("--entry", required=True, help="条目 id")
    diff_parser.set_defaults(func=cmd_diff)

    verify_parser = subparsers.add_parser("verify", help="校验审计链 + 条目指纹（只报不修）")
    verify_parser.add_argument("--root", default=".", help="库目录")
    verify_parser.add_argument("--json", action="store_true")
    verify_parser.set_defaults(func=cmd_verify)

    delete_parser = subparsers.add_parser(
        "delete", help="删除一条日记（整段移除 + 清指纹 + delete 审计）"
    )
    delete_parser.add_argument("--root", default=".", help="库目录")
    delete_parser.add_argument("--entry", required=True, help="条目 id")
    delete_parser.add_argument("--json", action="store_true")
    delete_parser.set_defaults(func=cmd_delete)

    export_parser = subparsers.add_parser("export", help="把库导出为单文件 .diary（zip）")
    export_parser.add_argument("--root", required=True, help="库目录")
    export_parser.add_argument("--out", required=True, help="输出文件，例如 日记.diary")
    export_parser.add_argument("--json", action="store_true")
    export_parser.set_defaults(func=cmd_export)

    import_parser = subparsers.add_parser("import", help="校验并导入单文件 .diary")
    import_parser.add_argument("--file", required=True, dest="file", help="要导入的 .diary")
    import_parser.add_argument("--root", required=True, help="目标库目录")
    import_parser.set_defaults(func=cmd_import)

    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
        sys.stderr.reconfigure(encoding="utf-8", newline="\n")
    except (AttributeError, OSError):
        pass

    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
