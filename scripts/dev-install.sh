#!/bin/bash
# Install all three packages in editable mode for development.
# Order matters: core first (others depend on it).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${REPO_ROOT}/.venv"

if [ ! -d "$VENV" ]; then
    echo "Error: .venv not found. Create it first: python3 -m venv .venv"
    exit 1
fi

PIP="${VENV}/bin/pip"

echo "→ Installing cited-core..."
$PIP install -e "${REPO_ROOT}/packages/core"

echo "→ Installing cited-mcp..."
$PIP install -e "${REPO_ROOT}/packages/mcp"

echo "→ Installing cited-cli with dev dependencies..."
$PIP install -e "${REPO_ROOT}[dev]"

echo "✓ All packages installed in editable mode."
