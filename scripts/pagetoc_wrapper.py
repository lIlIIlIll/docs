#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import subprocess
import sys


def run_pagetoc(payload: bytes) -> None:
    result = subprocess.run(
        ["mdbook-pagetoc"],
        input=payload,
        capture_output=True,
    )
    if result.stdout:
        sys.stdout.buffer.write(result.stdout)
    if result.stderr:
        sys.stderr.buffer.write(result.stderr)
    sys.exit(result.returncode)


def main() -> None:
    if len(sys.argv) >= 2 and sys.argv[1] == "supports":
        args = ["mdbook-pagetoc", "supports"] + sys.argv[2:]
        if len(args) == 2:
            sys.stdout.write("true")
            return
        result = subprocess.run(
            args,
            capture_output=True,
        )
        if result.stdout:
            sys.stdout.buffer.write(result.stdout)
        if result.stderr:
            sys.stderr.buffer.write(result.stderr)
        sys.exit(result.returncode)

    raw = sys.stdin.buffer.read()
    if not raw:
        return

    try:
        data = json.loads(raw)
    except Exception as exc:
        print(f"[pagetoc-wrapper] ERROR: {exc}", file=sys.stderr, flush=True)
        sys.exit(1)

    if isinstance(data, dict) and "book" in data:
        ctx = data.get("context", {})
        book = data["book"]
        payload = json.dumps([ctx, book], ensure_ascii=False).encode("utf-8")
        run_pagetoc(payload)

    run_pagetoc(raw)


if __name__ == "__main__":
    main()
