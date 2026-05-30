#!/usr/bin/env bash
# Moonraker update_manager install_script for FilaMind Flow.
#
# Runs on the printer host after each git pull. It only refreshes the backend
# virtualenv — the UI ships pre-built in `frontend/dist` (so no Node is needed on
# the host), and Moonraker restarts the `filamind-flow` service itself via the
# `managed_services` setting. No sudo required.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR/backend"

[ -d .venv ] || python3 -m venv .venv
./.venv/bin/pip install -q -U pip
./.venv/bin/pip install -q -r requirements.txt

echo "FilaMind Flow: backend dependencies up to date."
