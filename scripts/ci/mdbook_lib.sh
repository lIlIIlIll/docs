#!/usr/bin/env bash
set -euo pipefail

DOCS_ROOT="${GITHUB_WORKSPACE:-$(pwd)}"

log() {
  echo "[ci] $*" >&2
}

retry_clone() {
  local url="$1"
  local dir="$2"
  local depth="${3:-1}"
  local branch_hint="${4:-}"
  local attempt
  for attempt in 1 2 3; do
    log "clone attempt $attempt: $url -> $dir"
    rm -rf "$dir"
    if timeout 30 git -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=60 \
      clone --no-checkout --depth "$depth" ${branch_hint:+--branch "$branch_hint"} \
      "$url" "$dir"; then
      return 0
    fi
    log "clone failed, retrying..."
    sleep 10
  done
  return 1
}

ensure_local_branch() {
  local repo="$1"
  local branch="$2"
  if git -C "$repo" show-ref --verify --quiet "refs/remotes/origin/$branch"; then
    git -C "$repo" branch -f "$branch" "origin/$branch"
  fi
}

clone_ext_repo() {
  local url="$1"
  local dir="$2"
  local branch_hint="${3:-}"
  local depth="${4:-1}"
  retry_clone "$url" "$dir" "$depth" "$branch_hint"
  timeout 30 git -C "$dir" fetch --prune --tags --depth "$depth" origin dev main release/1.0 ${branch_hint:+ "$branch_hint"}
  # Detach HEAD so we can force-update local branches safely.
  git -C "$dir" checkout --detach
  ensure_local_branch "$dir" dev
  ensure_local_branch "$dir" main
  ensure_local_branch "$dir" "release/1.0"
  if [[ -n "$branch_hint" ]]; then
    ensure_local_branch "$dir" "$branch_hint"
  fi
}

is_shallow_repo() {
  local repo="$1"
  if git -C "$repo" rev-parse --is-shallow-repository >/dev/null 2>&1; then
    [[ "$(git -C "$repo" rev-parse --is-shallow-repository)" == "true" ]]
  else
    [[ -f "$repo/.git/shallow" ]]
  fi
}

unshallow_repo() {
  local repo="$1"
  if is_shallow_repo "$repo"; then
    log "unshallow repo: $repo"
    git -C "$repo" fetch --unshallow --tags origin
  fi
}

checkout_ref() {
  local repo_dir="$1"
  local ref="$2"
  if git -C "$repo_dir" show-ref --verify --quiet "refs/remotes/origin/$ref"; then
    git -C "$repo_dir" checkout --detach "origin/$ref"
  else
    git -C "$repo_dir" checkout --detach "$ref"
  fi
}

get_sha() {
  local repo="$1"
  local ref="$2"
  if git -C "$repo" rev-parse --verify "$ref" >/dev/null 2>&1; then
    git -C "$repo" rev-parse "$ref"
  else
    log "warn: missing $repo $ref, falling back to HEAD"
    git -C "$repo" rev-parse HEAD
  fi
}

pick_ref() {
  local repo="$1"
  shift
  local ref
  for ref in "$@"; do
    if git -C "$repo" rev-parse --verify "$ref" >/dev/null 2>&1; then
      echo "$ref"
      return 0
    fi
  done
  echo "HEAD"
}

ensure_tool_version() {
  local cmd="$1"
  local expected="$2"
  local install_cmd="$3"
  local force="${4:-false}"

  if [[ "$force" == "true" ]] || ! command -v "$cmd" >/dev/null 2>&1; then
    log "installing $cmd ($expected)"
    eval "$install_cmd"
    return
  fi

  local current
  current="$($cmd --version 2>/dev/null | awk '{print $NF}')"
  current="${current#v}"
  if [[ "$current" != "$expected" ]]; then
    log "$cmd version mismatch: have $current, want $expected"
    eval "$install_cmd"
  fi
}

create_worktree() {
  local repo="$1"
  local dir="$2"
  local ref="$3"
  rm -rf "$dir"
  git -C "$repo" worktree add -f "$dir" "$ref"
}

