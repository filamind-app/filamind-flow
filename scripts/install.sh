#!/usr/bin/env bash
# FilaMind Flow — one-line installer for a Klipper / Moonraker host.
#
#   curl -fsSL https://raw.githubusercontent.com/filamind-app/filamind-flow/main/scripts/install.sh | bash
#
# Installs the backend service, serves the (pre-built) UI via nginx, adds a
# Mainsail sidebar entry, and registers FilaMind with Moonraker's update_manager
# for one-click updates. Re-runnable. Run as your normal printer user (not root).
set -euo pipefail

REPO="${FILAMIND_REPO:-https://github.com/filamind-app/filamind-flow.git}"
APP="${FILAMIND_DIR:-$HOME/filamind-flow}"
UI_PORT="${FILAMIND_UI_PORT:-8090}"
API_PORT="${FILAMIND_API_PORT:-8011}"
PRINTER_DATA="${PRINTER_DATA:-$HOME/printer_data}"
SERVICE="filamind-flow"

info() { printf '\n\033[1;33m==>\033[0m %s\n' "$*"; }

[ "$(id -u)" -eq 0 ] && { echo "Please run as your printer user, not root."; exit 1; }
for c in git python3 nginx; do command -v "$c" >/dev/null || { echo "Missing dependency: $c"; exit 1; }; done

info "Fetching FilaMind Flow into $APP"
if [ -d "$APP/.git" ]; then git -C "$APP" pull --ff-only; else git clone "$REPO" "$APP"; fi

info "Backend virtualenv"
cd "$APP/backend"
[ -d .venv ] || python3 -m venv .venv
./.venv/bin/pip install -q -U pip
./.venv/bin/pip install -q -r requirements.txt

info "systemd service (sudo)"
sudo tee /etc/systemd/system/${SERVICE}.service >/dev/null <<EOF
[Unit]
Description=FilaMind Flow backend (Klipper / Moonraker panel)
After=network-online.target moonraker.service
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP/backend
Environment=FILAMIND_HOST=127.0.0.1
Environment=FILAMIND_PORT=$API_PORT
Environment=FILAMIND_MOONRAKER_URL=http://127.0.0.1:7125
ExecStart=$APP/backend/.venv/bin/python -m app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now ${SERVICE}

info "nginx site on :$UI_PORT (sudo)"
sudo tee /etc/nginx/sites-available/${SERVICE} >/dev/null <<EOF
server {
    listen $UI_PORT;
    server_name _;
    root $APP/frontend/dist;
    index index.html;

    # Hashed build assets are immutable; index.html must always revalidate so a
    # new deploy is picked up immediately (never serve a stale bundle).
    location /assets/ { add_header Cache-Control "public, max-age=31536000, immutable"; }
    location = /index.html { add_header Cache-Control "no-cache"; }
    location / { try_files \$uri \$uri/ /index.html; }
    location /api/ { proxy_pass http://127.0.0.1:$API_PORT; proxy_set_header Host \$host; }

    location ~ ^/(server|printer|access|machine) {
        proxy_pass http://127.0.0.1:7125;
        proxy_set_header Host \$host;
        proxy_set_header Origin "";
    }
    location /websocket {
        proxy_pass http://127.0.0.1:7125;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header Origin "";
        proxy_read_timeout 86400;
    }
}
EOF
sudo ln -sf /etc/nginx/sites-available/${SERVICE} /etc/nginx/sites-enabled/${SERVICE}
sudo nginx -t && sudo systemctl reload nginx

info "Mainsail sidebar entry"
mkdir -p "$PRINTER_DATA/config/.theme"
# The sidebar link is a static URL, so it must point at a host every client can
# reach. Prefer an explicit FILAMIND_PUBLIC_HOST; otherwise the primary LAN IP,
# which resolves everywhere on the network — unlike <hostname>.local, which needs
# mDNS the client may not have (Windows w/o Bonjour, Android, other subnets, VPN).
# Fall back to the mDNS name only if no IP could be found.
NAVI_HOST="${FILAMIND_PUBLIC_HOST:-$(hostname -I 2>/dev/null | awk '{print $1}')}"
[ -n "$NAVI_HOST" ] || NAVI_HOST="$(hostname).local"
FILAMIND_NAVI_HOST="$NAVI_HOST" FILAMIND_UI_PORT="$UI_PORT" python3 - "$PRINTER_DATA/config/.theme/navi.json" <<'PY'
import json, os, sys
p = sys.argv[1]
data = []
if os.path.exists(p):
    try:
        with open(p) as f:
            data = json.load(f)
    except Exception:
        data = []
if not isinstance(data, list):
    data = []
data = [e for e in data if not (isinstance(e, dict) and e.get('title') == 'FilaMind Flow')]
host = os.environ.get('FILAMIND_NAVI_HOST', 'localhost')
port = os.environ.get('FILAMIND_UI_PORT', '8090')
data.append({
    "title": "FilaMind Flow",
    "href": "http://%s:%s" % (host, port),
    "target": "_blank",
    "icon": "M5 3h14v4h-10v3h8v4h-8v7h-4z",
    "position": 88,
})
with open(p, 'w') as f:
    json.dump(data, f, indent=2)
    f.write('\n')
print("   navi.json -> http://%s:%s  (override with FILAMIND_PUBLIC_HOST=<ip-or-host>)" % (host, port))
PY

info "Registering with Moonraker (update_manager + service allowlist)"
ASVC="$PRINTER_DATA/moonraker.asvc"
[ -f "$ASVC" ] && { grep -qx "$SERVICE" "$ASVC" || echo "$SERVICE" >> "$ASVC"; }
MCONF="$PRINTER_DATA/config/moonraker.conf"
if [ -f "$MCONF" ] && ! grep -q "update_manager $SERVICE" "$MCONF"; then
  cp "$MCONF" "$MCONF.bak.filamind.$(date +%s)"
  cat >> "$MCONF" <<'EOF'

[update_manager filamind-flow]
type: git_repo
path: ~/filamind-flow
origin: https://github.com/filamind-app/filamind-flow.git
primary_branch: main
managed_services: filamind-flow
install_script: deploy/install-host.sh
EOF
fi
sudo systemctl restart moonraker || true

info "Done."
echo "  Open:    http://$NAVI_HOST:$UI_PORT   (also in the Mainsail sidebar)"
echo "  Service: sudo systemctl status $SERVICE"
