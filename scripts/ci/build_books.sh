#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/mdbook_lib.sh"

BUILD_DEV="${BUILD_DEV:-false}"
BUILD_MAIN="${BUILD_MAIN:-false}"
BUILD_RELEASE="${BUILD_RELEASE:-false}"
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

build_std_release() {
  local std_ref
  std_ref="$(pick_ref ext_runtime release/1.0 origin/release/1.0 main origin/main HEAD)"
  prepare_std_book ext_runtime "$GITHUB_WORKSPACE/std_release_book" "$std_ref" ""
  build_book "$GITHUB_WORKSPACE/std_release_book" "Cangjie Std API (release/1.0)" "$RELEASE_STD_OUT_DIR"
}

build_stdx_release() {
  local stdx_ref
  stdx_ref="$(pick_ref ext_stdx release/1.0 origin/release/1.0 main origin/main HEAD)"
  prepare_stdx_book ext_stdx "$GITHUB_WORKSPACE/stdx_release_book" "$stdx_ref" ""
  build_book "$GITHUB_WORKSPACE/stdx_release_book" "Cangjie Stdx API (release/1.0)" "$RELEASE_STDX_OUT_DIR"
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
  write_redirect "$book_root/release/1.0/index.html" "./std/" "Redirecting…"

  if [[ "${BUILD_PR}" == "true" ]]; then
    mkdir -p "$PR_OUT_ROOT"
    write_redirect "$PR_OUT_ROOT/index.html" "./std/" "Redirecting…"
    date +%s > "$PR_OUT_ROOT/.stamp"
  fi
}

assert_outputs() {
  test -d "$GITHUB_WORKSPACE/book"
  test -f "$DEV_STD_OUT_DIR/index.html" || (echo "dev std index.html missing" && exit 2)
  test -f "$DEV_STDX_OUT_DIR/index.html" || (echo "dev stdx index.html missing" && exit 2)
  test -f "$MAIN_STD_OUT_DIR/index.html" || (echo "main std index.html missing" && exit 2)
  test -f "$MAIN_STDX_OUT_DIR/index.html" || (echo "main stdx index.html missing" && exit 2)
  test -f "$RELEASE_STD_OUT_DIR/index.html" || (echo "release std index.html missing" && exit 2)
  test -f "$RELEASE_STDX_OUT_DIR/index.html" || (echo "release stdx index.html missing" && exit 2)
  grep -nE 'pagetoc\.(js|css)' "$DEV_STD_OUT_DIR/index.html" || echo 'pagetoc asset missing'
  find "$GITHUB_WORKSPACE/book" -path '*/theme/pagetoc.*' -print || echo 'theme/pagetoc.* missing'
  grep -nE 'class="pagetoc|id="pagetoc' "$DEV_STD_OUT_DIR/index.html" || echo 'pagetoc container missing'
  find "$GITHUB_WORKSPACE/book" -maxdepth 5 -type f -name 'toc.js' -print
  if [[ "${BUILD_PR}" == "true" ]]; then
    test -f "$PR_STD_OUT_DIR/index.html" || (echo "pr std index.html missing" && exit 2)
    test -f "$PR_STDX_OUT_DIR/index.html" || (echo "pr stdx index.html missing" && exit 2)
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
  if [[ "${BUILD_RELEASE}" == "true" ]]; then
    build_std_release
    build_stdx_release
  fi
  if [[ "${BUILD_PR}" == "true" ]]; then
    build_std_pr
    build_stdx_pr
  fi

  write_redirects
  assert_outputs
}

main "$@"
