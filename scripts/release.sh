#!/usr/bin/env bash
#
# release.sh — Bump version, tag, push, and update the Homebrew tap formula.
#
# Usage:
#   ./scripts/release.sh <new_version>
#
# Example:
#   ./scripts/release.sh 0.3.2
#
# What it does:
#   1. Validates the version argument and checks for clean git state
#   2. Bumps version in all pyproject.toml files and cited_core/__init__.py
#   3. Commits the version bump and creates a git tag (v<version>)
#   4. Pushes the commit and tag to origin (triggers GitHub Actions release)
#   5. Waits for the GitHub release to create the tarball
#   6. Regenerates the Homebrew formula with updated URL, SHA256, and dependency resources
#   7. Commits and pushes the formula update to homebrew-cited
#
# Prerequisites:
#   - Clean working tree in cited-cli (no uncommitted changes)
#   - gh CLI authenticated (for release polling)
#   - Python venv at .venv with cited-cli installed in editable mode
#   - homebrew-cited repo cloned at ~/repos/homebrew-cited
#
set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
CLI_REPO="$(cd "$(dirname "$0")/.." && pwd)"
TAP_REPO="$HOME/repos/homebrew-cited"
FORMULA="$TAP_REPO/Formula/cited.rb"
GITHUB_REPO="YouCited/cited-cli"
VENV="$CLI_REPO/.venv"

# Version files (single source of truth + mirrors)
VERSION_SOURCE="$CLI_REPO/packages/core/src/cited_core/__init__.py"
PYPROJECT_ROOT="$CLI_REPO/pyproject.toml"
PYPROJECT_CORE="$CLI_REPO/packages/core/pyproject.toml"
PYPROJECT_MCP="$CLI_REPO/packages/mcp/pyproject.toml"

# ── Helpers ───────────────────────────────────────────────────────────────────
die()  { echo "Error: $*" >&2; exit 1; }
info() { echo "→ $*"; }

# ── Validate args ─────────────────────────────────────────────────────────────
VERSION="${1:-}"
[[ -z "$VERSION" ]] && die "Usage: $0 <new_version>  (e.g. 0.3.2)"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "Version must be semver (e.g. 0.3.2)"
TAG="v$VERSION"

# ── Pre-flight checks ────────────────────────────────────────────────────────
cd "$CLI_REPO"
[[ -d "$TAP_REPO" ]]    || die "Homebrew tap repo not found at $TAP_REPO"
[[ -f "$FORMULA" ]]      || die "Formula not found at $FORMULA"
[[ -d "$VENV" ]]         || die "Python venv not found at $VENV"
command -v gh &>/dev/null || die "gh CLI not found — install with: brew install gh"

if ! git diff --quiet || ! git diff --cached --quiet; then
    die "Working tree is not clean. Commit or stash changes first."
fi

CURRENT_BRANCH=$(git branch --show-current)
[[ "$CURRENT_BRANCH" == "main" ]] || die "Must be on main branch (currently on $CURRENT_BRANCH)"

git fetch origin --tags
if git tag -l "$TAG" | grep -q "$TAG"; then
    die "Tag $TAG already exists"
fi

# ── Step 1: Bump version ─────────────────────────────────────────────────────
info "Bumping version to $VERSION"

# Single source of truth
sed -i '' "s/^__version__ = \".*\"/__version__ = \"$VERSION\"/" "$VERSION_SOURCE"
grep -q "__version__ = \"$VERSION\"" "$VERSION_SOURCE" || die "Failed to update $VERSION_SOURCE"

# Mirror in all pyproject.toml files
for pyp in "$PYPROJECT_ROOT" "$PYPROJECT_CORE" "$PYPROJECT_MCP"; do
    sed -i '' "s/^version = \".*\"/version = \"$VERSION\"/" "$pyp"
    grep -q "version = \"$VERSION\"" "$pyp" || die "Failed to update $pyp"
done

# Also update cited-core dependency pins in mcp and cli pyproject.toml
sed -i '' "s/\"cited-core>=.*\"/\"cited-core>=$VERSION\"/" "$PYPROJECT_ROOT" "$PYPROJECT_MCP"
sed -i '' "s/\"cited-mcp>=.*\"/\"cited-mcp>=$VERSION\"/" "$PYPROJECT_ROOT"

info "Version bumped in 4 files"

# ── Step 2: Commit and tag ────────────────────────────────────────────────────
info "Committing version bump and creating tag $TAG"

git add "$VERSION_SOURCE" "$PYPROJECT_ROOT" "$PYPROJECT_CORE" "$PYPROJECT_MCP"
git commit -m "chore: bump version to $VERSION"
git tag "$TAG"

# ── Step 3: Push ──────────────────────────────────────────────────────────────
info "Pushing commit and tag to origin"
git push origin main
git push origin "$TAG"

# ── Step 4: Wait for GitHub release ───────────────────────────────────────────
info "Waiting for GitHub release $TAG to be created..."
TARBALL_URL="https://github.com/$GITHUB_REPO/archive/refs/tags/$TAG.tar.gz"

