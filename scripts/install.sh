#!/usr/bin/env bash
# FilaMind Flow — the single installer for a Klipper / Moonraker host.
#
# Full install (run as your normal printer user, NOT root):
#   curl -fsSL https://raw.githubusercontent.com/filamind-app/filamind-flow/main/scripts/install.sh | bash
#
# It installs the backend service, serves the (pre-built) UI via nginx, adds a Mainsail sidebar
# entry, registers FilaMind with Moonraker's update_manager, AND grants the panel its narrow
# passwordless-sudo rights (so firmware flashing and the Host Control widget work). Re-runnable.
#
# Subcommands (run from inside the cloned repo, e.g. ~/filamind-flow):
#   sudo bash scripts/install.sh sudoers [user]        (re)grant the passwordless-sudo rights only
#   sudo bash scripts/install.sh kiosk [user] [url]     put FilaMind on the printer's touchscreen
#   sudo bash scripts/install.sh kiosk --uninstall      remove the kiosk, restore KlipperScreen
#        bash scripts/install.sh update                 refresh the backend venv (Moonraker's hook)
set -euo pipefail

REPO="${FILAMIND_REPO:-https://github.com/filamind-app/filamind-flow.git}"
APP="${FILAMIND_DIR:-$HOME/filamind-flow}"
UI_PORT="${FILAMIND_UI_PORT:-8090}"
API_PORT="${FILAMIND_API_PORT:-8011}"
PRINTER_DATA="${PRINTER_DATA:-$HOME/printer_data}"
SERVICE="filamind-flow"

info() { printf '\n\033[1;33m==>\033[0m %s\n' "$*"; }

# Repo root, resolved from this script's own location when it exists on disk (every subcommand is
# run from a clone). The curl|bash full install has no file on disk and clones into $APP itself.
SELF="${BASH_SOURCE[0]:-}"
REPO_ROOT=""
if [ -n "$SELF" ] && [ -f "$SELF" ]; then
  REPO_ROOT="$(cd "$(dirname "$SELF")/.." && pwd)"
fi

# ── update: refresh the backend virtualenv (Moonraker update_manager hook) ─────
do_update() {
  local dir="${REPO_ROOT:-$APP}"
  cd "$dir/backend"
  [ -d .venv ] || python3 -m venv .venv
  ./.venv/bin/pip install -q -U pip
  ./.venv/bin/pip install -q -r requirements.txt
  echo "FilaMind Flow: backend dependencies up to date."
}

# ── sudoers: grant the narrow passwordless-sudo rights the panel needs ─────────
# Firmware flashing (systemctl, dfu-util, cp, chmod, fuser) + Host Control (journalctl, rm,
# timedatectl, localectl, hostnamectl, nmcli). rm is path-guarded in the backend to
# /etc/systemd/system; nmcli covers the network (IP DHCP/static) controls.
do_sudoers() {
  local user_name="${1:-${SUDO_USER:-$(id -un)}}"
  local sudoers_file="/etc/sudoers.d/filamind"
  [ "$(id -u)" -eq 0 ] || { echo "This must run as root. Try: sudo bash $0 sudoers $user_name" >&2; exit 1; }

  local systemctl dfu cp chmod fuser journalctl rm_bin timedatectl localectl hostnamectl nmcli
  systemctl="$(command -v systemctl || echo /usr/bin/systemctl)"
  dfu="$(command -v dfu-util || echo /usr/bin/dfu-util)"
  cp="$(command -v cp || echo /bin/cp)"
  chmod="$(command -v chmod || echo /bin/chmod)"
  fuser="$(command -v fuser || echo /usr/bin/fuser)"
  journalctl="$(command -v journalctl || echo /usr/bin/journalctl)"
  rm_bin="$(command -v rm || echo /bin/rm)"
  timedatectl="$(command -v timedatectl || echo /usr/bin/timedatectl)"
  localectl="$(command -v localectl || echo /usr/bin/localectl)"
  hostnamectl="$(command -v hostnamectl || echo /usr/bin/hostnamectl)"
  nmcli="$(command -v nmcli || echo /usr/bin/nmcli)"

  local tmp
  tmp="$(mktemp)"
  trap 'rm -f "$tmp"' EXIT  # always clean up, even if `install` fails under set -e
  cat > "$tmp" <<EOF
# Managed by FilaMind Flow (scripts/install.sh sudoers) — firmware flashing + Host Control.
$user_name ALL=(root) NOPASSWD: $systemctl, $dfu, $cp, $chmod, $fuser, $journalctl, $rm_bin, $timedatectl, $localectl, $hostnamectl, $nmcli
EOF
  # Validate syntax BEFORE installing so a mistake can never lock you out of sudo.
  if visudo -cf "$tmp"; then
    install -m 0440 -o root -g root "$tmp" "$sudoers_file"
    echo "Installed $sudoers_file — '$user_name' can flash firmware and manage the host without a password."
  else
    echo "sudoers validation failed — not installed." >&2
    exit 1
  fi

  # DFU access: let the user talk to STM32 ROM bootloaders (0483:df11) without sudo.
  local rule="${REPO_ROOT:-$APP}/deploy/99-stm32-dfu.rules"
  local udev_rule="/etc/udev/rules.d/99-stm32-dfu.rules"
  if [ -f "$rule" ]; then
    install -m 0644 -o root -g root "$rule" "$udev_rule"
    udevadm control --reload-rules 2>/dev/null || true
    udevadm trigger 2>/dev/null || true
    echo "Installed $udev_rule — STM32 DFU boards are reachable without sudo."
  fi
}