find_std_doc_root() {
  local book_dir="$1"
  if [[ -d "$book_dir/stdlib/doc/libs" ]]; then
    echo "stdlib/doc/libs"
    return 0
  fi
  if [[ -d "$book_dir/stdlib/doc" ]]; then
    echo "stdlib/doc"
    return 0
  fi
  local doc_src
  doc_src="$(find "$book_dir" -type f -name summary_cjnative.md -print -quit || true)"
  if [[ -n "$doc_src" ]]; then
    echo "$(dirname "${doc_src#${book_dir}/}")"
    return 0
  fi
  doc_src="$(find "$book_dir" -type f -name SUMMARY.md -print -quit || true)"
  if [[ -n "$doc_src" ]]; then
    echo "$(dirname "${doc_src#${book_dir}/}")"
    return 0
  fi
  return 1
}

find_stdx_doc_root() {
  local book_dir="$1"
  if [[ -d "$book_dir/doc" ]]; then
    echo "doc"
    return 0
  fi
  local doc_src
  doc_src="$(find "$book_dir" -type f -name summary_cjnative.md -print -quit || true)"
  if [[ -n "$doc_src" ]]; then
    echo "$(dirname "${doc_src#${book_dir}/}")"
    return 0
  fi
  doc_src="$(find "$book_dir" -type f -name SUMMARY.md -print -quit || true)"
  if [[ -n "$doc_src" ]]; then
    echo "$(dirname "${doc_src#${book_dir}/}")"
    return 0
  fi
  return 1
}

copy_assets() {
  local book_dir="$1"
  mkdir -p "$book_dir/theme" "$book_dir/scripts"
  cp -r "$DOCS_ROOT/theme/." "$book_dir/theme/"
  find "$DOCS_ROOT/scripts" -maxdepth 1 -type f -print0 | xargs -0 -I{} cp -f {} "$book_dir/scripts/"
  cp -f "$DOCS_ROOT/book.toml" "$book_dir/book.toml"
}

set_book_src() {
  local book_toml="$1"
  local src="$2"
  # Pass values as argv to Python and use a quoted heredoc so the embedded Python code
  # is not subject to shell interpolation. This avoids NameError for `src`.
  python3 - "$book_toml" "$src" <<'PY'
from pathlib import Path
import sys
book_toml = sys.argv[1]
src = sys.argv[2]
p = Path(book_toml)
text = p.read_text()
text = text.replace('src = "src"', f'src = "{src}"')
p.write_text(text)
PY
}

normalize_summary() {
  local doc_root="$1"
  if [[ -f "$doc_root/summary_cjnative.md" ]]; then
    cp -f "$doc_root/summary_cjnative.md" "$doc_root/SUMMARY.md"
  fi
}

prepare_std_book() {
  local repo="$1"
  local worktree_dir="$2"
  local ref="$3"
  local doc_root="${4:-}"
  create_worktree "$repo" "$worktree_dir" "$ref"
  if [[ -z "$doc_root" ]]; then
    doc_root="$(find_std_doc_root "$worktree_dir" || true)"
  fi
  if [[ -z "$doc_root" ]]; then
    echo "stdlib doc not found in $worktree_dir" >&2
    exit 1
  fi
  rm -rf "$worktree_dir/$doc_root/std_en" || true
  rm -f "$worktree_dir/$doc_root/summary_cjnative_EN.md" || true
  normalize_summary "$worktree_dir/$doc_root"
  copy_assets "$worktree_dir"
  set_book_src "$worktree_dir/book.toml" "$doc_root"
}

prepare_stdx_book() {
  local repo="$1"
  local worktree_dir="$2"
  local ref="$3"
  local doc_root="${4:-}"
  create_worktree "$repo" "$worktree_dir" "$ref"
  if [[ -z "$doc_root" ]]; then
    doc_root="$(find_stdx_doc_root "$worktree_dir" || true)"
  fi
  if [[ -z "$doc_root" ]]; then
    echo "stdx doc not found in $worktree_dir" >&2
    exit 1
  fi
  normalize_summary "$worktree_dir/$doc_root"
  copy_assets "$worktree_dir"
  set_book_src "$worktree_dir/book.toml" "$doc_root"
}

build_book() {
  local book_dir="$1"
  local base_title="$2"
  local dest_dir="$3"
  local ts
  ts="$(TZ=Asia/Shanghai date +"%Y-%m-%d %H:%M")"
  (cd "$book_dir" && MDBOOK_BOOK__TITLE="$base_title $ts" mdbook build --dest-dir "$dest_dir")
  test -f "$dest_dir/index.html"
}

write_redirect() {
  local out_file="$1"
  local target="$2"
  local title="${3:-Redirecting…}"
  mkdir -p "$(dirname "$out_file")"
  cat > "$out_file" <<EOF
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="0; url=${target}">
    <script>location.replace("${target}");</script>
    <title>${title}</title>
  </head>
  <body>
    <a href="${target}">Go to docs</a>
  </body>
</html>
EOF
}