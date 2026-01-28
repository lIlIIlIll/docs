#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import json
import re
import datetime


def log(msg: str) -> None:
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[example-fold {ts}] {msg}", file=sys.stderr, flush=True)


if len(sys.argv) >= 2 and sys.argv[1] == "supports":
    print("true")
    sys.exit(0)


EXAMPLE_RE = re.compile(r"^(?P<indent>\s*)(?P<head>示例|Example)\s*[:：]\s*(?P<rest>.*)$")
OUTPUT_RE = re.compile(r"^(?P<indent>\s*)(?P<head>运行结果|输出结果|输出|Output)\s*[:：]\s*$")
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+")
FENCE_RE = re.compile(r"^\s*(```+|~~~+)")


def convert_example_fold(text: str) -> str:
    lines = text.splitlines()
    out = []
    in_example = False
    in_fence = False
    fence_marker = None

    def open_example(summary: str, indent: str) -> None:
        out.append(f'{indent}<details class="example-fold">')
        out.append(f"{indent}<summary>{summary}</summary>")
        out.append(f'{indent}<div class="example-fold-body">')

    def close_example(indent: str) -> None:
        out.append(f"{indent}</div>")
        out.append(f"{indent}</details>")
        out.append("")
        return

    current_indent = ""

    for line in lines:
        fence_match = FENCE_RE.match(line)
        if fence_match:
            marker = fence_match.group(1)
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif fence_marker and line.strip().startswith(fence_marker):
                in_fence = False

        if not in_fence:
            example_match = EXAMPLE_RE.match(line)
            if example_match:
                if in_example:
                    close_example(current_indent)
                    in_example = False
                head = example_match.group("head")
                rest = (example_match.group("rest") or "").strip()
                summary = f"{head}：{rest}" if rest else head
                current_indent = example_match.group("indent") or ""
                open_example(summary, current_indent)
                in_example = True
                continue

            if in_example and HEADING_RE.match(line):
                close_example(current_indent)
                in_example = False
                out.append(line)
                continue

            if in_example:
                output_match = OUTPUT_RE.match(line)
                if output_match:
                    out.append(f'{output_match.group("indent") or ""}<div class="example-fold-output-label">{output_match.group("head")}</div>')
                    continue

        out.append(line)

    if in_example:
        close_example(current_indent)

    return "\n".join(out)


def walk_items(item):
    chapter = item.get("Chapter")
    if chapter:
        before = chapter.get("content", "")
        after = convert_example_fold(before)
        if before != after:
            log(f"converted in: {chapter.get('path') or chapter.get('name')}")
            chapter["content"] = after
        for sub in chapter.get("sub_items", []):
            walk_items(sub)


def main() -> None:
    data = json.load(sys.stdin)

    if isinstance(data, list) and len(data) == 2:
        _ctx, book = data
        out_book = book
    elif isinstance(data, dict) and "book" in data:
        out_book = data["book"]
    else:
        raise TypeError(f"unexpected stdin JSON shape: {type(data)}")

    def iter_sections(book_like):
        if isinstance(book_like, list):
            return book_like
        if isinstance(book_like, dict):
            if "items" in book_like:
                return book_like.get("items", [])
            return book_like.get("sections", [])
        return []

    for item in iter_sections(out_book):
        walk_items(item)

    json.dump(out_book, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