for i in $(seq 1 30); do
    if gh release view "$TAG" --repo "$GITHUB_REPO" &>/dev/null; then
        info "Release $TAG found"
        break
    fi
    if [[ $i -eq 30 ]]; then
        die "Timed out waiting for release $TAG (5 minutes). Check GitHub Actions."
    fi
    sleep 10
done

# ── Step 5: Compute tarball SHA256 ────────────────────────────────────────────
info "Downloading tarball and computing SHA256"

TMPDIR_RELEASE=$(mktemp -d)
trap 'rm -rf "$TMPDIR_RELEASE"' EXIT

curl -sL "$TARBALL_URL" -o "$TMPDIR_RELEASE/source.tar.gz"
TARBALL_SHA=$(shasum -a 256 "$TMPDIR_RELEASE/source.tar.gz" | awk '{print $1}')
info "SHA256: $TARBALL_SHA"

# ── Step 6: Generate dependency resources ─────────────────────────────────────
info "Resolving Python dependencies and generating resource blocks"

# Install the new version into a temp venv to get exact resolved deps
TMPVENV="$TMPDIR_RELEASE/venv"
"$VENV/bin/python" -m venv "$TMPVENV"
"$TMPVENV/bin/pip" install --quiet --upgrade pip

# Install cited-cli from the tarball to get exact dependency resolution
"$TMPVENV/bin/pip" install --quiet "$TMPDIR_RELEASE/source.tar.gz"

# Generate resource blocks from installed packages
"$TMPVENV/bin/python" -c "
import importlib.metadata
import json
import sys
import urllib.request

# Get all installed packages except cited-cli itself, pip, setuptools, wheel.
# cited-core is NOT skipped — it's a sibling PyPI package that the brew venv
# must install alongside cited-cli (otherwise import fails on first run).
skip = {'cited-cli', 'pip', 'setuptools', 'wheel', 'pkg_resources'}
packages = []
for dist in importlib.metadata.distributions():
    name = dist.metadata['Name']
    if name.lower() in skip or name.lower().replace('-', '_') in {s.replace('-', '_') for s in skip}:
        continue
    version = dist.metadata['Version']
    packages.append((name, version))

packages.sort(key=lambda x: x[0].lower())

for name, version in packages:
    url = f'https://pypi.org/pypi/{name}/{version}/json'
    try:
        with urllib.request.urlopen(url) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f'# WARNING: Could not fetch {name}=={version}: {e}', file=sys.stderr)
        continue

    sdist = None
    for u in data['urls']:
        if u['packagetype'] == 'sdist':
            sdist = u
            break

    if not sdist:
        print(f'# WARNING: No sdist found for {name}=={version}', file=sys.stderr)
        continue

    resource_name = name.lower().replace('_', '-').replace('.', '-')
    print(f'  resource \"{resource_name}\" do')
    print(f'    url \"{sdist[\"url\"]}\"')
    print(f'    sha256 \"{sdist[\"digests\"][\"sha256\"]}\"')
    print(f'  end')
    print()
" > "$TMPDIR_RELEASE/resources.rb"

RESOURCE_COUNT=$(grep -c 'resource "' "$TMPDIR_RELEASE/resources.rb" || true)
info "Generated $RESOURCE_COUNT resource blocks"

[[ "$RESOURCE_COUNT" -gt 0 ]] || die "No resource blocks generated — something went wrong"

# ── Step 7: Rebuild the formula ───────────────────────────────────────────────
info "Writing updated formula"

cat > "$FORMULA" << RUBY
class Cited < Formula
  include Language::Python::Virtualenv

  desc "CLI for the Cited GEO platform"
  homepage "https://youcited.com"
  url "$TARBALL_URL"
  sha256 "$TARBALL_SHA"
  license "Proprietary"

  depends_on "python@3.12"
  depends_on "rust" => :build

$(cat "$TMPDIR_RELEASE/resources.rb")
  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "cited-cli", shell_output("#{bin}/cited version")
  end
end
RUBY

# ── Step 8: Commit and push the tap ──────────────────────────────────────────
info "Committing and pushing formula update to homebrew-cited"

cd "$TAP_REPO"

if ! git diff --quiet "$FORMULA"; then
    git add "$FORMULA"
    git commit -m "formula: update cited to $TAG"
    git push origin main
    info "Homebrew tap updated"
else
    info "Formula unchanged — nothing to push"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "✓ Release $TAG complete!"
echo ""
echo "  PyPI:           cited-core, cited-mcp, cited-cli published (via GitHub Actions)"
echo "  GitHub:         $TAG pushed, release created"
echo "  Homebrew:       formula updated to $TAG"
echo ""
echo "  Users can now run:"
echo "    brew update && brew upgrade cited"
echo "    pip install --upgrade cited-cli"
echo "    uvx cited-mcp  # auto-updates"
