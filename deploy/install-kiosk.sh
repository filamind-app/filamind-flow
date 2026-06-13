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
# What it does:
#   * installs a Wayland kiosk compositor (cage) + Chromium
#   * adds the user to the video / render / input / seat / tty groups (DRM + touch access)
#   * writes /etc/systemd/system/filamind-kiosk.service with
#         Conflicts=KlipperScreen.service     (starting one stops the other)
#   * does NOT enable it at boot — KlipperScreen stays the boot default. FilaMind Flow's
#     "KlipperScreen Studio > Kiosk" toggles the swap; a plain switch is reboot-recoverable,
#     and there's an explicit "make default" if you want the kiosk to survive a reboot.
#
# Recover a dark screen over SSH at any time:
#     sudo systemctl stop filamind-kiosk && sudo systemctl start KlipperScreen
#
set -euo pipefail

UNIT="/etc/systemd/system/filamind-kiosk.service"

if [ "$(id -u)" -ne 0 ]; then
  echo "This must run as root. Try: sudo bash $0 $*" >&2
  exit 1
fi

# ── Uninstall ──────────────────────────────────────────────────────────────
if [ "${1:-}" = "--uninstall" ]; then
  systemctl stop filamind-kiosk.service 2>/dev/null || true
  systemctl disable filamind-kiosk.service 2>/dev/null || true
  rm -f "$UNIT"
  systemctl daemon-reload
  systemctl enable KlipperScreen.service 2>/dev/null || true
  systemctl start KlipperScreen.service 2>/dev/null || true
  echo "Removed the FilaMind kiosk service and restored KlipperScreen."
  exit 0
fi

USER_NAME="${1:-${SUDO_USER:-$(id -un)}}"
URL="${2:-http://localhost:8090}"
USER_UID="$(id -u "$USER_NAME")"

echo "Installing the FilaMind kiosk for user '$USER_NAME' → $URL"

# ── Packages: a Wayland kiosk compositor (cage) + a browser (chromium) ───────
# cage runs a single fullscreen app directly on KMS/DRM — no X, no desktop. It is the most
# portable way to put a browser on these embedded touch panels on current Debian/Armbian images.
if command -v apt-get >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq || true
  apt-get install -y --no-install-recommends cage chromium || \
    apt-get install -y --no-install-recommends cage chromium-browser || \
    echo "WARNING: could not auto-install cage/chromium — install them manually, then re-run." >&2
else
  echo "WARNING: no apt-get found — install 'cage' and 'chromium' yourself, then re-run." >&2
fi

CAGE="$(command -v cage || echo /usr/bin/cage)"
CHROMIUM="$(command -v chromium || command -v chromium-browser || echo /usr/bin/chromium)"

# DRM + input access for the kiosk session.
usermod -aG video,render,input,tty "$USER_NAME" 2>/dev/null || true
usermod -aG seat "$USER_NAME" 2>/dev/null || true

# ── systemd unit — the reversible swap lives in Conflicts= ───────────────────
cat > "$UNIT" <<EOF
# Managed by FilaMind Flow (deploy/install-kiosk.sh).
# Fullscreen FilaMind Flow on the touchscreen. Conflicts with KlipperScreen so that starting
# one stops the other — FilaMind toggles the swap. Not enabled at boot by default.
[Unit]
Description=FilaMind Flow kiosk (fullscreen touchscreen browser)
Conflicts=KlipperScreen.service
After=multi-user.target systemd-user-sessions.service network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER_NAME
PAMName=login
TTYPath=/dev/tty1
StandardInput=tty-fail
StandardOutput=journal
StandardError=journal
Environment=XDG_RUNTIME_DIR=/run/user/$USER_UID
Environment=XDG_SESSION_TYPE=wayland
# Give the FilaMind web bundle a moment to be reachable before we open it.
ExecStartPre=/bin/sh -c 'command -v curl >/dev/null 2>&1 && { for i in \$(seq 1 30); do curl -sf "$URL" >/dev/null 2>&1 && exit 0; sleep 1; done; }; sleep 3'
ExecStart=$CAGE -- $CHROMIUM --kiosk --app=$URL --ozone-platform=wayland --noerrdialogs --disable-infobars --no-first-run --disable-translate --check-for-update-interval=31536000 --overscroll-history-navigation=0
Restart=on-failure
RestartSec=5

[Install]
WantedBy=graphical.target
EOF

systemctl daemon-reload

cat <<EOF

Installed $UNIT.

KlipperScreen is still your boot default. To put FilaMind on the screen:
  - from FilaMind Flow:  KlipperScreen Studio > Kiosk > "Switch to FilaMind"
  - or over SSH:         sudo systemctl start filamind-kiosk

Restore KlipperScreen:   sudo systemctl start KlipperScreen   (or the widget's "Restore" button)
A normal reboot also restores KlipperScreen unless you chose "Make FilaMind the default".
EOF
