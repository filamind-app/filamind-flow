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
    # Resonance captures move the toolhead for minutes (belt comparison = two sweeps;
    # vibrations profile longer), so raise nginx's 60s default read timeout or they 504.
    location /api/ {
        proxy_pass http://127.0.0.1:$API_PORT;
        proxy_set_header Host \$host;
        proxy_read_timeout 1200s;
        proxy_send_timeout 1200s;
    }

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

info "Subpath integration on the host's primary web server"
# Expose FilaMind under /filamind/ on whatever server already answers on :80 (Mainsail /
# Fluidd). That server is the one a remote reverse proxy or a Cloudflare tunnel already
# forwards, so the panel becomes reachable on LAN, by IP, AND through the tunnel with ONE
# host-relative link — no extra port to expose, no mDNS. The marker-guarded block proxies
# the whole subtree to the panel's own :$UI_PORT nginx (which routes assets / API /
# websocket), so nothing about the panel's serving changes. Falls back gracefully: if no
# primary :80 site is found, the sidebar link stays an absolute host:port URL.
SUBPATH_OK=0
PRIMARY_SITE=""
for cand in /etc/nginx/sites-enabled/mainsail /etc/nginx/sites-enabled/fluidd /etc/nginx/sites-enabled/*; do
  [ -f "$cand" ] || continue
  if grep -qE 'listen[[:space:]]+(\[::\]:)?80([[:space:]];]|;|[[:space:]])' "$cand" 2>/dev/null; then
    PRIMARY_SITE="$(readlink -f "$cand")"; break
  fi
done
if [ -n "$PRIMARY_SITE" ]; then
  if FILAMIND_UI_PORT="$UI_PORT" python3 - "$PRIMARY_SITE" <<'PY'
import os, re, sys, time
path = sys.argv[1]
port = os.environ.get('FILAMIND_UI_PORT', '8090')
src = open(path).read()
if 'filamind-flow subpath' in src:
    sys.exit(0)  # already integrated
# Find the first server { ... } block that listens on :80 and insert our location after its '{'.
m = re.search(r'server\s*\{', src)
if not m:
    sys.exit(2)
block = (
    "\n    # >>> filamind-flow subpath >>>\n"
    "    location ^~ /filamind/ {\n"
    "        proxy_pass http://127.0.0.1:%s/;\n"
    "        proxy_http_version 1.1;\n"
    "        proxy_set_header Host $host;\n"
    "        proxy_set_header Upgrade $http_upgrade;\n"
    '        proxy_set_header Connection $connection_upgrade;\n'
    "        proxy_set_header X-Forwarded-Proto $scheme;\n"
    "        proxy_read_timeout 1200s;\n"
    "        proxy_send_timeout 1200s;\n"
    "    }\n"
    "    location = /filamind { return 301 /filamind/; }\n"
    "    # <<< filamind-flow subpath <<<\n" % port
)
out = src[: m.end()] + block + src[m.end() :]
open(path + '.bak.filamind.' + str(int(time.time())), 'w').write(src)
open(path, 'w').write(out)
print('   integrated /filamind/ into %s' % path)
PY
  then
    if sudo nginx -t 2>/dev/null; then sudo systemctl reload nginx && SUBPATH_OK=1; fi
  fi
fi

info "Mainsail sidebar entry"
mkdir -p "$PRINTER_DATA/config/.theme"
# Prefer the host-relative /filamind/ link (works on LAN, by IP, and through a tunnel) when
# the subpath integration succeeded. Otherwise fall back to an absolute host:port URL —
# an explicit FILAMIND_PUBLIC_HOST, else the primary LAN IP (resolves everywhere on the
# network, unlike <hostname>.local which needs mDNS the client may lack).
if [ "$SUBPATH_OK" = 1 ]; then
  NAVI_HREF="/filamind/"; NAVI_TARGET="_self"
else
  NAVI_HOST="${FILAMIND_PUBLIC_HOST:-$(hostname -I 2>/dev/null | awk '{print $1}')}"
  [ -n "$NAVI_HOST" ] || NAVI_HOST="$(hostname).local"
  NAVI_HREF="http://$NAVI_HOST:$UI_PORT"; NAVI_TARGET="_blank"
fi
FILAMIND_NAVI_HREF="$NAVI_HREF" FILAMIND_NAVI_TARGET="$NAVI_TARGET" python3 - "$PRINTER_DATA/config/.theme/navi.json" <<'PY'
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
href = os.environ.get('FILAMIND_NAVI_HREF', '/filamind/')
data.append({
    "title": "FilaMind Flow",
    "href": href,
    "target": os.environ.get('FILAMIND_NAVI_TARGET', '_self'),
    "icon": "M5 3h14v4h-10v3h8v4h-8v7h-4z",
    "position": 88,
})
with open(p, 'w') as f:
    json.dump(data, f, indent=2)
    f.write('\n')
print("   navi.json -> %s" % href)
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
if [ "$SUBPATH_OK" = 1 ]; then
  echo "  Open:    <your printer URL>/filamind/   (same host as Mainsail; also in the sidebar)"
else
  echo "  Open:    http://${NAVI_HOST:-$(hostname -I 2>/dev/null | awk '{print $1}')}:$UI_PORT   (also in the Mainsail sidebar)"
fi
echo "  Service: sudo systemctl status $SERVICE"
