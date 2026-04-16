#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/mdbook_lib.sh"

BUILD_DEV="${BUILD_DEV:-false}"
BUILD_MAIN="${BUILD_MAIN:-false}"
BUILD_VERSIONS="${BUILD_VERSIONS:-false}"
BUILD_PR="${BUILD_PR:-false}"

build_std_dev() {
  local std_ref
  std_ref="$(pick_ref ext_runtime dev origin/dev main origin/main HEAD)"
  prepare_std_book ext_runtime "$GITHUB_WORKSPACE/std_dev_book" "$std_ref" "stdlib/doc/libs"
  build_book "$GITHUB_WORKSPACE/std_dev_book" "Cangjie Std API (dev)" "$DEV_STD_OUT_DIR"
}

build_stdx_dev() {
  local stdx_ref
  stdx_ref="$(pick_ref ext_stdx dev origin/dev main origin/main HEAD)"
  prepare_stdx_book ext_stdx "$GITHUB_WORKSPACE/stdx_dev_book" "$stdx_ref" "doc"
  build_book "$GITHUB_WORKSPACE/stdx_dev_book" "Cangjie Stdx API (dev)" "$DEV_STDX_OUT_DIR"
}

build_std_main() {
  local std_ref
  std_ref="$(pick_ref ext_runtime main origin/main HEAD)"
  prepare_std_book ext_runtime "$GITHUB_WORKSPACE/std_main_book" "$std_ref" "stdlib/doc/libs"
  build_book "$GITHUB_WORKSPACE/std_main_book" "Cangjie Std API (main)" "$MAIN_STD_OUT_DIR"
}

build_stdx_main() {
  local stdx_ref
  stdx_ref="$(pick_ref ext_stdx main origin/main HEAD)"
  prepare_stdx_book ext_stdx "$GITHUB_WORKSPACE/stdx_main_book" "$stdx_ref" "doc"
  build_book "$GITHUB_WORKSPACE/stdx_main_book" "Cangjie Stdx API (main)" "$MAIN_STDX_OUT_DIR"
}

build_version_branch() {
  local branch="$1"
  local version_root="$GITHUB_WORKSPACE/book/$branch"
  local std_out_dir="$version_root/std"
  local stdx_out_dir="$version_root/stdx"
  local std_ref
  local stdx_ref

  std_ref="$(pick_ref ext_runtime "$branch" "origin/$branch" main origin/main HEAD)"
  stdx_ref="$(pick_ref ext_stdx "$branch" "origin/$branch" main origin/main HEAD)"
  prepare_std_book ext_runtime "$GITHUB_WORKSPACE/std_${branch//\//_}_book" "$std_ref" ""
  build_book "$GITHUB_WORKSPACE/std_${branch//\//_}_book" "Cangjie Std API ($branch)" "$std_out_dir"
  prepare_stdx_book ext_stdx "$GITHUB_WORKSPACE/stdx_${branch//\//_}_book" "$stdx_ref" ""
  build_book "$GITHUB_WORKSPACE/stdx_${branch//\//_}_book" "Cangjie Stdx API ($branch)" "$stdx_out_dir"
}

build_std_pr() {
  prepare_std_book ext_runtime "$GITHUB_WORKSPACE/std_pr_book" "HEAD" "stdlib/doc/libs"
  build_book "$GITHUB_WORKSPACE/std_pr_book" "Cangjie Std API (pr ${PR_ID})" "$PR_STD_OUT_DIR"
}

build_stdx_pr() {
  prepare_stdx_book ext_stdx "$GITHUB_WORKSPACE/stdx_pr_book" "HEAD" "doc"
  build_book "$GITHUB_WORKSPACE/stdx_pr_book" "Cangjie Stdx API (pr ${PR_ID})" "$PR_STDX_OUT_DIR"
}

