#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, json, re, datetime, os


# -------- 日志到 stderr --------
def log(msg):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[table-joiner {ts}] {msg}", file=sys.stderr, flush=True)


# -------- supports 协议 --------
if len(sys.argv) >= 2 and sys.argv[1] == "supports":
    print("true")
    sys.exit(0)


# -------- Pipe 表识别 --------
# “看起来像表格行”：以 | 开头或结尾，并且含有 |
def looks_like_table_row(s: str) -> bool:
    t = s.strip()
    if not t or "|" not in t:
        return False
    return t.startswith("|") or t.endswith("|")


# 分隔行：| --- | :---: | ---- |
SEP_RE = re.compile(r"^\s*\|?\s*[:\-]+(?:\s*\|\s*[:\-]+)*\s*\|?\s*$")


def join_blank_lines_inside_tables(text: str) -> str:
    lines = text.splitlines()
    out = []
    i, n = 0, len(lines)

    def is_fence(line: str):
        m = re.match(r"^(\s*)(`{3,}|~{3,})", line)
        return m.group(2) if m else None

    in_fence = False
    fence = None

    while i < n:
        line = lines[i]
        # 保护代码围栏：不改代码块里的“表格示例”
        fm = is_fence(line)
        if fm:
            if not in_fence:
                in_fence, fence = True, fm
            elif fm == fence:
                in_fence, fence = False, None
            out.append(line)
            i += 1
            continue

        if in_fence:
            out.append(line)
            i += 1
            continue

        # 如果是“表格行/分隔行”，且下一行是空行、下下行仍是表格行/分隔行 → 吃掉中间空行
        if looks_like_table_row(line) or SEP_RE.match(line or ""):
            if i + 2 < n:
                nxt = lines[i + 1]
                nxt2 = lines[i + 2]
                if nxt.strip() == "" and (
                    looks_like_table_row(nxt2) or SEP_RE.match(nxt2 or "")
                ):
                    out.append(line)
                    i += 2  # 跳过中间空行
                    continue

        out.append(line)
        i += 1

    return "\n".join(out)


# -------- 递归处理章节 --------
def walk_items(item):
    # 只处理 dict；字符串/None 跳过
    if not isinstance(item, dict):
        return
    ch = item.get("Chapter")
    if ch and isinstance(ch, dict):
        before = ch.get("content", "")
        if before != after:
            log(f"joined table blank lines in: {ch.get('path') or ch.get('name')}")
            ch["content"] = after
        for sub in ch.get("sub_items", []):
            walk_items(sub)


def walk_items(item):
    # 变体解包：Chapter / Separator / PartTitle
    ch = item.get("Chapter")
    if ch:
        before = ch.get("content", "")
        after = join_blank_lines_inside_tables(before)
        if before != after:
            log(f"joined table blank lines in: {ch.get('path') or ch.get('name')}")
            ch["content"] = after
        for sub in ch.get("sub_items", []):
            walk_items(sub)


def main():
    data = json.load(sys.stdin)

    # 兼容两种输入形状
    if isinstance(data, list) and len(data) == 2:
        ctx, book = data
        # 对于这种输入，book 通常已经是一个数组（Vec<BookItem>）
        out_book = book
    elif isinstance(data, dict) and "book" in data:
        # 对这种输入，book 往往是个对象，里头有 "sections"
        book = data["book"]
        out_book = book.get("sections", book)
    else:
        raise TypeError(f"unexpected stdin JSON shape: {type(data)}")

    # 处理内容
    # 注意：如果 out_book 是对象，取 sections 递归；如果是数组，直接遍历
    def iter_sections(book_like):
        if isinstance(book_like, list):
            return book_like
        return book_like.get("sections", [])

    for it in iter_sections(book):
        walk_items(it)

    # —— 关键点：只输出 Book ——（在 0.4.52 下应为 JSON 数组）
    json.dump(out_book, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"ERROR: {e}")
        sys.exit(1)
