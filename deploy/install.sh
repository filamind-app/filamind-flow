#!/usr/bin/env bash
# FilaMind Flow installer / updater.
# Builds the frontend, installs backend dependencies, and reports next steps.
# Safe to re-run (used by Moonraker's update_manager install_script).
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Building frontend"
cd "${REPO_DIR}/frontend"
npm ci
npm run build

echo "==> Installing backend"
cd "${REPO_DIR}/backend"
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt

echo "==> Done."
echo "    Restart the service: sudo systemctl restart filamind-flow"
