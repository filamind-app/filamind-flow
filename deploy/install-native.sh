#!/usr/bin/env bash
# FilaMind Flow — install the NATIVE touch app on the printer's touchscreen.
#
# Downloads the prebuilt arm64 .deb (the Tauri touch app that CI built) from the GitHub Release,
# installs it, and writes a `filamind-kiosk` systemd unit (via scripts/install.sh kiosk --bin)
# that can take over the touchscreen from KlipperScreen — reversibly. The unit is NOT enabled at
# boot; you switch to it from the Screen Manager (Touch UI > "Use"). KlipperScreen stays the boot
# default until you persist the switch, so any experiment is reboot-recoverable.
#
# We never BUILD on the printer — a Tauri/Rust build would exhaust a ~1 GB host's RAM and take other
# services down with it. We fetch the aarch64 .deb CI already produced.
#
#   bash deploy/install-native.sh                # download + install the .deb + write the unit
#   bash deploy/install-native.sh --uninstall    # remove the unit + package, restore KlipperScreen
#   bash deploy/install-native.sh --protect-oom  # also shield klipper/moonraker from the OOM killer
#
# NOTE: `apt-get` (to install the .deb) and `bash install.sh kiosk` (to write the unit) need real
# root. The narrow FilaMind sudoers grant covers only systemctl/cp, so this script needs INTERACTIVE
# sudo (or a one-time broadened grant); the unattended Setup-service path can't apt-install for you.
set -euo pipefail

REPO="filamind-app/filamind-flow"
ASSET="filamind-flow-arm64.deb"
SERVICE="filamind-kiosk"             # the unit name flow's switch_touch expects (KIOSK_UNIT)
URL_DEFAULT="http://localhost:8090"  # the flow-touch webview origin (nginx)
SCREEN_UNIT="KlipperScreen.service"

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
USER_NAME="$(id -un)"
PRINTER_DATA="${PRINTER_DATA:-$HOME/printer_data}"
ASVC="$PRINTER_DATA/moonraker.asvc"

# When piped (curl | bash) there's no controlling terminal for sudo to prompt; reconnect one if it
# actually opens (a headless run falls through to passwordless sudo for the narrow grant).
if [ ! -t 0 ] && (exec </dev/tty) 2>/dev/null; then exec </dev/tty; fi

log() { echo "[native] $*"; }

restore_klipperscreen() {
  if systemctl list-unit-files "$SCREEN_UNIT" 2>/dev/null | grep -q "^$SCREEN_UNIT"; then
    sudo systemctl enable "$SCREEN_UNIT" || true
    sudo systemctl start "$SCREEN_UNIT" || true
  else
    log "WARNING: $SCREEN_UNIT is not installed — no display owner to restore to; leaving as-is."
  fi
}

deregister_moonraker() {
  [ -f "$ASVC" ] && sed -i "/^${SERVICE}\$/d" "$ASVC" 2>/dev/null || true
}

uninstall() {
  log "Removing the FilaMind Flow native touch app…"
  sudo systemctl stop "${SERVICE}.service" 2>/dev/null || true
  sudo systemctl disable "${SERVICE}.service" 2>/dev/null || true
  sudo rm -f "/etc/systemd/system/${SERVICE}.service"
  sudo systemctl daemon-reload || true
  # Restore the display owner BEFORE removing the binary so there's never a dark-screen window.
  restore_klipperscreen
  local pkg
  pkg="$(dpkg -S /usr/bin/filamind-flow 2>/dev/null | cut -d: -f1 || true)"
  if [ -n "$pkg" ]; then
    sudo apt-get remove -y "$pkg" 2>/dev/null || sudo dpkg -r "$pkg" 2>/dev/null || true
  fi
  deregister_moonraker
  sudo systemctl restart moonraker 2>/dev/null || true
  log "Removed. KlipperScreen is the display owner again."
  exit 0
}

PROTECT_OOM=0
case "${1:-}" in
  --uninstall) uninstall ;;
  --protect-oom) PROTECT_OOM=1 ;;
  "") ;;
  *) echo "usage: $0 [--uninstall | --protect-oom]" >&2; exit 2 ;;
esac

# ── 1. arch guard + fetch the prebuilt .deb ─────────────────────────────────────────────────────
ARCH="$(dpkg --print-architecture 2>/dev/null || uname -m)"
case "$ARCH" in
  arm64 | aarch64) ;;
  *) echo "[native] This touch app targets arm64; this host is '$ARCH'. Aborting." >&2; exit 1 ;;
esac

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
DEB_URL="https://github.com/$REPO/releases/latest/download/$ASSET"
log "Downloading $ASSET from the latest Release…"
curl -fL "$DEB_URL" -o "$TMP/$ASSET" \
  || { echo "[native] Could not download $DEB_URL — is there a published Release with the .deb asset?" >&2; exit 1; }

# ── 2. install it (apt resolves the libwebkit2gtk-4.1 runtime dep) ──────────────────────────────
log "Installing the .deb (needs sudo for apt)…"
sudo apt-get install -y "$TMP/$ASSET" \
  || { sudo dpkg -i "$TMP/$ASSET" || true; sudo apt-get -y -f install; }

# Discover the installed binary path — don't assume the Cargo package name maps 1:1 to /usr/bin/<x>.
PKG="$(dpkg-deb -f "$TMP/$ASSET" Package 2>/dev/null || echo filamind-flow)"
BIN="$(dpkg -L "$PKG" 2>/dev/null | grep -E '^/usr/bin/' | head -1 || true)"
[ -n "$BIN" ] || BIN="/usr/bin/filamind-flow"
log "Installed binary: $BIN"

# ── 3. write the kiosk unit via flow's single-source unit-writer ────────────────────────────────
sudo bash "$APP_DIR/scripts/install.sh" kiosk --bin "$BIN" "$USER_NAME" "$URL_DEFAULT" "$SERVICE"

# ── 4. register with Moonraker so the panel can start/stop/restart it ───────────────────────────
if [ -f "$ASVC" ]; then
  grep -qx "$SERVICE" "$ASVC" || echo "$SERVICE" >> "$ASVC"
  sudo systemctl restart moonraker 2>/dev/null || true
fi

# ── 5. optional: protect klipper/moonraker from the OOM killer (opt-in) ─────────────────────────
if [ "$PROTECT_OOM" = 1 ]; then
  for svc in klipper moonraker; do
    src="$APP_DIR/deploy/oom/$svc.conf"
    [ -f "$src" ] || continue
    sudo mkdir -p "/etc/systemd/system/$svc.service.d"
    sudo cp "$src" "/etc/systemd/system/$svc.service.d/filamind-oom.conf"
  done
  sudo systemctl daemon-reload || true
  log "Applied protective OOM drop-ins to klipper + moonraker."
fi

cat <<MSG

[native] Done. The FilaMind Flow native touch app is installed but NOT yet on the screen.
  Put it on the screen:  Screen Manager > Touch UI > "Use"   (or: sudo systemctl start $SERVICE)
  KlipperScreen stays the boot default until you persist the switch (reboot-recoverable).
  Remove it:             bash deploy/install-native.sh --uninstall
MSG
