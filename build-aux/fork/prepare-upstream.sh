#!/usr/bin/env bash
# Run on a full master checkout of one fork. Each runner can write only to its own fork.
set -euo pipefail

studio=Huihuing/obs-studio
browser=Huihuing/obs-browser
repo=${GITHUB_REPOSITORY:?}
case "$repo" in "$studio"|"$browser") ;; *) exit 1 ;; esac
tag=$(gh api repos/obsproject/obs-studio/releases/latest --jq .tag_name)
[[ $tag =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "Unexpected stable release tag: $tag"; exit 1; }
branch="sync/obs-$tag"
existing=$(gh pr list --repo "$repo" --base master --head "$branch" --state all --json number --jq 'length')
if [[ $existing != 0 ]]; then
    echo "A PR for $tag already exists in $repo."
    exit 0
fi

# Recover if the branch push succeeded on a previous run but PR creation failed.
remote_branch=$(git ls-remote --heads origin "refs/heads/$branch")
if [[ -z $remote_branch ]]; then
    if [[ $repo == "$browser" ]]; then
        target=$(gh api "repos/obsproject/obs-studio/contents/plugins/obs-browser?ref=$tag" --jq .sha)
        git fetch --no-tags https://github.com/obsproject/obs-browser.git "$target"
    else
        git fetch --no-tags https://github.com/obsproject/obs-studio.git "refs/tags/$tag"
        target=$(git rev-parse 'FETCH_HEAD^{commit}')
    fi
    if git merge-base --is-ancestor "$target" HEAD; then
        echo "$repo already includes the upstream commit for $tag."
        exit 0
    fi

    if [[ $repo == "$studio" ]]; then
        old_pin=$(git rev-parse HEAD:plugins/obs-browser)
        required_pin=$(git rev-parse "$target:plugins/obs-browser")
        temp=$(mktemp -d)
        trap 'rm -rf -- "$temp"' EXIT
        git clone --quiet --single-branch --branch master --filter=blob:none --no-checkout \
            "https://github.com/$browser.git" "$temp/browser"
        pin=$(git -C "$temp/browser" rev-parse HEAD)
        git -C "$temp/browser" fetch --no-tags https://github.com/obsproject/obs-browser.git "$required_pin"
        git -C "$temp/browser" merge-base --is-ancestor "$old_pin" "$pin" || {
            echo "Browser master does not include the current Studio pin $old_pin."; exit 1;
        }
        if ! git -C "$temp/browser" merge-base --is-ancestor "$required_pin" "$pin"; then
            echo "Waiting for $browser to merge $required_pin for $tag."
            exit 0
        fi
    fi

    git config user.name 'github-actions[bot]'
    git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
    git switch -c "$branch"
    if ! git merge --no-ff --no-commit "$target"; then
        conflicts=$(git diff --name-only --diff-filter=U)
        if [[ $repo != "$studio" || $conflicts != plugins/obs-browser ]]; then
            echo "Manual merge required for $tag. Conflicting paths: $conflicts"
            git merge --abort || true
            exit 1
        fi
    fi
    if [[ $repo == "$studio" ]]; then
        git config -f .gitmodules submodule.plugins/obs-browser.url "https://github.com/$browser.git"
        git add .gitmodules
        git update-index --add --cacheinfo "160000,$pin,plugins/obs-browser"
    fi
    git diff --cached --check
    git commit -m "Merge upstream changes for OBS $tag"
    git push origin "HEAD:refs/heads/$branch"
fi
gh pr create --repo "$repo" --base master --head "$branch" --draft \
    --title "Sync upstream OBS $tag" \
    --body "Review the merge, preserve its ancestry with a merge commit, and verify the custom browser in the paired Studio build. Upstream release: https://github.com/obsproject/obs-studio/releases/tag/$tag"
