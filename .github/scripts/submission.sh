#!/usr/bin/env bash
# Turn an editor submission issue into a pull request.
# runs at the repository root, on the base branch.
# env: GITHUB_EVENT_PATH, GH_TOKEN, GH_REPO, PYTHON, SUBMISSION_*.
set -euo pipefail

python="${PYTHON:-python}"
event="${GITHUB_EVENT_PATH:?GITHUB_EVENT_PATH names no issues event}"
marker='<!-- gen3tl-submission -->'
out="$(mktemp -d)"
trap 'rm -rf "$out"' EXIT

remote() {
  if [ -n "${SUBMISSION_DRY_RUN:-}" ]; then
    printf 'dry run:' >&2
    printf ' %q' "$@" >&2
    printf '\n' >&2
  else
    "$@"
  fi
}

# Exit 1 means refused; the status file tells.
"$python" -m gen3tl web submission --event "$event" --out "$out" || true
status="$(cat "$out/status" 2>/dev/null || true)"
case "$status" in
  valid | invalid) ;;
  *)
    printf '%s\n' "submission: web submission wrote no status" >&2
    exit 1
    ;;
esac
number="$(cat "$out/issue")"
if [ "$status" = invalid ]; then
  remote gh issue comment "$number" --body-file "$out/comment.md"
  exit 0
fi

profile="$(cat "$out/profile")"
language="$(cat "$out/language")"
# rendering the site catalog checks it
if [ "$profile" = site ]; then
  check=(web site-catalog --data "$out/site-data")
  checked="the site catalog check (web site-catalog)"
else
  check=(--profile "$profile" --lang "$language" check po)
  checked="check po"
fi
if ! "$python" -m gen3tl "${check[@]}" >"$out/po-check.txt" 2>&1; then
  # an added picture is not in HEAD: remove it
  while IFS= read -r file; do
    if git cat-file -e "HEAD:$file" 2>/dev/null; then
      git restore --source=HEAD --worktree -- "$file"
    else
      rm -f -- "$file"
    fi
  done <"$out/files"
  {
    printf '%s\n' "$marker" "This submission cannot be applied: $checked fails on the changed catalog." ""
    printf '%s\n' '```'
    tail -n 40 "$out/po-check.txt"
    printf '%s\n' '```'
  } >"$out/comment.md"
  remote gh issue comment "$number" --body-file "$out/comment.md"
  exit 0
fi

rules="$(cat "$out/rules")"
proposals="$(cat "$out/note-proposals")"
if [ "$rules" -gt 0 ] || [ "$proposals" -gt 0 ]; then
  "$python" -m gen3tl check pr --base HEAD --out "$out/check" >"$out/pr-check.txt" 2>&1 || true
  if [ ! -s "$out/check/report.md" ]; then
    printf '%s\n' 'submission: missing review report' >&2
    exit 1
  fi
  cat "$out/check/report.md" >>"$out/pr.md"
fi

base="${SUBMISSION_BASE:-$(git rev-parse --abbrev-ref HEAD)}"
branch="submission/$number"
title="$(cat "$out/title")"
git checkout -q -B "$branch"
if [ -n "$(cat "$out/index")" ]; then
  "$python" -m gen3tl --profile "$profile" --lang "$language" lang index
fi
git add --pathspec-from-file="$out/files"
git -c user.name='github-actions[bot]' \
  -c user.email='41898282+github-actions[bot]@users.noreply.github.com' \
  commit -q -F "$out/commit.txt"
# The branch belongs to the issue; edits replace it.
remote git push --force origin "HEAD:refs/heads/$branch"
existing="$(remote gh pr list --head "$branch" --base "$base" --state open --json url --jq '.[0].url // empty')"
if [ -n "$existing" ]; then
  remote gh pr edit "$existing" --title "$title" --body-file "$out/pr.md"
  if { [ "$rules" -gt 0 ] || [ "$proposals" -gt 0 ]; } && [ "$(remote gh pr view "$existing" --json isDraft --jq '.isDraft')" = false ]; then
    remote gh pr ready "$existing" --undo
  fi
  url="$existing"
else
  draft=()
  if [ "$rules" -gt 0 ] || [ "$proposals" -gt 0 ]; then draft=(--draft); fi
  url="$(remote gh pr create --base "$base" --head "$branch" --title "$title" --body-file "$out/pr.md" ${draft[@]+"${draft[@]}"})"
fi
{
  printf '%s\n' "$marker" "Pull request ${url:-(dry run)} applies the $(cat "$out/summary")." ""
  printf '%s\n' "Edit the issue to change the submission; the pull request follows the edit."
  # Empty without notes: no section.
  if [ -s "$out/notes.md" ]; then
    printf '\n'
    cat "$out/notes.md"
  fi
} >"$out/answer.md"
remote gh issue comment "$number" --body-file "$out/answer.md"
git checkout -q "$base"
printf 'submission: #%s -> %s\n' "$number" "${url:-(dry run)}"
