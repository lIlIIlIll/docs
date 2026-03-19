#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


REQUIRED_TOP_LEVEL = {"format", "generated_at", "source", "symbol_count", "symbols", "diagnostics"}
REQUIRED_SYMBOL_FIELDS = {
    "id","fqname","kind","package","module","container","display","qualified_title",
    "page_title","page_title_html","signature","signature_short","summary_short_md",
    "summary_md","details_md","examples_md","page_url","anchor","related_links",
    "since","deprecated","aliases","search_keys","extension_info"
}


def validate_symbol(symbol: dict, index: int) -> list[str]:
    errors = []
    missing = REQUIRED_SYMBOL_FIELDS - set(symbol.keys())
    if missing:
        return [f"symbol[{index}] missing fields: {', '.join(sorted(missing))}"]
    for key in ("id","fqname","kind","package","module","display","qualified_title","page_title","page_title_html","page_url"):
        if not isinstance(symbol[key], str) or not symbol[key]:
            errors.append(f"symbol[{index}] invalid {key}")
    if symbol["container"] is not None and not isinstance(symbol["container"], str):
        errors.append(f"symbol[{index}] container must be string|null")
    if symbol["anchor"] is not None and not isinstance(symbol["anchor"], str):
        errors.append(f"symbol[{index}] anchor must be string|null")
    if not isinstance(symbol["examples_md"], list):
        errors.append(f"symbol[{index}] examples_md must be array")
    if not isinstance(symbol["related_links"], list):
        errors.append(f"symbol[{index}] related_links must be array")
    if not isinstance(symbol["aliases"], list):
        errors.append(f"symbol[{index}] aliases must be array")
    if not isinstance(symbol["search_keys"], list):
        errors.append(f"symbol[{index}] search_keys must be array")
    if symbol["page_url"].find("_samples/") != -1:
        errors.append(f"symbol[{index}] sample page leaked into symbols")
    if symbol["kind"] in {"function","method","constructor"}:
        if not symbol.get("signature"):
            errors.append(f"symbol[{index}] callable symbol missing signature")
        callable_info = symbol.get("callable")
        if not isinstance(callable_info, dict):
            errors.append(f"symbol[{index}] callable symbol missing callable object")
        else:
            if not isinstance(callable_info.get("params"), list):
                errors.append(f"symbol[{index}] callable.params must be array")
            if not isinstance(callable_info.get("throws"), list):
                errors.append(f"symbol[{index}] callable.throws must be array")
    extension_info = symbol["extension_info"]
    if extension_info is not None:
        if not isinstance(extension_info, dict):
            errors.append(f"symbol[{index}] extension_info must be object|null")
        else:
            for key in ("target", "target_display", "implements", "implements_display"):
                if key not in extension_info:
                    errors.append(f"symbol[{index}] extension_info missing {key}")
    deprecated = symbol["deprecated"]
    if deprecated is not None:
        if not isinstance(deprecated, dict):
            errors.append(f"symbol[{index}] deprecated must be object|null")
        else:
            for key in ("is_deprecated","message_md","since","replacement_fqname","replacement_url"):
                if key not in deprecated:
                    errors.append(f"symbol[{index}] deprecated missing {key}")
    return errors


def validate_docs_index(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = []
    missing = REQUIRED_TOP_LEVEL - set(data.keys())
    if missing:
        return [f"top-level missing fields: {', '.join(sorted(missing))}"]
    if data.get("format") != 4:
        errors.append(f"format must be 4, got {data.get('format')}")
    symbols = data["symbols"]
    diagnostics = data["diagnostics"]
    if not isinstance(symbols, list):
        return ["top-level symbols must be array"]
    if not isinstance(diagnostics, list):
        return ["top-level diagnostics must be array"]
    if data["symbol_count"] != len(symbols):
        errors.append(f"symbol_count mismatch: declared {data['symbol_count']}, actual {len(symbols)}")
    ids = Counter()
    for i, symbol in enumerate(symbols):
        if not isinstance(symbol, dict):
            errors.append(f"symbol[{i}] must be object")
            continue
        errors.extend(validate_symbol(symbol, i))
        ids[symbol["id"]] += 1
    dup = sorted(k for k,v in ids.items() if v > 1)
    if dup:
        errors.append(f"duplicate symbol ids: {', '.join(dup)}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate docs-index.json.")
    parser.add_argument("docs_index")
    args = parser.parse_args()
    errors = validate_docs_index(Path(args.docs_index).resolve())
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"OK: {Path(args.docs_index).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
