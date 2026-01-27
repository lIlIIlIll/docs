#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, json, re, datetime


def log(msg):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[bq→admonition {ts}] {msg}", file=sys.stderr, flush=True)


# --- supports 协议 ---
if len(sys.argv) >= 2 and sys.argv[1] == "supports":
    print("true")
    sys.exit(0)

HEADER_RE = re.compile(
    r"^\s*>\s*\*\*(?P<head>[^*:：]+)\s*[:：]\s*\*\*\s*(?P<rest>.*)$"
)
MAP = {
    "注意": "CAUTION",
    "警告": "WARNING",
    "警示": "WARNING",
    "提示": "TIP",
    "信息": "NOTE",
    "Note": "NOTE",
    "Notes": "NOTE",
    "说明": "NOTE",
    "Explanation": "NOTE",
    "注": "NOTE",
    "引用": "NOTE",
    "成功": "TIP",
    "通过": "TIP",
    "例子": "NOTE",
    "示例": "NOTE",
    "例": "NOTE",
    "Example": "NOTE",
    "Warning": "WARNING",
    "Caution": "CAUTION",
    "Important": "IMPORTANT",
    "Tip": "TIP",
    "失败": "WARNING",
    "错误": "WARNING",
    "危险": "WARNING",
    "Error": "WARNING",
    "Danger": "WARNING",
}


def convert_blockquote_to_admonition(text: str) -> str:
    lines = text.splitlines()
    out, i, n = [], 0, len(lines)

    def is_bq(line: str) -> bool:
        # 允许前置空格后再出现 '>'（常见于缩进场景）
        s = line.lstrip()
        return s.startswith(">")

    while i < n:
        m = HEADER_RE.match(lines[i].lstrip())
        if not m:
            out.append(lines[i])
            i += 1
            continue

        head = m.group("head").strip()
        kind = MAP.get(head, "NOTE")
        rest = (m.group("rest") or "").strip()
        if rest.startswith(">"):
            rest = rest[1:]
            if rest.startswith(" "):
                rest = rest[1:]

        # 收集连续的 blockquote 行（只接受以 '>' 开头的行）
        i += 1
        body = []
        if rest:
            body.append(rest)
        while i < n and is_bq(lines[i]):
            s = lines[i].lstrip()[1:]  # 去掉 '>'
            if s.startswith(" "):
                s = s[1:]  # 去掉紧随其后的一个空格（若有）
            body.append(s)
            i += 1

        # 在生成的 admonition blockquote 前后 放一行空行，确保与后续内容分离
        if out and out[-1] != "":
            out.append("")  # 与前文隔开一行（更保险）
        out.append(f"> [!{kind}]")
        for line in body:
            if line == "":
                out.append(">")
            else:
                out.append(f"> {line}")
        out.append("")  # 与后文隔开一行（关键：避免“黏连”）

    return "\n".join(out)


def walk_items(item):
    # 变体解包：Chapter / Separator / PartTitle
    ch = item.get("Chapter")
    if ch:
        before = ch.get("content", "")
        after = convert_blockquote_to_admonition(before)
        if before != after:
            log(f"converted in: {ch.get('path') or ch.get('name')}")
            ch["content"] = after
        for sub in ch.get("sub_items", []):
            walk_items(sub)
    # 其他变体无需处理


def main():
    data = json.load(sys.stdin)

    # 兼容两种输入形状
    if isinstance(data, list) and len(data) == 2:
        ctx, book = data
        out_book = book
    elif isinstance(data, dict) and "book" in data:
        # 对这种输入，book 往往是个对象，里头有 "sections"
        book = data["book"]
        out_book = book
    else:
        raise TypeError(f"unexpected stdin JSON shape: {type(data)}")

    # 处理内容
    # 注意：如果 out_book 是对象，取 sections 递归；如果是数组，直接遍历
    def iter_sections(book_like):
        if isinstance(book_like, list):
            return book_like
        if isinstance(book_like, dict):
            if "items" in book_like:
                return book_like.get("items", [])
            return book_like.get("sections", [])
        return []

    for it in iter_sections(book):
        walk_items(it)

    # —— 关键点：输出 Book 结构 ——（保持输入结构：list/dict）
    json.dump(out_book, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"ERROR: {e}")
        # 非 0 退出会让 mdBook 中止；这里保留，让你能第一时间看到问题
        sys.exit(1)
