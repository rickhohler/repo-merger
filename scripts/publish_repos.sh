#!/usr/bin/env bash
set -euo pipefail

# Ensure every golden repo under the workspace publishes to the `gh_default` remote
# (creating the GitHub repo if needed) and optionally pushes the current branch.

usage() {
  cat <<EOF
Usage: $0 <workspace-root> [--remote-only] [--dry-run]

<workspace-root> must be the directory that contains the checked-out git repositories.
--remote-only  Skip pushing; only ensure the remote exists.
--dry-run      Show what would happen without creating repos, adding remotes, or pushing.
--limit <n>    Stop after the first <n> golden repositories are mirrored.
EOF
  exit 1
}

die() {
  echo "$*" >&2
  exit 1
}

if (( $# < 1 )); then
  usage
fi

workspace_root=$1
shift

remote_only=false
dry_run=false
limit=0
while (( $# )); do
  case $1 in
    --remote-only)
      remote_only=true
      shift
      ;;
    --dry-run)
      dry_run=true
      shift
      ;;
    --limit)
      shift
      if [[ -z $1 || $1 == --* ]]; then
        usage
      fi
      value=$1
      if [[ $value =~ ^[0-9]+$ ]]; then
        limit=$((value))
      else
        die "--limit requires a non-negative integer"
      fi
      shift
      ;;
    *) usage ;;
  esac
done

for tool in git gh; do
  command -v "$tool" >/dev/null 2>&1 || die "$tool is required but was not found in PATH"
done

[[ -d $workspace_root ]] || die "Workspace root not found: $workspace_root"

gh_user=$(gh api user --jq .login 2>/dev/null || true)
[[ -n $gh_user ]] || die "Unable to determine GitHub user via 'gh api user'"

remote_name="gh_default"
declare -i total_repos=0
declare -i repo_created=0
declare -i repo_created_dry=0
declare -i remote_added=0
declare -i remote_added_dry=0
declare -i remote_existing=0
declare -i pushed=0
declare -i pushed_dry=0
declare -i processed=0

squeeze_name() {
  local slug=$1
  slug="${slug//[^A-Za-z0-9._-]/-}"
  slug="${slug##-}"
  slug="${slug%%-}"
  echo "${slug:-repo}"
}

process_repo() {
  local repo_dir=$1
  local repo_slug=$2
  local repo_target="${gh_user}/${repo_slug}"
  local remote_url="git@github.com:${repo_target}.git"

  total_repos+=1

  local existing_remote
  if existing_remote=$(git -C "$repo_dir" remote get-url "$remote_name" 2>/dev/null); then
    if [[ $existing_remote == "$remote_url" ]]; then
      remote_existing+=1
      echo "[$repo_slug] $remote_name already configured as $existing_remote"
      return
    fi
    if [[ $dry_run == true ]]; then
      echo "[$repo_slug] DRY-RUN: would remove stale $remote_name remote ($existing_remote)"
    else
      git -C "$repo_dir" remote remove "$remote_name"
      echo "[$repo_slug] Removed stale $remote_name remote"
    fi
  fi

  if ! gh repo view "$repo_target" >/dev/null 2>&1; then
    if [[ $dry_run == true ]]; then
      repo_created_dry+=1
      echo "[$repo_slug] DRY-RUN: would create private repository $repo_target"
    else
      repo_created+=1
      gh repo create "$repo_target" --private --description "Workspace repo $repo_slug" --confirm
      echo "[$repo_slug] Created private repository $repo_target"
    fi
  else
    echo "[$repo_slug] Reusing existing GitHub repository $repo_target"
  fi

  if [[ $dry_run == true ]]; then
    remote_added_dry+=1
    echo "[$repo_slug] DRY-RUN: would add remote $remote_name -> $remote_url"
  else
      git -C "$repo_dir" remote add "$remote_name" "$remote_url"
      remote_added+=1
      echo "[$repo_slug] Added remote $remote_name -> $remote_url"
  fi
}

push_repo() {
  local repo_dir=$1
  local repo_slug
  repo_slug=$(basename "$(dirname "$repo_dir")")

  if [[ $dry_run == true ]]; then
    pushed_dry+=1
    echo "[$repo_slug] DRY-RUN: would mirror-push -> $remote_name"
  else
    local attempt=1
    local max_attempts=2
    local push_output

    while true; do
      if push_output=$(git -C "$repo_dir" push --mirror "$remote_name" 2>&1); then
        pushed+=1
        echo "[$repo_slug] Mirrored all refs to $remote_name"
        return
      fi

      printf "[$repo_slug] Push error (attempt %d): %s\n" "$attempt" "$push_output"
      if (( attempt >= max_attempts )); then
        die "[$repo_slug] git push --mirror failed after enabling lfs.allowincompletepush: $push_output"
      fi

      git -C "$repo_dir" config lfs.allowincompletepush true
      echo "[$repo_slug] Enabled git config lfs.allowincompletepush=true and retrying"
      attempt=$((attempt + 1))
    done
  fi
}


owner_repo_from_url() {
  local url=$1
  url="${url#git@github.com:}"
  url="${url#https://github.com/}"
  url="${url%.git}"
  owner="${url%%/*}"
  repo="${url##*/}"
  echo "$owner" "$repo"
}

for project_dir in "$workspace_root"/*; do
  [[ -d $project_dir ]] || continue
  golden_dir="$project_dir/golden"
  [[ -d $golden_dir ]] || continue
  origin_url=$(git -C "$golden_dir" remote get-url origin 2>/dev/null || true)
  if [[ -n $origin_url ]]; then
    read -r origin_owner origin_repo <<< "$(owner_repo_from_url "$origin_url")"
    if [[ -n $origin_owner && -n $origin_repo ]]; then
      if [[ $origin_owner == $gh_user ]]; then
        base_name="$origin_repo"
      else
        base_name="${origin_owner}-${origin_repo}"
      fi
    else
      base_name=$(basename "$project_dir")
    fi
  else
    base_name=$(basename "$project_dir")
  fi
  repo_slug=$(squeeze_name "$base_name")

  if ! git -C "$golden_dir" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "[$repo_slug] golden directory is not a git repository; skipping"
    continue
  fi

  if [[ $limit -gt 0 && $processed -ge $limit ]]; then
    echo "Reached limit of $limit repositories; stopping"
    break
  fi
  process_repo "$golden_dir" "$repo_slug"
  processed+=1

  if [[ $remote_only == false ]]; then
    push_repo "$golden_dir"
  fi
done

echo
echo "Workspace publish summary:"
printf "  Repos processed: %d\n" "$total_repos"
printf "  Repositories created: %d\n" "$repo_created"
[[ $dry_run == true ]] && printf "    (would create: %d)\n" "$repo_created_dry"
printf "  Remotes added: %d\n" "$remote_added"
[[ $dry_run == true ]] && printf "    (would add: %d)\n" "$remote_added_dry"
printf "  Remotes already present: %d\n" "$remote_existing"
if [[ $remote_only == true ]]; then
  echo "  Push step disabled (--remote-only)"
else
  printf "  Branches pushed: %d\n" "$pushed"
  [[ $dry_run == true ]] && printf "    (would push: %d)\n" "$pushed_dry"
fi