write_redirects() {
  local book_root="$GITHUB_WORKSPACE/book"
  mkdir -p "$book_root"
  write_redirect "$book_root/index.html" "./dev/std/" "Redirecting…"
  write_redirect "$book_root/dev/index.html" "./std/" "Redirecting…"
  write_redirect "$book_root/main/index.html" "./std/" "Redirecting…"
  while IFS= read -r branch; do
    [[ -n "$branch" ]] || continue
    write_redirect "$book_root/$branch/index.html" "./std/" "Redirecting…"
  done <<< "${VERSION_BRANCHES:-}"

  if [[ "${BUILD_PR}" == "true" ]]; then
    mkdir -p "$PR_OUT_ROOT"
    write_redirect "$PR_OUT_ROOT/index.html" "./std/" "Redirecting…"
    date +%s > "$PR_OUT_ROOT/.stamp"
  fi
}

assert_outputs() {
  test -d "$GITHUB_WORKSPACE/book"
  test -f "$DEV_STD_OUT_DIR/index.html" || (echo "dev std index.html missing" && exit 2)
  test -f "$DEV_STD_OUT_DIR/docs-index.json" || (echo "dev std docs-index.json missing" && exit 2)
  test -f "$DEV_STDX_OUT_DIR/index.html" || (echo "dev stdx index.html missing" && exit 2)
  test -f "$DEV_STDX_OUT_DIR/docs-index.json" || (echo "dev stdx docs-index.json missing" && exit 2)
  test -f "$MAIN_STD_OUT_DIR/index.html" || (echo "main std index.html missing" && exit 2)
  test -f "$MAIN_STD_OUT_DIR/docs-index.json" || (echo "main std docs-index.json missing" && exit 2)
  test -f "$MAIN_STDX_OUT_DIR/index.html" || (echo "main stdx index.html missing" && exit 2)
  test -f "$MAIN_STDX_OUT_DIR/docs-index.json" || (echo "main stdx docs-index.json missing" && exit 2)
  while IFS= read -r branch; do
    [[ -n "$branch" ]] || continue
    test -f "$GITHUB_WORKSPACE/book/$branch/std/index.html" || (echo "$branch std index.html missing" && exit 2)
    test -f "$GITHUB_WORKSPACE/book/$branch/std/docs-index.json" || (echo "$branch std docs-index.json missing" && exit 2)
    test -f "$GITHUB_WORKSPACE/book/$branch/stdx/index.html" || (echo "$branch stdx index.html missing" && exit 2)
    test -f "$GITHUB_WORKSPACE/book/$branch/stdx/docs-index.json" || (echo "$branch stdx docs-index.json missing" && exit 2)
  done <<< "${VERSION_BRANCHES:-}"
  grep -nE 'pagetoc\.(js|css)' "$DEV_STD_OUT_DIR/index.html" || echo 'pagetoc asset missing'
  find "$GITHUB_WORKSPACE/book" -path '*/theme/pagetoc.*' -print || echo 'theme/pagetoc.* missing'
  grep -nE 'class="pagetoc|id="pagetoc' "$DEV_STD_OUT_DIR/index.html" || echo 'pagetoc container missing'
  find "$GITHUB_WORKSPACE/book" -maxdepth 5 -type f -name 'toc.js' -print
  if [[ "${BUILD_PR}" == "true" ]]; then
    test -f "$PR_STD_OUT_DIR/index.html" || (echo "pr std index.html missing" && exit 2)
    test -f "$PR_STD_OUT_DIR/docs-index.json" || (echo "pr std docs-index.json missing" && exit 2)
    test -f "$PR_STDX_OUT_DIR/index.html" || (echo "pr stdx index.html missing" && exit 2)
    test -f "$PR_STDX_OUT_DIR/docs-index.json" || (echo "pr stdx docs-index.json missing" && exit 2)
    test -f "$PR_OUT_ROOT/.stamp" || (echo "pr stamp missing" && exit 2)
  fi
}

main() {
  if [[ "${BUILD_DEV}" == "true" ]]; then
    build_std_dev
    build_stdx_dev
  fi
  if [[ "${BUILD_MAIN}" == "true" ]]; then
    build_std_main
    build_stdx_main
  fi
  if [[ "${BUILD_VERSIONS}" == "true" ]]; then
    while IFS= read -r branch; do
      [[ -n "$branch" ]] || continue
      build_version_branch "$branch"
    done <<< "${VERSION_BRANCHES:-}"
  fi
  if [[ "${BUILD_PR}" == "true" ]]; then
    build_std_pr
    build_stdx_pr
  fi

  write_redirects
  assert_outputs
}

main "$@"
