#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import json
import re

FENCE_RE = re.compile(r"^\s*(```+|~~~+)")
DEPRECATED_SUP_RE = re.compile(r"<sup>\s*\\?(\\()?deprecated\\?(\\)?\s*</sup>", re.IGNORECASE)
PLACEHOLDER_TAG_RE = re.compile(
    r"<(/?)(elementtype|v|r|t|tret|signal|string|object|argumentmatcher|uint8)>",
    re.IGNORECASE,
)
INLINE_GENERIC_RE = re.compile(r"(?P<prefix>[\w\]\)\.>])<(?P<tag>[A-Za-z][A-Za-z0-9_]*)>")
DIGIT_TAG_RE = re.compile(r"<(/?)([A-Za-z_]*\d+[A-Za-z0-9_]*)>")


def escape_placeholders(text: str) -> str:
    lines = text.splitlines()
    out = []
    in_fence = False
    fence_marker = None

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
            line = DEPRECATED_SUP_RE.sub(r'<span class="deprecated-sup">(deprecated)</span>', line)
            line = PLACEHOLDER_TAG_RE.sub(r"&lt;\1\2&gt;", line)
            line = INLINE_GENERIC_RE.sub(r"\g<prefix>&lt;\g<tag>&gt;", line)
            line = DIGIT_TAG_RE.sub(r"&lt;\1\2&gt;", line)

        out.append(line)

    return "\n".join(out)


def walk_items(item):
    chapter = item.get("Chapter")
    if chapter:
        before = chapter.get("content", "")
        after = escape_placeholders(before)
        if before != after:
            chapter["content"] = after
        for sub in chapter.get("sub_items", []):
            walk_items(sub)


def main() -> None:
    if len(sys.argv) >= 2 and sys.argv[1] == "supports":
        print("true")
        return

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
