#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit


SEARCHINDEX_PATTERN = re.compile(
    r"JSON\.parse\((?P<payload>'(?:\\.|[^'])*')\)\)\s*;?\s*$",
    re.DOTALL,
)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
LABEL_RE = re.compile(r"^(功能|参数|返回值|示例|运行结果|类型|父类型|异常|自\s*[0-9.]+\s*版本开始支持|Since|Deprecated|说明|描述)：?\s*(.*)$")
TOP_LEVEL_KIND_RE = re.compile(r"^(class|struct|interface|enum|func|macro|const|var|typealias|type)\s+(.+)$", re.IGNORECASE)
MEMBER_KIND_RE = re.compile(r"^(?:(static)\s+)?(prop|let|func|init|operator)\b\s*(.*)$", re.IGNORECASE)
MACRO_TITLE_RE = re.compile(r"^`?(?P<name>@[A-Za-z_][\w]*)`?\s*(?:宏|Macro)$")
EXTEND_RE = re.compile(
    r"^extend(?:<[^>]+>)?\s+(?P<target>.+?)(?:\s*<:\s*(?P<iface>.+))?$",
    re.IGNORECASE,
)
SAMPLE_TITLE_RE = re.compile(r"^(?P<container>[A-Za-z_][\w]*)\s*的\s*(?P<members>.+?)\s*函数$")
LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
DEPRECATED_RE = re.compile(r"\(deprecated\)|已废弃|弃用|废弃", re.IGNORECASE)
IDENT_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
DOCS_SITE_PREFIX = {
    "std": "https://955work.icu/dev/std",
    "stdx": "https://955work.icu/dev/stdx",
}


@dataclass
class Heading:
    level: int
    text: str
    content: list[str]


@dataclass
class ApiSymbol:
    id: str
    fqname: str
    kind: str
    package: str
    module: str
    container: str | None
    display: str
    qualified_title: str
    page_title: str
    page_title_html: str
    signature: str | None
    summary_short_md: str | None
    summary_md: str | None
    details_md: str | None
    notes_md: str | None
    exceptions_md: str | None
    see_also_md: str | None
    params: list[dict]
    returns_md: str | None
    examples_md: list[str]
    page_url: str
    anchor: str | None
    related_links: list[dict] = field(default_factory=list)
    since: str | None = None
    deprecated: dict | None = None
    aliases: list[str] = field(default_factory=list)
    search_keys_normalized: list[str] = field(default_factory=list)
    example_titles: list[str] = field(default_factory=list)
    example_snippets_short: list[str] = field(default_factory=list)
    signature_short: str | None = None
    callable: dict | None = None
    type_info: dict | None = None
    value_info: dict | None = None
    availability: dict | None = None
    extension_info: dict | None = None
    parent_types: list[str] = field(default_factory=list)


def clean_text(text: str) -> str:
    text = text or ""
    text = text.replace("\xa0", " ")
    text = text.replace("\\<", "<").replace("\\>", ">")
    text = LINK_RE.sub(r"\1", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_markdown(text: str) -> str | None:
    text = text.strip()
    if not text:
        return None
    text = re.sub(r"<!--\s*verify\s*-->\s*", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() or None


def strip_inline_html(text: str) -> str:
    return re.sub(r"</?[a-z][^>]*>", "", text or "")


def split_platform_list(text: str) -> list[str]:
    return [clean_text(x) for x in re.split(r"[、,，]", text) if clean_text(x)]


def absolutize_markdown_links(text: str | None, page_url: str) -> str | None:
    if not text:
        return text

    def normalize_target(target: str) -> str:
        return normalize_doc_target(target, page_url)

    def repl(match: re.Match[str]) -> str:
        label = match.group(1)
        target = match.group(2).strip()
        if not target:
            return match.group(0)
        return f"[{label}]({normalize_target(target)})"

    return MARKDOWN_LINK_RE.sub(repl, text)


def normalize_doc_target(target: str, page_url: str) -> str:
    if target.startswith(("http://", "https://", "mailto:")):
        return target
    parts = urlsplit(target)
    path = parts.path
    if path.endswith(".md"):
        path = path[:-3] + ".html"
    normalized = urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))
    return urljoin(page_url, normalized)


def extract_markdown_links(text: str | None, page_url: str) -> list[dict]:
    if not text:
        return []
    links: list[dict] = []
    for match in MARKDOWN_LINK_RE.finditer(text):
        label = clean_text(match.group(1))
        target = match.group(2).strip()
        if not label or not target:
            continue
        links.append({"title": label, "url": normalize_doc_target(target, page_url)})
    return links


def extract_blockquote_admonitions(lines: list[str]) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    for raw_line in lines:
        stripped = raw_line.strip()
        if stripped.startswith(">"):
            current.append(re.sub(r"^>\s?", "", stripped))
            continue
        if current:
            text = normalize_markdown("\n".join(current))
            if text:
                blocks.append(text)
            current = []
    if current:
        text = normalize_markdown("\n".join(current))
        if text:
            blocks.append(text)
    return blocks


def first_sentence(text: str | None) -> str | None:
    if not text:
        return None
    for part in re.split(r"(?<=[。！？.!?])\s+", text.strip()):
        part = part.strip()
        if part:
            return part
    return text.strip() or None


def summarize_markdown(text: str | None, max_len: int = 120) -> str | None:
    if not text:
        return None
    text = normalize_markdown(text)
    if not text:
        return None
    paragraph = text.split("\n\n", 1)[0].strip()
    sentence = first_sentence(paragraph) or paragraph
    plain = clean_text(strip_inline_html(LINK_RE.sub(r"\1", sentence)))
    if len(plain) <= max_len:
        return sentence
    truncated = plain[: max_len - 1].rstrip()
    return truncated + "…"


def extract_replacement_fqname(text: str | None) -> str | None:
    if not text:
        return None
    match = re.search(r"\[([A-Za-z_][\w]*)\]\([^)]+\)", text)
    if match:
        return match.group(1)
    match = re.search(r"\b([A-Za-z_][\w]*)\b", text)
    return match.group(1) if match else None


def build_deprecated_info(
    module: str,
    page_url: str,
    heading_text: str,
    deprecated_lines: list[str],
    all_lines: list[str],
) -> dict | None:
    message_md = normalize_markdown("\n".join(deprecated_lines))
    replacement = extract_replacement_fqname(message_md)
    if not message_md:
        for idx, line in enumerate(all_lines):
            if not DEPRECATED_RE.search(line or ""):
                continue
            start = idx
            end = idx + 1
            while start > 0 and all_lines[start - 1].strip().startswith(">"):
                start -= 1
            while end < len(all_lines) and all_lines[end].strip().startswith(">"):
                end += 1
            candidate = normalize_markdown("\n".join(all_lines[start:end]))
            if candidate:
                message_md = candidate
                replacement = extract_replacement_fqname(message_md)
                break
    if message_md:
        message_md = re.sub(r"^>\s?", "", message_md, flags=re.MULTILINE)
        message_md = re.sub(r"^\*\*注意：\*\*\s*\n?", "", message_md, flags=re.MULTILINE)
        message_md = normalize_markdown(message_md)
    if replacement and "." not in replacement and module:
        replacement = f"{module}.{replacement}"
    is_deprecated = bool(DEPRECATED_RE.search(heading_text or "")) or bool(message_md)
    if not is_deprecated:
        return None
    return {
        "is_deprecated": True,
        "message_md": message_md,
        "since": None,
        "replacement_fqname": replacement,
        "replacement_url": None if not replacement else page_url,
    }


