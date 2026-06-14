#!/usr/bin/env bash
# Moonraker update_manager install_script hook for FilaMind Flow.
#
# This is the entry Moonraker runs after each git pull (referenced as `install_script:
# deploy/install-host.sh` in moonraker.conf). It just delegates to the single installer's `update`
# step, which refreshes the backend virtualenv. The UI ships pre-built in `frontend/dist` (no Node
# on the host) and Moonraker restarts the service itself, so nothing else is needed here. No sudo.
set -euo pipefail
exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/scripts/install.sh" update