# ── kiosk: turn the printer's touchscreen into a fullscreen FilaMind browser ───
# Auto-detects X11 (Xorg/xinit) vs Wayland (cage on KMS) by reading KlipperScreen.service, installs
# a browser + compositor, and writes a `filamind-kiosk` unit that Conflicts= KlipperScreen (starting
# one stops the other). Not enabled at boot — FilaMind toggles the swap. Best-effort (no errexit).
do_kiosk() {
  set +e
  local UNIT="/etc/systemd/system/filamind-kiosk.service"
  local SCREEN_UNIT="KlipperScreen.service"
  log() { echo "[kiosk] $*"; }
  die() { echo "[kiosk] ERROR: $*" >&2; exit 1; }

  [ "$(id -u)" -eq 0 ] || die "must run as root — try: sudo bash $0 kiosk $*"

  if [ "${1:-}" = "--uninstall" ]; then
    systemctl stop filamind-kiosk.service 2>/dev/null
    systemctl disable filamind-kiosk.service 2>/dev/null
    rm -f "$UNIT"
    systemctl daemon-reload
    systemctl enable "$SCREEN_UNIT" 2>/dev/null
    systemctl start "$SCREEN_UNIT" 2>/dev/null
    log "Removed the FilaMind kiosk service and restored KlipperScreen."
    exit 0
  fi

  local USER_NAME URL USER_UID DISTRO
  USER_NAME="${1:-${SUDO_USER:-$(id -un)}}"
  URL="${2:-http://localhost:8090}"
  id "$USER_NAME" >/dev/null 2>&1 || die "user '$USER_NAME' not found — pass it: sudo bash $0 kiosk <user> [url]"
  USER_UID="$(id -u "$USER_NAME")"
  DISTRO="unknown"
  [ -r /etc/os-release ] && DISTRO="$(. /etc/os-release && echo "${PRETTY_NAME:-$ID}")"
  log "user=$USER_NAME uid=$USER_UID url=$URL"
  log "distro=$DISTRO"

  local KS_UNIT_TEXT KS_USER KS_TTY TTY
  KS_UNIT_TEXT="$(systemctl cat "$SCREEN_UNIT" 2>/dev/null || true)"
  KS_USER="$(printf '%s\n' "$KS_UNIT_TEXT" | sed -n 's/^User=//p' | head -1)"
  KS_TTY="$(printf '%s\n' "$KS_UNIT_TEXT" | sed -n 's/^TTYPath=//p' | head -1)"
  [ -n "$KS_USER" ] && USER_NAME="$KS_USER" && USER_UID="$(id -u "$USER_NAME")"
  TTY="${KS_TTY:-/dev/tty1}"
  if [ -n "$KS_UNIT_TEXT" ]; then
    log "found KlipperScreen.service (User=${KS_USER:-?}, TTYPath=${TTY})"
  else
    log "KlipperScreen.service not found via systemctl — continuing with defaults"
  fi

  local uses_x11=0 uses_wayland=0
  if printf '%s\n' "$KS_UNIT_TEXT" | grep -qiE 'xinit|startx|/usr/bin/X|DISPLAY=:'; then uses_x11=1; fi
  if command -v xinit >/dev/null 2>&1 || command -v Xorg >/dev/null 2>&1; then uses_x11=1; fi
  if printf '%s\n' "$KS_UNIT_TEXT" | grep -qiE 'cage|sway|labwc|weston|wayfire|wayland'; then uses_wayland=1; fi

  local APT
  APT="$(command -v apt-get || true)"
  apt_install() {
    [ -n "$APT" ] || { log "no apt-get — install '$*' manually, then re-run"; return 0; }
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "$@" 2>/dev/null \
      && log "installed: $*" || log "could not install: $* (may be unavailable in this image's repos)"
  }
  find_browser() {
    local b
    for b in chromium chromium-browser chromium-bin firefox-esr firefox; do
      command -v "$b" 2>/dev/null && return 0
    done
    return 1
  }

  [ -n "$APT" ] && DEBIAN_FRONTEND=noninteractive apt-get update -qq 2>/dev/null || true
  command -v "$(find_browser 2>/dev/null)" >/dev/null 2>&1 || apt_install chromium
  local BROWSER
  BROWSER="$(find_browser || true)"
  [ -n "$BROWSER" ] || apt_install chromium-browser
  BROWSER="$(find_browser || true)"
  [ -n "$BROWSER" ] || die "no browser found (tried chromium / chromium-browser). Install one (e.g. 'sudo apt-get install chromium'), then re-run."
  log "browser=$BROWSER"

  local HAS_DRI=0 MODE="" EXEC ENV_LINES XINIT CAGE
  { [ -e /dev/dri/card0 ] || [ -e /dev/dri/card1 ]; } && HAS_DRI=1
  if [ "$uses_x11" = 1 ] && [ "$uses_wayland" != 1 ]; then
    MODE="x11"
  elif [ "$uses_wayland" = 1 ]; then
    MODE="wayland"
  elif command -v cage >/dev/null 2>&1 && [ "$HAS_DRI" = 1 ]; then
    MODE="wayland"
  elif command -v xinit >/dev/null 2>&1; then
    MODE="x11"
  elif [ "$HAS_DRI" = 1 ]; then
    apt_install cage
    command -v cage >/dev/null 2>&1 && MODE="wayland"
  fi

  if [ "$MODE" = "x11" ]; then
    command -v xinit >/dev/null 2>&1 || apt_install xserver-xorg xinit
    command -v xinit >/dev/null 2>&1 || die "X11 detected but 'xinit' is missing and could not be installed."
    XINIT="$(command -v xinit)"
    EXEC="$XINIT $BROWSER --kiosk --app=$URL --ozone-platform=x11 --noerrdialogs --disable-infobars --no-first-run --disable-translate --check-for-update-interval=31536000 --overscroll-history-navigation=0 -- :0 -nocursor"
    ENV_LINES=$'Environment=XDG_RUNTIME_DIR=/run/user/'"$USER_UID"
  elif [ "$MODE" = "wayland" ]; then
    command -v cage >/dev/null 2>&1 || apt_install cage
    command -v cage >/dev/null 2>&1 || die "Wayland path needs 'cage' but it isn't installed and couldn't be added."
    CAGE="$(command -v cage)"
    EXEC="$CAGE -- $BROWSER --kiosk --app=$URL --ozone-platform=wayland --noerrdialogs --disable-infobars --no-first-run --disable-translate --check-for-update-interval=31536000 --overscroll-history-navigation=0"
    ENV_LINES=$'Environment=XDG_RUNTIME_DIR=/run/user/'"$USER_UID"$'\nEnvironment=XDG_SESSION_TYPE=wayland'
  else
    die "Could not detect a usable display stack (no Xorg/xinit, and no cage + /dev/dri). Tell us your setup — 'systemctl cat KlipperScreen.service' shows how your screen is driven."
  fi
  log "display mode=$MODE"

  local g
  for g in video render input tty seat; do usermod -aG "$g" "$USER_NAME" 2>/dev/null || true; done

  cat >"$UNIT" <<EOF
# Managed by FilaMind Flow (scripts/install.sh kiosk).
# Fullscreen FilaMind Flow on the touchscreen ($MODE). Conflicts with KlipperScreen so that
# starting one stops the other — FilaMind toggles the swap. Not enabled at boot by default.
[Unit]
Description=FilaMind Flow kiosk (fullscreen touchscreen browser)
Conflicts=$SCREEN_UNIT
After=multi-user.target systemd-user-sessions.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER_NAME
PAMName=login
TTYPath=$TTY
StandardInput=tty-fail
StandardOutput=journal
StandardError=journal
$ENV_LINES
# Give the FilaMind web bundle a moment to be reachable before we open it.
ExecStartPre=/bin/sh -c 'command -v curl >/dev/null 2>&1 && { for i in \$(seq 1 30); do curl -sf "$URL" >/dev/null 2>&1 && exit 0; sleep 1; done; }; sleep 3'
ExecStart=$EXEC
Restart=on-failure
RestartSec=5

[Install]
WantedBy=graphical.target
EOF

  systemctl daemon-reload
  cat <<EOF

[kiosk] Installed $UNIT  (mode: $MODE, browser: $BROWSER, user: $USER_NAME, tty: $TTY)

KlipperScreen is still your boot default. To put FilaMind on the screen:
  - from FilaMind Flow:  KlipperScreen Studio > Kiosk > "Switch to FilaMind"
  - or over SSH:         sudo systemctl start filamind-kiosk

Restore KlipperScreen:   sudo systemctl start KlipperScreen   (or the widget's "Restore" button)
EOF
  exit 0
}

# ── install: the full one-line install (clone + venv + service + nginx + sidebar + update + sudo) ──
do_install() {
  [ "$(id -u)" -eq 0 ] && { echo "Please run as your printer user, not root."; exit 1; }
  local c
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
  local SUBPATH_OK=0 PRIMARY_SITE="" cand
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
  local NAVI_HREF NAVI_TARGET NAVI_HOST
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
  local ASVC="$PRINTER_DATA/moonraker.asvc" MCONF="$PRINTER_DATA/config/moonraker.conf"
  [ -f "$ASVC" ] && { grep -qx "$SERVICE" "$ASVC" || echo "$SERVICE" >> "$ASVC"; }
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

  info "Granting the panel its passwordless-sudo rights (firmware + Host Control)"
  # Do it as part of the install so timezone/locale/hostname/network/cleanup/firmware all work
  # out of the box — no separate manual step. (Re-grant later with: sudo bash scripts/install.sh sudoers)
  sudo bash "$APP/scripts/install.sh" sudoers "$USER" || \
    info "Could not grant sudo automatically — run it yourself: sudo bash $APP/scripts/install.sh sudoers"

  info "Done."
  if [ "$SUBPATH_OK" = 1 ]; then
    echo "  Open:    <your printer URL>/filamind/   (same host as Mainsail; also in the sidebar)"
  else
    echo "  Open:    http://${NAVI_HOST:-$(hostname -I 2>/dev/null | awk '{print $1}')}:$UI_PORT   (also in the Mainsail sidebar)"
  fi
  echo "  Service: sudo systemctl status $SERVICE"
}

# ── dispatch ───────────────────────────────────────────────────────────────────
CMD="${1:-install}"
case "$CMD" in
  sudoers) shift; do_sudoers "$@" ;;
  kiosk) shift; do_kiosk "$@" ;;
  update) do_update ;;
  install) do_install ;;
  *)
    echo "Unknown command: $CMD" >&2
    echo "Usage: install.sh [install|sudoers [user]|kiosk [user] [url]|kiosk --uninstall|update]" >&2
    exit 2
    ;;
esac
