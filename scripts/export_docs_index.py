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


SEARCHINDEX_PATTERN = re.compile(
    r"JSON\.parse\((?P<payload>'(?:\\.|[^'])*')\)\)\s*;?\s*$",
    re.DOTALL,
)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
LABEL_RE = re.compile(r"^(功能|参数|返回值|示例|运行结果|类型|父类型|异常|自\s*[0-9.]+\s*版本开始支持|Since|Deprecated|说明|描述)：?\s*(.*)$")
TOP_LEVEL_KIND_RE = re.compile(r"^(class|struct|interface|enum|func|macro|const|var|typealias)\s+(.+)$", re.IGNORECASE)
MEMBER_KIND_RE = re.compile(r"^(?:(static)\s+)?(prop|let|func|init|operator)\b\s*(.*)$", re.IGNORECASE)
MACRO_TITLE_RE = re.compile(r"^`?(?P<name>@[A-Za-z_][\w]*)`?\s*(?:宏|Macro)$")
EXTEND_RE = re.compile(
    r"^extend(?:<[^>]+>)?\s+(?P<target>.+?)(?:\s*<:\s*(?P<iface>.+))?$",
    re.IGNORECASE,
)
SAMPLE_TITLE_RE = re.compile(r"^(?P<container>[A-Za-z_][\w]*)\s*的\s*(?P<members>.+?)\s*函数$")
LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
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
    params: list[dict]
    returns_md: str | None
    examples_md: list[str]
    page_url: str
    anchor: str | None
    related_links: list[dict] = field(default_factory=list)
    since: str | None = None
    deprecated: dict | None = None
    aliases: list[str] = field(default_factory=list)
    signature_short: str | None = None
    callable: dict | None = None
    type_info: dict | None = None
    value_info: dict | None = None
    availability: dict | None = None
    extension_info: dict | None = None


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


def split_module_parts(rel_path: Path) -> tuple[str, str]:
    parts = list(rel_path.parts)
    if not parts:
        return "", ""
    package = parts[0]
    module_parts = [part for part in parts[:-1] if "_package_" not in part and "_samples" not in part]
    if not module_parts:
        module_parts = [package]
    return package, ".".join(module_parts)


def include_package(package: str) -> bool:
    return package in DOCS_SITE_PREFIX


def md_to_doc_url(src_root: Path, md_path: Path, anchor: str | None = None) -> str:
    rel = md_path.relative_to(src_root)
    package = rel.parts[0] if rel.parts else ""
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


def build_signature_short(signature: str | None) -> str | None:
    if not signature:
        return None
    match = re.search(r"^(.*?\()(.+)(\)\s*(?::\s*.+)?)$", signature)
    if not match:
        return signature
    params = split_params_src(match.group(2))
    if len(params) <= 2:
        return signature
    first_two = ", ".join(params[:2])
    return f"{match.group(1)}{first_two}, ...{match.group(3)}"


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
    elif kind in {"class", "struct", "interface", "enum", "func", "macro", "const", "var", "typealias"}:
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
    if kind in {"class", "struct", "interface", "enum", "typealias"}:
        symbol_container = None

    signature = sanitize_signature(parse_signature(heading.content))
    unlabeled, sections = split_labeled_sections(heading.content)
    summary_md = extract_prose_markdown(sections.get("功能", [])) or first_nonempty_paragraph(unlabeled)

    detail_parts: list[str] = []
    for label in ("说明", "描述", "类型", "父类型", "异常"):
        block = normalize_markdown("\n".join(sections.get(label, [])))
        if block:
            prefix = "" if label in {"说明", "描述"} else f"{label}：\n"
            detail_parts.append(f"{prefix}{block}".strip())
    page_url = md_to_doc_url(src_root, md_path)
    deprecated_lines = sections.get("Deprecated", [])
    deprecated_info = build_deprecated_info(module, page_url, heading_text, deprecated_lines, heading.content)
    deprecated = deprecated or bool(deprecated_info)
    for block in extract_blockquote_admonitions(sections.get("功能", [])):
        if deprecated_info and deprecated_info.get("message_md") and deprecated_info["message_md"] in block:
            continue
        plain = strip_inline_html(block).strip()
        if "支持平台" in plain:
            continue
        detail_parts.append(block)
    if deprecated_lines:
        block = normalize_markdown("\n".join(deprecated_lines))
        if block:
            detail_parts.append(f"Deprecated:\n{block}")

    params = parse_params(sections.get("参数", []))
    returns_md = parse_returns(sections.get("返回值", []))
    examples_md = parse_examples(sections.get("示例", []))
    since = parse_since(sections.get("Since", []))
    availability = parse_availability(heading.content)
    type_text = parse_type_text(sections.get("类型", []))

    if kind == "macro":
        signature = display

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
    type_info = {"type_params": [], "bases": [], "implements": []} if kind in {"class", "struct", "interface", "enum", "typealias", "exception"} else None
    value_info = None
    if kind in {"property", "field", "variable", "constant"}:
        value_info = {"value_type": inferred_return_type, "mutable": kind in {"property", "field", "variable"}}
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
        summary_short_md=first_sentence(summary_md),
        summary_md=summary_md,
        details_md=normalize_markdown("\n\n".join(detail_parts)),
        params=params,
        returns_md=returns_md,
        examples_md=examples_md,
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
        extension_info=extension_info,
    )