def slugify_heading(text: str) -> str:
    text = strip_inline_html(clean_text(text))
    text = re.sub(r"\(\s*deprecated\s*\)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b已废弃\b|\b弃用\b|\b废弃\b", "", text, flags=re.IGNORECASE)
    text = text.lower()
    text = text.replace("`", "")
    text = text.replace("<", "").replace(">", "")
    text = re.sub(r"[()]", "", text)
    text = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "-", text)
    return text.strip("-")


def load_searchindex_name(site_root: Path) -> str:
    candidates = sorted(site_root.glob("searchindex-*.js"))
    if not candidates:
        raise FileNotFoundError(f"no searchindex-*.js found in {site_root}")
    if len(candidates) > 1:
        raise RuntimeError(
            f"multiple searchindex files found in {site_root}: "
            + ", ".join(path.name for path in candidates)
        )
    raw = candidates[0].read_text(encoding="utf-8")
    if not SEARCHINDEX_PATTERN.search(raw):
        raise ValueError(f"unsupported search index format: {candidates[0]}")
    return candidates[0].name


def parse_book_src(book_dir: Path) -> Path:
    book_toml = book_dir / "book.toml"
    if not book_toml.is_file():
        return book_dir / "src"
    text = book_toml.read_text(encoding="utf-8")
    match = re.search(r'^\s*src\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        return book_dir / "src"
    return (book_dir / match.group(1)).resolve()


def iter_markdown_files(src_root: Path) -> list[Path]:
    return sorted(path for path in src_root.rglob("*.md") if path.name != "SUMMARY.md")


def split_module_parts(rel_path: Path, default_package: str | None = None) -> tuple[str, str]:
    parts = list(rel_path.parts)
    if not parts:
        return "", ""
    stdx_wrappers = {"libs_stdx", "libs_stdx_en"}
    if parts[0] in DOCS_SITE_PREFIX:
        package = parts[0]
        module_seed = parts[:-1]
    elif default_package:
        wrapper = parts[0]
        if wrapper.endswith("_en"):
            package = f"{default_package}_en"
        else:
            package = default_package
        tail_parts = parts[1:-1] if wrapper in stdx_wrappers else parts[:-1]
        module_seed = [package, *tail_parts]
    else:
        package = parts[0]
        module_seed = parts[:-1]
    module_parts = [part for part in module_seed if "_package_" not in part and "_samples" not in part]
    if not module_parts:
        module_parts = [package]
    return package, ".".join(module_parts)


def infer_default_package(book_dir: Path, site_root: Path, src_root: Path) -> str | None:
    top_dirs = {path.name for path in src_root.iterdir() if path.is_dir()} if src_root.is_dir() else set()
    if top_dirs & set(DOCS_SITE_PREFIX):
        return None
    hints = " ".join((str(book_dir), str(site_root), str(src_root))).lower()
    if "stdx" in hints:
        return "stdx"
    if re.search(r"(^|[^a-z])std([^a-z]|$)", hints):
        return "std"
    return None


def include_package(package: str) -> bool:
    return package in DOCS_SITE_PREFIX


def md_to_doc_url(
    src_root: Path,
    md_path: Path,
    anchor: str | None = None,
    default_package: str | None = None,
) -> str:
    rel = md_path.relative_to(src_root)
    if rel.parts and rel.parts[0] in DOCS_SITE_PREFIX:
        package = rel.parts[0]
    else:
        package = default_package or (rel.parts[0] if rel.parts else "")
    base = DOCS_SITE_PREFIX.get(package, "")
    path = "/" + rel.with_suffix(".html").as_posix()
    url = f"{base}{path}" if base else path
    if anchor:
        return f"{url}#{anchor}"
    return url


def parse_headings(lines: list[str]) -> tuple[str, list[Heading]]:
    title = ""
    indices: list[tuple[int, int, str]] = []
    for idx, line in enumerate(lines):
        match = HEADING_RE.match(line.strip())
        if not match:
            continue
        level = len(match.group(1))
        text = clean_text(match.group(2))
        if level == 1 and not title:
            title = text
        indices.append((idx, level, text))

    headings: list[Heading] = []
    for pos, (idx, level, text) in enumerate(indices):
        next_idx = indices[pos + 1][0] if pos + 1 < len(indices) else len(lines)
        content = lines[idx + 1 : next_idx]
        headings.append(Heading(level=level, text=text, content=content))
    return title, headings


def is_builtin_page_title(title: str) -> bool:
    plain = clean_text(strip_inline_html(title))
    return plain in {"内置类型", "Builtin Types"}


def extract_code_blocks(lines: list[str]) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    in_code = False
    lang = ""
    current: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code:
                blocks.append((lang, "\n".join(current).rstrip()))
                in_code = False
                lang = ""
                current = []
            else:
                in_code = True
                lang = stripped[3:].strip()
            continue
        if in_code:
            current.append(line.rstrip("\n"))
    return blocks


def split_labeled_sections(lines: list[str]) -> tuple[list[str], dict[str, list[str]]]:
    unlabeled: list[str] = []
    sections: dict[str, list[str]] = {}
    current_label: str | None = None
    for raw_line in lines:
        line = raw_line.rstrip("\n")
        match = LABEL_RE.match(line.strip())
        if match:
            current_label = clean_text(match.group(1))
            sections.setdefault(current_label, [])
            rest = match.group(2).strip()
            if rest:
                sections[current_label].append(rest)
            continue
        if current_label is None:
            unlabeled.append(line)
        else:
            sections[current_label].append(line)
    return unlabeled, sections


def first_nonempty_paragraph(lines: list[str]) -> str | None:
    paragraphs: list[str] = []
    current: list[str] = []
    in_code = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if not stripped:
            if current:
                paragraphs.append(clean_text(" ".join(current)))
                current = []
            continue
        if stripped.startswith("<!--"):
            continue
        current.append(stripped)
    if current:
        paragraphs.append(clean_text(" ".join(current)))
    for paragraph in paragraphs:
        if paragraph:
            return paragraph
    return None


def clean_label_block(lines: list[str]) -> list[str]:
    return [line for line in lines if line.strip() and not line.strip().startswith("<!--")]


def extract_prose_markdown(lines: list[str]) -> str | None:
    chunks: list[str] = []
    current: list[str] = []
    for raw_line in lines:
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            if current:
                last = current[-1].strip()
                if re.search(r"(?:例如|举例来说|如|如下|下面).*[：:]$", last):
                    current.pop()
            if current:
                chunks.append("\n".join(current))
                current = []
            break
        if stripped.startswith("<!--"):
            continue
        if stripped in {"例如：", "举例来说：", "如：", "如下："}:
            if current:
                chunks.append("\n".join(current))
            break
        if not stripped:
            if current:
                chunks.append("\n".join(current))
                current = []
            continue
        if stripped.startswith(">"):
            if current:
                chunks.append("\n".join(current))
                current = []
            chunks.append(stripped)
            continue
        if stripped.startswith("- "):
            if current and not current[-1].startswith("- "):
                chunks.append("\n".join(current))
                current = []
            current.append(stripped)
            continue
        if current and current[-1].startswith("- "):
            chunks.append("\n".join(current))
            current = []
        current.append(stripped)
    if current:
        chunks.append("\n".join(current))

    normalized_chunks: list[str] = []
    for chunk in chunks:
        lines_out: list[str] = []
        for line in chunk.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(("- ", ">")):
                lines_out.append(stripped)
            else:
                lines_out.append(clean_text(stripped))
        text = "\n".join(lines_out).strip()
        if text:
            normalized_chunks.append(text)
    if normalized_chunks and re.search(r"(?:例如|举例来说|如|如下|下面).*[：:]$", normalized_chunks[-1]):
        normalized_chunks.pop()
    return normalize_markdown("\n\n".join(normalized_chunks))


def split_bullet(line: str) -> str:
    stripped = line.strip()
    return stripped[1:].strip() if stripped.startswith("-") else stripped


def parse_params(lines: list[str]) -> list[dict]:
    params: list[dict] = []
    for raw_line in clean_label_block(lines):
        if not raw_line.strip().startswith("-"):
            continue
        text = split_bullet(raw_line)
        match = re.match(r"(?P<label>[^:]+):\s*(?P<type>.+?)(?:\s+-\s+(?P<doc>.+))?$", text)
        if not match:
            continue
        params.append(
            {
                "label": clean_text(match.group("label")),
                "type": clean_text(match.group("type")) or None,
                "doc_md": normalize_markdown(match.group("doc") or ""),
            }
        )
    return params


def parse_returns(lines: list[str]) -> str | None:
    items: list[str] = []
    for raw_line in clean_label_block(lines):
        text = split_bullet(raw_line)
        if " - " in text:
            text = text.split(" - ", 1)[1]
        items.append(text)
    return normalize_markdown("\n".join(items))


def parse_throws(lines: list[str]) -> list[dict]:
    throws: list[dict] = []
    for raw_line in clean_label_block(lines):
        if not raw_line.strip().startswith("-"):
            continue
        text = split_bullet(raw_line)
        exc_type = text
        doc_md = None
        if " - " in text:
            exc_type, doc_md = text.split(" - ", 1)
        exc_type = clean_text(exc_type)
        doc_md = normalize_markdown(doc_md or "")
        throws.append({"type": exc_type, "doc_md": doc_md})
    return throws


def parse_availability(lines: list[str]) -> dict | None:
    supported = None
    unsupported = None
    for raw_line in lines:
        line = strip_inline_html(raw_line).strip()
        line = re.sub(r"^[>\-\s]+", "", line)
        if not line:
            continue
        if line.startswith("不支持平台"):
            _, _, rest = line.partition("：")
            if not rest:
                _, _, rest = line.partition(":")
            unsupported = split_platform_list(rest.strip().rstrip("。"))
            continue
        if line.startswith("支持平台"):
            _, _, rest = line.partition("：")
            if not rest:
                _, _, rest = line.partition(":")
            supported = split_platform_list(rest.strip().rstrip("。"))
    if supported is None and unsupported is None:
        return None
    return {"supported_platforms": supported, "unsupported_platforms": unsupported}


def strip_structured_notes(text: str | None, *, deprecated_message: str | None, availability: dict | None) -> str | None:
    if not text:
        return None
    cleaned = text
    if deprecated_message:
        cleaned = cleaned.replace(deprecated_message, "")
        deprecated_plain = strip_inline_html(LINK_RE.sub(r"\1", deprecated_message))
        cleaned = cleaned.replace(deprecated_plain, "")
        lines = []
        for raw_line in cleaned.splitlines():
            plain = strip_inline_html(raw_line).strip().lstrip("> ").strip()
            if DEPRECATED_RE.search(plain) and ("代替" in plain or "替代" in plain):
                continue
            lines.append(raw_line)
        cleaned = "\n".join(lines)
    if availability:
        lines: list[str] = []
        skip_blank_after_notice = False
        for raw_line in cleaned.splitlines():
            plain = strip_inline_html(raw_line).strip()
            if plain in {"**注意：**", "注意："}:
                skip_blank_after_notice = True
                continue
            if "支持平台" in plain:
                skip_blank_after_notice = False
                continue
            if skip_blank_after_notice and not plain:
                continue
            skip_blank_after_notice = False
            lines.append(raw_line)
        cleaned = "\n".join(lines)
    cleaned = re.sub(r"(^|\n)>\s*$", r"\1", cleaned, flags=re.MULTILINE)
    cleaned = cleaned.replace("> **注意：**", "").replace("**注意：**", "")
    cleaned = re.sub(r"[，,]?\s*(?:例如|举例来说|如|如下)[:：]\s*$", "", cleaned)
    return normalize_markdown(cleaned)


def parse_examples(lines: list[str]) -> list[str]:
    examples: list[str] = []
    for lang, code in extract_code_blocks(lines):
        if not code:
            continue
        fence = f"```{lang}".rstrip()
        examples.append(f"{fence}\n{code}\n```")
    return examples


def build_example_snippets_short(examples: list[str]) -> list[str]:
    snippets: list[str] = []
    for example in examples:
        lines = example.splitlines()
        code_lines = []
        for line in lines[1:]:
            if line.strip() == "```":
                break
            if line.strip():
                code_lines.append(line.strip())
        if not code_lines:
            continue
        snippet = None
        for line in code_lines:
            if line.startswith(("import ", "package ")):
                continue
            if line in {"main() {", "main(): Unit {", "{"}:
                continue
            if line.startswith("//"):
                continue
            snippet = clean_text(line)
            break
        snippet = snippet or clean_text(code_lines[0])
        if len(snippet) > 100:
            snippet = snippet[:99].rstrip() + "…"
        snippets.append(snippet)
    return snippets


def parse_since(lines: list[str]) -> str | None:
    text = clean_text(" ".join(clean_label_block(lines)))
    if not text:
        return None
    match = re.search(r"([0-9]+\.[0-9]+(?:\.[0-9]+)?)", text)
    if match:
        return match.group(1)
    return None


def parse_signature(lines: list[str]) -> str | None:
    for lang, code in extract_code_blocks(lines):
        if lang == "cangjie" and code:
            parts: list[str] = []
            depth = 0
            for raw_line in code.strip().splitlines():
                line = clean_text(raw_line)
                if not line:
                    continue
                parts.append(line)
                depth += line.count("(") - line.count(")")
                if "{" in line and depth <= 0:
                    break
                if depth <= 0 and re.search(r"\)\s*(?::\s*.+)?$", line):
                    break
            signature = " ".join(parts).strip()
            signature = re.sub(r"\s*\{\s*$", "", signature)
            signature = re.sub(r"\s+", " ", signature).strip()
            return signature or None
    return None


def parse_type_text(lines: list[str]) -> str | None:
    text = clean_text(" ".join(clean_label_block(lines)))
    return text or None


def sanitize_signature(signature: str | None) -> str | None:
    if not signature:
        return None
    text = signature.strip()
    if "## " in text or "```" in text:
        return None
    if text.count("(") != text.count(")"):
        return None
    return text


def fallback_callable_signature(
    heading_text: str,
    display: str,
    kind: str,
    params: list[dict],
    returns_md: str | None,
    signature: str | None,
) -> str | None:
    if kind not in {"function", "method", "constructor"} or signature:
        return signature
    label = "init" if kind == "constructor" else display
    args = []
    for item in params:
        part = item["label"]
        if item.get("type"):
            part = f"{part}: {item['type']}"
        args.append(part)
    returns = ""
    if kind != "constructor" and returns_md and returns_md not in {"Unit"}:
        returns = f": {returns_md}"
    return f"public {'init' if kind == 'constructor' else 'func'} {label}({', '.join(args)}){returns}".strip()


def build_extension_info(heading_text: str) -> dict | None:
    match = EXTEND_RE.match(heading_text)
    if not match:
        return None
    target_text = clean_text(match.group("target"))
    iface_text = clean_text(match.group("iface") or "")
    target_display = type_display_name(target_text)
    interface_display = type_display_name(iface_text) if iface_text else None
    return {
        "target": target_text or None,
        "target_display": target_display or None,
        "implements": iface_text or None,
        "implements_display": interface_display or None,
        "extension_kind": "implementation" if iface_text else "extension",
        "extension_owner_fqname": None,
    }


def split_params_src(params_src: str) -> list[str]:
    params: list[str] = []
    current: list[str] = []
    depth = 0
    for ch in params_src:
        if ch in "(<[{":
            depth += 1
        elif ch in ")>]}":
            depth = max(depth - 1, 0)
        if ch == "," and depth == 0:
            part = "".join(current).strip()
            if part:
                params.append(part)
            current = []
            continue
        current.append(ch)
    tail = "".join(current).strip()
    if tail:
        params.append(tail)
    return params


def split_top_level(text: str, delimiter: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in "(<[{":
            depth += 1
        elif ch in ")>]}":
            depth = max(depth - 1, 0)
        if depth == 0 and text.startswith(delimiter, i):
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
            i += len(delimiter)
            continue
        current.append(ch)
        i += 1
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def parse_type_params(signature: str | None, display: str) -> list[str]:
    if not signature:
        return []
    match = re.search(rf"\b{re.escape(display)}<([^>]+)>", signature)
    if not match:
        return []
    return [clean_text(item) for item in split_params_src(match.group(1)) if clean_text(item)]


def parse_type_params_from_text(text: str | None, display: str) -> list[str]:
    if not text:
        return []
    match = re.search(rf"\b{re.escape(display)}<([^>]+)>", text)
    if not match:
        return []
    return [clean_text(item) for item in split_params_src(match.group(1)) if clean_text(item)]


def parse_parent_types_from_signature(signature: str | None) -> list[str]:
    if not signature or "<:" not in signature:
        return []
    tail = signature.split("<:", 1)[1]
    tail = tail.split(" where ", 1)[0].strip()
    tail = re.sub(r"\s*\{\s*\}?\s*$", "", tail).strip()
    return [clean_text(item) for item in split_top_level(tail, "&") if clean_text(item)]


def is_probable_type_expr(text: str) -> bool:
    candidate = LINK_RE.sub(r"\1", text or "")
    candidate = strip_inline_html(candidate).strip()
    if not candidate:
        return False
    if any(marker in candidate for marker in ("使用示例", "参考示例", "示例见", "例如", "说明", "注意")):
        return False
    if candidate in {":", "-", "—"}:
        return False
    return bool(re.search(r"[A-Za-z_][A-Za-z0-9_]*", candidate))


def parse_parent_types_from_section(lines: list[str]) -> list[str]:
    parent_types: list[str] = []
    collected = False
    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped:
            if collected:
                break
            continue
        if not stripped.startswith("-"):
            if collected:
                break
            continue
        collected = True
        text = split_bullet(raw_line)
        if " - " in text:
            text = text.split(" - ", 1)[0]
        text = LINK_RE.sub(r"\1", text)
        text = clean_text(text)
        if is_probable_type_expr(text):
            parent_types.append(text)
    return parent_types


def parse_see_also(lines: list[str]) -> str | None:
    items: list[str] = []
    for raw_line in lines:
        stripped = raw_line.strip()
        plain = strip_inline_html(stripped)
        if not plain:
            continue
        if plain.startswith(("使用示例见", "另见", "参见", "See also", "See ")):
            items.append(stripped)
    return normalize_markdown("\n".join(items))


def related_links_from_markdown(text: str | None, page_url: str, kind: str) -> list[dict]:
    links = extract_markdown_links(text, page_url)
    return [{"kind": kind, "title": item["title"], "url": item["url"]} for item in links]


def parse_callable_info(signature: str | None, param_docs: list[dict]) -> tuple[dict | None, str | None]:
    if not signature:
        return None, None
    match = re.search(r"\((.*)\)\s*(?::\s*(.+))?$", signature)
    if not match:
        return None, None
    params_src = match.group(1).strip()
    return_type = clean_text(match.group(2) or "") or None
    docs_by_label = {item["label"]: item for item in param_docs}
    params = []
    for item in split_params_src(params_src):
        name_part, _, type_part = item.partition(":")
        label = clean_text(name_part.replace("!", ""))
        type_text = clean_text(type_part) or None
        is_named = "!" in name_part
        has_default = "=" in item
        default_value_md = None
        if "=" in item:
            default_value_md = clean_text(item.split("=", 1)[1]) or None
            type_text = clean_text(type_part.split("=", 1)[0]) or None
        params.append(
            {
                "label": label or item,
                "type": type_text,
                "is_named": is_named,
                "is_optional": has_default,
                "has_default": has_default,
                "default_value_md": default_value_md,
                "doc_md": docs_by_label.get(label, {}).get("doc_md"),
            }
        )
    return {"return_type": return_type, "params": params, "throws": []}, return_type


def simplify_type_text(text: str | None) -> str | None:
    if not text:
        return text
    value = clean_text(text)
    value = re.sub(r"\(([^()]*)\)\s*->", lambda _m: "(…) ->", value) if "->" in value else value
    if "<" in value and len(value) > 36:
        value = re.sub(r"<[^<>]+>", "<…>", value)
    return value


def build_signature_short(signature: str | None) -> str | None:
    if not signature:
        return None
    signature = clean_text(signature)
    if len(signature) <= 100:
        return signature
    match = re.search(r"^(.*?\()(.+)(\)\s*(?::\s*.+)?)$", signature)
    if not match:
        return simplify_type_text(signature)
    params = split_params_src(match.group(2))
    suffix = match.group(3)

    def render_param(item: str) -> str:
        name_part, sep, type_part = item.partition(":")
        if not sep:
            return simplify_type_text(item) or item
        type_part = simplify_type_text(type_part)
        return f"{clean_text(name_part)}: {type_part}"

    rendered = [render_param(item) for item in params]
    return_suffix = ""
    ret_match = re.match(r"\)\s*(?::\s*(.+))?$", suffix)
    if ret_match and ret_match.group(1):
        return_suffix = f"): {simplify_type_text(ret_match.group(1))}"
    else:
        return_suffix = ")"

    if len(rendered) <= 2:
        candidate = f"{match.group(1)}{', '.join(rendered)}{return_suffix}"
        return candidate if len(candidate) <= 100 else f"{match.group(1)}{rendered[0]}, ...{return_suffix}"
    return f"{match.group(1)}{', '.join(rendered[:2])}, ...{return_suffix}"


def heading_name(raw: str) -> str:
    raw = clean_text(raw)
    raw = re.sub(r"<.*?>", "", raw)
    raw = raw.replace("`", "")
    raw = raw.split("(", 1)[0]
    raw = raw.split(" ", 1)[0]
    return raw.strip()


def type_display_name(raw: str) -> str | None:
    text = strip_inline_html(raw or "").replace("`", "").strip()
    match = re.search(r"[A-Za-z_][A-Za-z0-9_]*", text)
    return match.group(0) if match else None


def display_from_heading(kind: str, heading_text: str) -> str:
    tail = heading_text
    member_match = MEMBER_KIND_RE.match(heading_text)
    if kind == "func" and member_match:
        tail = member_match.group(3)
    elif kind == "builtin":
        tail = heading_text
    elif kind in {"class", "struct", "interface", "enum", "func", "macro", "const", "var", "typealias", "type"}:
        tail = TOP_LEVEL_KIND_RE.match(heading_text).group(2) if TOP_LEVEL_KIND_RE.match(heading_text) else heading_text
    elif kind in {"prop", "let", "init", "operator"}:
        match = MEMBER_KIND_RE.match(heading_text)
        tail = match.group(3) if match else heading_text
        if kind == "init":
            return "init"
    elif kind == "method":
        match = MEMBER_KIND_RE.match(heading_text)
        tail = match.group(3) if match else heading_text
    name = heading_name(tail)
    return name or clean_text(heading_text)


def normalize_kind(kind: str, container: str | None) -> str:
    kind = kind.lower()
    if kind == "builtin":
        return "builtin"
    if kind == "type":
        return "typealias"
    if kind == "func":
        return "method" if container else "function"
    if kind == "let":
        return "property" if container else "variable"
    if kind == "prop":
        return "property"
    if kind == "init":
        return "constructor"
    return kind


def callable_hash(signature: str | None, display: str) -> str:
    seed = signature or display
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8]


def build_symbol_id(kind: str, package: str, module: str, container: str | None, display: str, signature: str | None) -> str:
    scope = "::".join(module.split("."))
    if container:
        scope = f"{scope}::{container}"
    base = f"{kind}::{scope}::{display}" if scope else f"{kind}::{display}"
    if kind in {"function", "method", "constructor"}:
        return f"{base}#{callable_hash(signature, display)}"
    return base


def parse_symbol_section(
    package: str,
    module: str,
    page_title: str,
    md_path: Path,
    src_root: Path,
    heading: Heading,
    container: str | None,
    extension_info: dict | None,
    default_package: str | None = None,
) -> ApiSymbol | None:
    heading_text = heading.text
    deprecated = bool(DEPRECATED_RE.search(heading_text))
    top_match = TOP_LEVEL_KIND_RE.match(heading_text)
    member_match = MEMBER_KIND_RE.match(heading_text)
    macro_match = MACRO_TITLE_RE.match(heading_text)
    constructor_match = (
        re.match(rf"^{re.escape(container)}\s*\(", heading_text) if container else None
    )
    if top_match:
        raw_kind = top_match.group(1)
    elif is_builtin_page_title(page_title) and heading.level == 2:
        raw_kind = "builtin"
    elif macro_match:
        raw_kind = "macro"
    elif member_match:
        raw_kind = member_match.group(2)
    elif constructor_match:
        raw_kind = "init"
    else:
        return None

    kind = normalize_kind(raw_kind, container)
    display = display_from_heading(raw_kind.lower(), heading_text)
    symbol_container = container if kind in {"method", "property", "constructor", "operator"} else None
    if kind in {"class", "struct", "interface", "enum", "typealias", "builtin"}:
        symbol_container = None
    symbol_extension_info = dict(extension_info) if extension_info else None
    if symbol_extension_info and symbol_container:
        symbol_extension_info["extension_owner_fqname"] = f"{module}.{symbol_container}"

    signature = sanitize_signature(parse_signature(heading.content))
    unlabeled, sections = split_labeled_sections(heading.content)
    summary_lines = [line for line in sections.get("功能", []) if not line.strip().startswith(">")]
    summary_md = extract_prose_markdown(summary_lines) or first_nonempty_paragraph(unlabeled)

    page_url = md_to_doc_url(src_root, md_path, default_package=default_package)
    deprecated_lines = sections.get("Deprecated", [])
    deprecated_info = build_deprecated_info(module, page_url, heading_text, deprecated_lines, heading.content)
    deprecated = deprecated or bool(deprecated_info)
    if deprecated_info and deprecated_info.get("message_md"):
        deprecated_info["message_md"] = absolutize_markdown_links(deprecated_info["message_md"], page_url)
    parent_types = parse_parent_types_from_signature(signature)
    if not parent_types:
        parent_types = parse_parent_types_from_section(sections.get("父类型", []))
    notes_parts: list[str] = []
    notes_block = normalize_markdown("\n".join(sections.get("说明", []) + sections.get("描述", [])))
    if notes_block:
        notes_parts.append(notes_block)
    for block in extract_blockquote_admonitions(sections.get("功能", [])):
        if deprecated_info and deprecated_info.get("message_md") and deprecated_info["message_md"] in block:
            continue
        plain = strip_inline_html(block).strip()
        if "支持平台" in plain:
            continue
        notes_parts.append(block)
    if deprecated_lines:
        block = normalize_markdown("\n".join(deprecated_lines))
        if block:
            notes_parts.append(f"Deprecated:\n{block}")

    params = parse_params(sections.get("参数", []))
    returns_md = parse_returns(sections.get("返回值", []))
    examples_md = parse_examples(sections.get("示例", []))
    since = parse_since(sections.get("Since", []))
    availability = parse_availability(heading.content)
    type_text = parse_type_text(sections.get("类型", []))

    if kind == "macro":
        signature = display
    elif kind == "builtin" and not signature:
        signature = strip_inline_html(heading_text).strip()

    if kind in {"property", "variable"} and not signature and type_text:
        signature = f"public {'prop' if kind == 'property' else 'let'} {display}: {type_text}"

    signature = fallback_callable_signature(heading_text, display, kind, params, returns_md, signature)
    if kind == "constructor" and signature:
        signature = re.sub(r"^public\s+[A-Za-z_][A-Za-z0-9_]*", "public init", signature, count=1)

    summary_md = strip_structured_notes(
        summary_md,
        deprecated_message=deprecated_info["message_md"] if deprecated_info else None,
        availability=availability,
    )
    summary_md = absolutize_markdown_links(summary_md, page_url)
    returns_md = absolutize_markdown_links(returns_md, page_url)
    notes_md = absolutize_markdown_links(normalize_markdown("\n\n".join(notes_parts)), page_url)
    exceptions_md = absolutize_markdown_links(
        normalize_markdown("\n".join(sections.get("异常", []))) if sections.get("异常") else None,
        page_url,
    )
    if exceptions_md:
        exceptions_md = normalize_markdown(f"异常：\n{exceptions_md}")
    see_also_md = absolutize_markdown_links(parse_see_also(heading.content), page_url)

    if kind in {"function", "method", "constructor"} and not signature:
        return None

    fq_parts = [module]
    if symbol_container:
        fq_parts.append(symbol_container)
    fq_parts.append(display)
    fqname = ".".join(part for part in fq_parts if part)
    qualified_title = f"{symbol_container}.{heading_text}" if symbol_container else heading_text

    anchor = slugify_heading(heading_text)
    if kind == "method" and symbol_container and qualified_title.startswith(f"{symbol_container}.func "):
        qualified_title = qualified_title.replace(f"{symbol_container}.func ", f"{symbol_container}.", 1)
    elif kind == "function" and qualified_title.startswith("func "):
        qualified_title = qualified_title
    aliases = [display]
    if symbol_container:
        aliases.append(f"{symbol_container}.{display}")
    aliases.append(fqname)
    aliases = [alias for i, alias in enumerate(aliases) if alias and alias not in aliases[:i]]
    callable_info, inferred_return_type = parse_callable_info(signature, params)
    throws = parse_throws(sections.get("异常", []))
    if kind in {"function", "method", "constructor"} and callable_info is None:
        callable_info = {"return_type": inferred_return_type, "params": [], "throws": []}
    if callable_info is not None:
        callable_info["throws"] = throws
    if kind in {"function", "method", "constructor"} and returns_md is None and inferred_return_type not in {None, "Unit"}:
        returns_md = inferred_return_type
    type_info = None
    if kind in {"class", "struct", "interface", "enum", "typealias", "exception", "builtin"}:
        type_info = {
            "type_params": parse_type_params(signature, display) or parse_type_params_from_text(heading_text, display),
            "bases": [],
            "implements": [],
        }
    value_info = None
    if kind in {"property", "field", "variable", "constant"}:
        value_info = {"value_type": inferred_return_type, "mutable": kind in {"property", "field", "variable"}}
    detail_parts: list[str] = []
    if notes_md:
        detail_parts.append(notes_md)
    if see_also_md:
        detail_parts.append(see_also_md)
    summary_short_md = summarize_markdown(summary_md, max_len=90)
    if summary_short_md:
        summary_short_md = normalize_markdown(absolutize_markdown_links(summary_short_md, page_url))
    return ApiSymbol(
        id=build_symbol_id(kind, package, module, symbol_container, display, signature),
        fqname=fqname,
        kind=kind,
        package=package,
        module=module,
        container=symbol_container,
        display=display,
        qualified_title=strip_inline_html(qualified_title).strip(),
        page_title=strip_inline_html(heading_text if heading_text else page_title).strip(),
        page_title_html=heading_text if heading_text else page_title,
        signature=signature,
        summary_short_md=summary_short_md,
        summary_md=summary_md,
        details_md=normalize_markdown("\n\n".join(detail_parts)),
        notes_md=notes_md,
        exceptions_md=exceptions_md,
        see_also_md=see_also_md,
        params=params,
        returns_md=returns_md,
        examples_md=examples_md,
        example_titles=[],
        example_snippets_short=build_example_snippets_short(examples_md),
        page_url=page_url,
        anchor=anchor,
        since=since,
        deprecated=deprecated_info,
        aliases=aliases,
        signature_short=build_signature_short(signature),
        callable=callable_info if kind in {"function", "method", "constructor"} else None,
        type_info=type_info,
        value_info=value_info,
        availability=availability,
        extension_info=symbol_extension_info,
        parent_types=parent_types,
    )


def parse_api_file(src_root: Path, md_path: Path, default_package: str | None = None) -> list[ApiSymbol]:
    rel = md_path.relative_to(src_root)
    package, module = split_module_parts(rel, default_package=default_package)
    if not include_package(package):
        return []
    lines = md_path.read_text(encoding="utf-8").splitlines()
    page_title, headings = parse_headings(lines)
    symbols: list[ApiSymbol] = []
    current_container: str | None = None
    current_extension_info: dict | None = None
    for heading in headings:
        if heading.level == 2:
            top_match = TOP_LEVEL_KIND_RE.match(heading.text)
            macro_match = MACRO_TITLE_RE.match(heading.text)
            builtin_match = is_builtin_page_title(page_title)
            if not top_match and not macro_match and not builtin_match:
                continue
            raw_kind = top_match.group(1).lower() if top_match else ("macro" if macro_match else "builtin")
            current_container = None
            current_extension_info = None
            symbol = parse_symbol_section(
                package, module, page_title, md_path, src_root, heading, None, None, default_package=default_package
            )
            if symbol:
                symbols.append(symbol)
                if raw_kind in {"class", "struct", "interface", "enum", "typealias", "builtin"}:
                    current_container = symbol.display
        elif heading.level == 3:
            extend_match = EXTEND_RE.match(heading.text)
            if extend_match:
                current_container = heading_name(extend_match.group("target")) or current_container
                current_extension_info = build_extension_info(heading.text)
                continue
            if current_container:
                symbol = parse_symbol_section(
                    package,
                    module,
                    page_title,
                    md_path,
                    src_root,
                    heading,
                    current_container,
                    current_extension_info,
                    default_package=default_package,
                )
                if symbol:
                    symbols.append(symbol)
        elif heading.level >= 4 and current_container:
            symbol = parse_symbol_section(
                package,
                module,
                page_title,
                md_path,
                src_root,
                heading,
                current_container,
                current_extension_info,
                default_package=default_package,
            )
            if symbol:
                symbols.append(symbol)
    return symbols


def sample_related_keys(title: str) -> tuple[str | None, set[str]]:
    match = SAMPLE_TITLE_RE.match(clean_text(title))
    if not match:
        return None, set()
    container = match.group("container")
    members = {
        part.strip()
        for part in re.split(r"[、/]", match.group("members"))
        if part.strip()
    }
    return container, members


def extract_code_identifiers(examples_md: list[str]) -> set[str]:
    names: set[str] = set()
    for block in examples_md:
        for match in IDENT_RE.findall(block):
            names.add(match)
    return names


def extract_title_identifiers(title: str) -> set[str]:
    names: set[str] = set()
    for match in IDENT_RE.findall(strip_inline_html(title)):
        names.add(match)
    return names


def parse_example_file(src_root: Path, md_path: Path, default_package: str | None = None) -> dict:
    rel = md_path.relative_to(src_root)
    package, module = split_module_parts(rel, default_package=default_package)
    if not include_package(package):
        return {}
    lines = md_path.read_text(encoding="utf-8").splitlines()
    title, _headings = parse_headings(lines)
    summary = first_nonempty_paragraph(lines[1:])
    examples_md = [
        f"{fence}\n{code}\n```"
        for lang, code in extract_code_blocks(lines)
        if code
        for fence in [f"```{lang}".rstrip()]
    ]
    container, members = sample_related_keys(title)
    identifiers = sorted(extract_code_identifiers(examples_md))
    example_id_base = module.replace(".", "::")
    if container and members:
        tail = "-".join(sorted(members))
        example_id = f"example::{example_id_base}::{container}::{tail}"
    else:
        example_id = f"example::{example_id_base}::{md_path.stem}"
    return {
        "id": example_id,
        "title": strip_inline_html(title or md_path.stem).strip(),
        "summary_md": summary,
        "doc_url": md_to_doc_url(src_root, md_path, default_package=default_package),
        "examples_md": examples_md,
        "module": module,
        "container_hint": container,
        "member_hints": sorted(members),
        "identifiers": identifiers,
        "title_identifiers": sorted(extract_title_identifiers(title or md_path.stem)),
        "related_symbols": [],
    }


def relate_examples(symbols: list[ApiSymbol], examples: list[dict]) -> None:
    by_module: dict[str, list[ApiSymbol]] = {}
    for symbol in symbols:
        by_module.setdefault(symbol.module, []).append(symbol)

    for example in examples:
        matches: list[str] = []
        identifiers = set(example["identifiers"])
        title_identifiers = set(example["title_identifiers"])
        for symbol in by_module.get(example["module"], []):
            if example["container_hint"]:
                if symbol.container == example["container_hint"]:
                    if example["member_hints"] and symbol.display not in example["member_hints"]:
                        continue
                elif symbol.display != example["container_hint"]:
                    continue
            elif example["member_hints"] and symbol.display not in example["member_hints"]:
                continue
            if symbol.container:
                if symbol.display not in identifiers and symbol.display not in title_identifiers:
                    if symbol.container not in identifiers and symbol.container not in title_identifiers:
                        continue
            else:
                if symbol.display not in identifiers and symbol.display not in title_identifiers:
                    continue

            if symbol.kind in {"method", "function", "constructor", "property", "operator"} and symbol.display not in identifiers:
                if symbol.display not in title_identifiers and (not symbol.container or symbol.container not in identifiers):
                    continue
            matches.append(symbol.id)
            symbol.related_links.append(
                {
                    "kind": "example",
                    "title": example["title"],
                    "url": example["doc_url"],
                }
            )
        example["related_symbols"] = sorted(set(matches))
        del example["module"]
        del example["container_hint"]
        del example["member_hints"]
        del example["identifiers"]
        del example["title_identifiers"]


def make_search_keys(symbol: ApiSymbol) -> list[str]:
    keys = [symbol.display, symbol.fqname]
    if symbol.module:
        keys.append(symbol.module)
        keys.append(symbol.module.split(".")[-1])
    if symbol.container:
        keys.append(f"{symbol.container}.{symbol.display}")
    deduped: list[str] = []
    for key in keys:
        if key and key not in deduped:
            deduped.append(key)
    return deduped


def make_search_keys_normalized(symbol: ApiSymbol) -> list[str]:
    keys = []
    keys.extend(symbol.aliases)
    keys.extend(make_search_keys(symbol))
    normalized: list[str] = []
    for key in keys:
        value = clean_text(strip_inline_html(key)).lower()
        if value and value not in normalized:
            normalized.append(value)
    return normalized


def finalize_example_metadata(symbols: list[ApiSymbol]) -> None:
    for symbol in symbols:
        symbol.example_titles = [
            link["title"]
            for link in symbol.related_links
            if link.get("kind") == "example" and link.get("title")
        ]
        symbol.example_snippets_short = build_example_snippets_short(symbol.examples_md)


def resolve_type_info(symbols: list[ApiSymbol]) -> None:
    by_display: dict[str, list[ApiSymbol]] = {}
    for symbol in symbols:
        by_display.setdefault(symbol.display, []).append(symbol)

    for symbol in symbols:
        if not symbol.type_info:
            continue
        bases: list[str] = []
        implements: list[str] = []
        for parent in symbol.parent_types:
            display = type_display_name(parent) or parent
            candidates = by_display.get(display, [])
            resolved_kind = candidates[0].kind if len(candidates) == 1 else None
            if symbol.kind == "interface":
                bases.append(parent)
            elif resolved_kind in {"class", "struct"}:
                bases.append(parent)
            else:
                implements.append(parent)
        symbol.type_info["bases"] = bases
        symbol.type_info["implements"] = implements


def build_overview_links(src_root: Path, default_package: str | None = None) -> dict[str, list[dict]]:
    links_by_target: dict[str, list[dict]] = {}
    for md_path in iter_markdown_files(src_root):
        rel_posix = md_path.relative_to(src_root).as_posix()
        if not rel_posix.endswith("_package_overview.md"):
            continue
        package, _module = split_module_parts(md_path.relative_to(src_root), default_package=default_package)
        if not include_package(package):
            continue
        lines = md_path.read_text(encoding="utf-8").splitlines()
        title, _headings = parse_headings(lines)
        page_url = md_to_doc_url(src_root, md_path, default_package=default_package)
        guide_title = title or md_path.stem
        for raw_line in lines:
            for item in extract_markdown_links(raw_line, page_url):
                if "_package_api/" not in item["url"]:
                    continue
                links_by_target.setdefault(item["url"], []).append(
                    {
                        "kind": "guide",
                        "title": guide_title,
                        "url": page_url,
                    }
                )
    return links_by_target


def attach_related_links(symbols: list[ApiSymbol], overview_links: dict[str, list[dict]]) -> None:
    for symbol in symbols:
        if symbol.see_also_md:
            symbol.related_links.extend(related_links_from_markdown(symbol.see_also_md, symbol.page_url, "see_also"))
        for key in (symbol.page_url, f"{symbol.page_url}#{symbol.anchor}" if symbol.anchor else None):
            if not key:
                continue
            symbol.related_links.extend(overview_links.get(key, []))


def build_diagnostics_index(src_root: Path, default_package: str | None = None) -> list[dict]:
    diagnostics: list[dict] = []
    candidate_dirs = [
        src_root / "compiler" / "errors",
        src_root / "diagnostics",
        src_root / "errors",
    ]
    for root in candidate_dirs:
        if not root.is_dir():
            continue
        for md_path in sorted(root.rglob("*.md")):
            lines = md_path.read_text(encoding="utf-8").splitlines()
            title, _headings = parse_headings(lines)
            code_match = re.search(r"\b([0-9]{3,})\b", md_path.stem) or re.search(r"\b([0-9]{3,})\b", title)
            if not code_match:
                continue
            diagnostics.append(
                {
                    "code": int(code_match.group(1)),
                    "source": "Cangjie",
                    "title": title or md_path.stem,
                    "summary_md": first_nonempty_paragraph(lines[1:]),
                    "details_md": normalize_markdown("\n".join(lines[1:])),
                    "page_url": md_to_doc_url(src_root, md_path, default_package=default_package),
                    "anchor": None,
                    "since": None,
                    "deprecated": False,
                    "search_keys": [code_match.group(1), clean_text(title or md_path.stem).lower()],
                }
            )
    return diagnostics


def build_docs_index(site_root: Path, book_dir: Path) -> dict:
    src_root = parse_book_src(book_dir)
    default_package = infer_default_package(book_dir, site_root, src_root)
    searchindex_name = load_searchindex_name(site_root)
    symbols: list[ApiSymbol] = []
    examples: list[dict] = []

    for md_path in iter_markdown_files(src_root):
        rel_posix = md_path.relative_to(src_root).as_posix()
        if "/_package_api/" in rel_posix or "_package_api/" in rel_posix:
            symbols.extend(parse_api_file(src_root, md_path, default_package=default_package))
        elif "/_samples/" in rel_posix or "_samples/" in rel_posix:
            example = parse_example_file(src_root, md_path, default_package=default_package)
            if example:
                examples.append(example)

    unique_symbols: dict[str, ApiSymbol] = {}
    for symbol in symbols:
        if symbol.id not in unique_symbols:
            unique_symbols[symbol.id] = symbol

    symbols = sorted(
        unique_symbols.values(),
        key=lambda item: (item.package, item.module, item.container or "", item.display, item.kind, item.id),
    )
    resolve_type_info(symbols)
    for symbol in symbols:
        symbol.search_keys_normalized = make_search_keys_normalized(symbol)
    symbol_by_fqname = {symbol.fqname: symbol for symbol in symbols}
    for symbol in symbols:
        if symbol.deprecated and symbol.deprecated.get("replacement_fqname"):
            target = symbol_by_fqname.get(symbol.deprecated["replacement_fqname"])
            if target:
                symbol.deprecated["replacement_url"] = (
                    f"{target.page_url}#{target.anchor}" if target.anchor else target.page_url
                )
    attach_related_links(symbols, build_overview_links(src_root, default_package=default_package))
    relate_examples(symbols, examples)
    finalize_example_metadata(symbols)
    examples = sorted(examples, key=lambda item: (item["doc_url"], item["id"]))
    diagnostics = build_diagnostics_index(src_root, default_package=default_package)

    package_names = sorted({symbol.package for symbol in symbols})
    if len(package_names) == 1:
        site_name = f"{package_names[0]} docs"
    else:
        site_name = "cangjie docs"

    return {
        "format": 4,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": {
            "site": site_name,
            "version": None,
            "searchindex": searchindex_name,
        },
        "symbol_count": len(symbols),
        "symbols": [
            {
                "id": symbol.id,
                "fqname": symbol.fqname,
                "kind": symbol.kind,
                "package": symbol.package,
                "module": symbol.module,
                "container": symbol.container,
                "display": symbol.display,
                "qualified_title": symbol.qualified_title,
                "page_title": symbol.page_title,
                "page_title_html": symbol.page_title_html,
                "signature": symbol.signature,
                "signature_short": symbol.signature_short,
                "summary_short_md": symbol.summary_short_md,
                "summary_md": symbol.summary_md,
                "details_md": symbol.details_md,
                "notes_md": symbol.notes_md,
                "exceptions_md": symbol.exceptions_md,
                "see_also_md": symbol.see_also_md,
                "params": symbol.params,
                "returns_md": symbol.returns_md,
                "examples_md": symbol.examples_md,
                "example_titles": symbol.example_titles,
                "example_snippets_short": symbol.example_snippets_short,
                "page_url": symbol.page_url,
                "anchor": symbol.anchor,
                "related_links": sorted(
                    {json.dumps(link, ensure_ascii=False, sort_keys=True): link for link in symbol.related_links}.values(),
                    key=lambda item: (item["kind"], item["title"], item["url"]),
                ),
                "since": symbol.since,
                "deprecated": symbol.deprecated,
                "aliases": symbol.aliases,
                "search_keys": make_search_keys(symbol),
                "search_keys_normalized": symbol.search_keys_normalized,
                "callable": symbol.callable,
                "type_info": symbol.type_info,
                "value_info": symbol.value_info,
                "availability": symbol.availability,
                "extension_info": symbol.extension_info,
            }
            for symbol in symbols
        ],
        "diagnostics": diagnostics,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export mdBook docs into docs-index.json.")
    parser.add_argument("site_root", help="Rendered mdBook output directory")
    parser.add_argument("--book-dir", required=True, help="mdBook project directory")
    parser.add_argument("--output", help="Output JSON path. Defaults to <site_root>/docs-index.json.")
    args = parser.parse_args()

    site_root = Path(args.site_root).resolve()
    book_dir = Path(args.book_dir).resolve()
    output_path = Path(args.output).resolve() if args.output else site_root / "docs-index.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    docs_index = build_docs_index(site_root, book_dir)
    output_path.write_text(json.dumps(docs_index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
