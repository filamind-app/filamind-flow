#!/usr/bin/env bash
#
# FilaMind Kiosk installer — turn the printer's touchscreen into a fullscreen
# FilaMind Flow browser that can be swapped with KlipperScreen at will.
#
# Run once, as root:
#     sudo bash deploy/install-kiosk.sh [user] [url]
#     sudo bash deploy/install-kiosk.sh --uninstall
#
#   user  defaults to the account that invoked sudo (the one KlipperScreen / FilaMind run as).
#   url   defaults to http://localhost:8090 (the FilaMind Flow nginx bundle on the host).
#
# It auto-detects how the touchscreen is driven — **X11** (Xorg/xinit, how most KlipperScreen
# images run) or **Wayland** (a `cage` compositor on KMS) — installs a browser, and writes a
# `filamind-kiosk` systemd service that **conflicts with KlipperScreen** (starting one stops the
# other). It is NOT enabled at boot; FilaMind toggles the swap. If it can't find a browser or a
# usable display stack, it stops with a clear message instead of writing a unit that won't start.
#
# Recover a dark screen over SSH at any time:
#     sudo systemctl stop filamind-kiosk && sudo systemctl start KlipperScreen
#
set -uo pipefail

UNIT="/etc/systemd/system/filamind-kiosk.service"
SCREEN_UNIT="KlipperScreen.service"

log() { echo "[kiosk] $*"; }
die() {
  echo "[kiosk] ERROR: $*" >&2
  exit 1
}

[ "$(id -u)" -eq 0 ] || die "must run as root — try: sudo bash $0 $*"

# ── Uninstall ────────────────────────────────────────────────────────────────
if [ "${1:-}" = "--uninstall" ]; then
  systemctl stop filamind-kiosk.service 2>/dev/null || true
  systemctl disable filamind-kiosk.service 2>/dev/null || true
  rm -f "$UNIT"
  systemctl daemon-reload
  systemctl enable "$SCREEN_UNIT" 2>/dev/null || true
  systemctl start "$SCREEN_UNIT" 2>/dev/null || true
  log "Removed the FilaMind kiosk service and restored KlipperScreen."
  exit 0
fi

USER_NAME="${1:-${SUDO_USER:-$(id -un)}}"
URL="${2:-http://localhost:8090}"
id "$USER_NAME" >/dev/null 2>&1 || die "user '$USER_NAME' not found — pass it: sudo bash $0 <user> [url]"
USER_UID="$(id -u "$USER_NAME")"
DISTRO="unknown"
[ -r /etc/os-release ] && DISTRO="$(. /etc/os-release && echo "${PRETTY_NAME:-$ID}")"
log "user=$USER_NAME uid=$USER_UID url=$URL"
log "distro=$DISTRO"

# ── Inspect how KlipperScreen drives the panel (so we mirror its known-good setup) ──
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

# Does KlipperScreen run under X11? (xinit / startx / Xorg / DISPLAY=: in its unit, or X is installed)
uses_x11=0
if printf '%s\n' "$KS_UNIT_TEXT" | grep -qiE 'xinit|startx|/usr/bin/X|DISPLAY=:'; then uses_x11=1; fi
if command -v xinit >/dev/null 2>&1 || command -v Xorg >/dev/null 2>&1; then uses_x11=1; fi
uses_wayland=0
if printf '%s\n' "$KS_UNIT_TEXT" | grep -qiE 'cage|sway|labwc|weston|wayfire|wayland'; then uses_wayland=1; fi

# ── Packages: a browser (either way) + the compositor for the chosen path ─────
APT="$(command -v apt-get || true)"
apt_install() { # best-effort, never aborts the script
  [ -n "$APT" ] || {
    log "no apt-get — install '$*' manually, then re-run"
    return 0
  }
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
BROWSER="$(find_browser || true)"
[ -n "$BROWSER" ] || apt_install chromium-browser
BROWSER="$(find_browser || true)"
[ -n "$BROWSER" ] || die "no browser found (tried chromium / chromium-browser). Install one (e.g. 'sudo apt-get install chromium'), then re-run."
log "browser=$BROWSER"

# ── Pick the display path ─────────────────────────────────────────────────────
HAS_DRI=0
{ [ -e /dev/dri/card0 ] || [ -e /dev/dri/card1 ]; } && HAS_DRI=1
MODE=""
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

# DRM + input access for the kiosk session.
for g in video render input tty seat; do usermod -aG "$g" "$USER_NAME" 2>/dev/null || true; done

# ── systemd unit — the reversible swap lives in Conflicts= ───────────────────
cat >"$UNIT" <<EOF
# Managed by FilaMind Flow (deploy/install-kiosk.sh).
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

If the screen stays dark after switching, see what went wrong with:
  systemctl status filamind-kiosk  --no-pager
  journalctl -u filamind-kiosk -b --no-pager | tail -40

Restore KlipperScreen:   sudo systemctl start KlipperScreen   (or the widget's "Restore" button)
A normal reboot also restores KlipperScreen unless you chose "Make FilaMind the default".
EOF