def parse_api_file(src_root: Path, md_path: Path) -> list[ApiSymbol]:
    rel = md_path.relative_to(src_root)
    package, module = split_module_parts(rel)
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
            if not top_match and not macro_match:
                continue
            raw_kind = top_match.group(1).lower() if top_match else "macro"
            current_container = None
            current_extension_info = None
            symbol = parse_symbol_section(package, module, page_title, md_path, src_root, heading, None, None)
            if symbol:
                symbols.append(symbol)
                if raw_kind in {"class", "struct", "interface", "enum", "typealias"}:
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


def parse_example_file(src_root: Path, md_path: Path) -> dict:
    rel = md_path.relative_to(src_root)
    package, module = split_module_parts(rel)
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
        "title": title or md_path.stem,
        "summary_md": summary,
        "doc_url": md_to_doc_url(src_root, md_path),
        "examples_md": examples_md,
        "module": module,
        "container_hint": container,
        "member_hints": sorted(members),
        "identifiers": identifiers,
        "related_symbols": [],
    }


def relate_examples(symbols: list[ApiSymbol], examples: list[dict]) -> None:
    by_module: dict[str, list[ApiSymbol]] = {}
    for symbol in symbols:
        by_module.setdefault(symbol.module, []).append(symbol)

    for example in examples:
        matches: list[str] = []
        identifiers = set(example["identifiers"])
        for symbol in by_module.get(example["module"], []):
            if example["container_hint"]:
                if symbol.container == example["container_hint"]:
                    if example["member_hints"] and symbol.display not in example["member_hints"]:
                        continue
                elif symbol.display != example["container_hint"]:
                    continue
            elif example["member_hints"] and symbol.display not in example["member_hints"]:
                continue

            if symbol.container and symbol.container not in identifiers and symbol.display not in identifiers:
                if example["member_hints"]:
                    continue
            if symbol.kind in {"method", "function", "constructor", "property", "operator"}:
                if symbol.display not in identifiers and symbol.container not in identifiers:
                    continue
            matches.append(symbol.id)
            symbol.related_links.append(
                {
                    "kind": "example",
                    "title": Path(example["doc_url"]).stem,
                    "url": example["doc_url"],
                }
            )
        example["related_symbols"] = sorted(set(matches))
        del example["module"]
        del example["container_hint"]
        del example["member_hints"]
        del example["identifiers"]


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


def build_docs_index(site_root: Path, book_dir: Path) -> dict:
    src_root = parse_book_src(book_dir)
    searchindex_name = load_searchindex_name(site_root)
    symbols: list[ApiSymbol] = []
    examples: list[dict] = []

    for md_path in iter_markdown_files(src_root):
        rel_posix = md_path.relative_to(src_root).as_posix()
        if "/_package_api/" in rel_posix or "_package_api/" in rel_posix:
            symbols.extend(parse_api_file(src_root, md_path))
        elif "/_samples/" in rel_posix or "_samples/" in rel_posix:
            example = parse_example_file(src_root, md_path)
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
    symbol_by_fqname = {symbol.fqname: symbol for symbol in symbols}
    for symbol in symbols:
        if symbol.deprecated and symbol.deprecated.get("replacement_fqname"):
            target = symbol_by_fqname.get(symbol.deprecated["replacement_fqname"])
            if target:
                symbol.deprecated["replacement_url"] = (
                    f"{target.page_url}#{target.anchor}" if target.anchor else target.page_url
                )
    relate_examples(symbols, examples)
    examples = sorted(examples, key=lambda item: (item["doc_url"], item["id"]))

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
                "params": symbol.params,
                "returns_md": symbol.returns_md,
                "examples_md": symbol.examples_md,
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
                "callable": symbol.callable,
                "type_info": symbol.type_info,
                "value_info": symbol.value_info,
                "availability": symbol.availability,
                "extension_info": symbol.extension_info,
            }
            for symbol in symbols
        ],
        "diagnostics": [],
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
