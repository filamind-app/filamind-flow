#!/usr/bin/env bash
#
# Grants the FilaMind Flow backend the narrow passwordless-sudo rights it needs:
#   - Firmware flashing: stop/start the Klipper services, run dfu-util, install a
#     Linux-process MCU binary.
#   - Host Control widget: manage systemd units (systemctl), read unit logs
#     (journalctl), remove user-installed unit files (rm — path-guarded in the
#     backend to /etc/systemd/system only), and change system settings:
#     timedatectl (time/timezone/NTP), localectl (language/keymap), hostnamectl
#     (hostname) and nmcli (Wi-Fi).
# Nothing else uses sudo.
#
# Run once, as root:
#     sudo bash deploy/setup-sudoers.sh [user]
#
# `user` defaults to the user that invoked sudo (the account the backend runs as).

set -euo pipefail

USER_NAME="${1:-${SUDO_USER:-$(id -un)}}"
SUDOERS_FILE="/etc/sudoers.d/filamind"

if [ "$(id -u)" -ne 0 ]; then
  echo "This must run as root. Try: sudo bash $0 ${1:-$USER_NAME}" >&2
  exit 1
fi

# Resolve absolute tool paths (sudoers needs full paths), with sane fallbacks.
SYSTEMCTL="$(command -v systemctl || echo /usr/bin/systemctl)"
DFU_UTIL="$(command -v dfu-util || echo /usr/bin/dfu-util)"
CP_BIN="$(command -v cp || echo /bin/cp)"
CHMOD_BIN="$(command -v chmod || echo /bin/chmod)"
FUSER_BIN="$(command -v fuser || echo /usr/bin/fuser)"
JOURNALCTL="$(command -v journalctl || echo /usr/bin/journalctl)"
RM_BIN="$(command -v rm || echo /bin/rm)"
TIMEDATECTL="$(command -v timedatectl || echo /usr/bin/timedatectl)"
LOCALECTL="$(command -v localectl || echo /usr/bin/localectl)"
HOSTNAMECTL="$(command -v hostnamectl || echo /usr/bin/hostnamectl)"
NMCLI="$(command -v nmcli || echo /usr/bin/nmcli)"

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
cat > "$TMP" <<EOF
# Managed by FilaMind Flow (deploy/setup-sudoers.sh) — firmware flashing + Host Control.
$USER_NAME ALL=(root) NOPASSWD: $SYSTEMCTL, $DFU_UTIL, $CP_BIN, $CHMOD_BIN, $FUSER_BIN, $JOURNALCTL, $RM_BIN, $TIMEDATECTL, $LOCALECTL, $HOSTNAMECTL, $NMCLI
EOF

# Validate syntax BEFORE installing so a mistake can never lock you out of sudo.
visudo -cf "$TMP"
install -m 0440 -o root -g root "$TMP" "$SUDOERS_FILE"

echo "Installed $SUDOERS_FILE — '$USER_NAME' can now flash firmware and manage host services without a password."

# DFU access: let the user talk to STM32 ROM bootloaders (0483:df11) directly, so
# dfu-util can flash without sudo. Ships beside this script.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
UDEV_RULE="/etc/udev/rules.d/99-stm32-dfu.rules"
if [ -f "$SCRIPT_DIR/99-stm32-dfu.rules" ]; then
  install -m 0644 -o root -g root "$SCRIPT_DIR/99-stm32-dfu.rules" "$UDEV_RULE"
  udevadm control --reload-rules 2>/dev/null || true
  udevadm trigger 2>/dev/null || true
  echo "Installed $UDEV_RULE — STM32 DFU boards are reachable without sudo."
fi
