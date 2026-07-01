#!/usr/bin/env bash
# FilaMind Flow - the single installer for a Klipper / Moonraker host.
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
#   sudo bash scripts/install.sh kiosk [user] [url] [unit]   put a FilaMind UI on the touchscreen
#       (default unit 'filamind-kiosk' -> the flow web UI; for the FilaMind screen touch app use:
#        sudo bash scripts/install.sh kiosk biqu http://localhost:8088 filamind-screen-kiosk)
#   sudo bash scripts/install.sh kiosk --uninstall [unit]    remove a kiosk, restore KlipperScreen
#        bash scripts/install.sh update                 refresh the backend venv (Moonraker's hook)
#        bash scripts/install.sh suite                  also install the 3D agent + screen native app
#        bash scripts/install.sh uninstall              remove FilaMind from the host (keeps app files)
#
# Install everything in one go (flow + the 3D agent + the screen native app):
#   FILAMIND_WITH_SUITE=1 curl -fsSL https://raw.githubusercontent.com/filamind-app/filamind-flow/main/scripts/install.sh | bash
set -euo pipefail

REPO="${FILAMIND_REPO:-https://github.com/filamind-app/filamind-flow.git}"
APP="${FILAMIND_DIR:-$HOME/filamind-flow}"
UI_PORT="${FILAMIND_UI_PORT:-8090}"
API_PORT="${FILAMIND_API_PORT:-8011}"
PRINTER_DATA="${PRINTER_DATA:-$HOME/printer_data}"
SERVICE="filamind-flow"

info() { printf '\n\033[1;33m==>\033[0m %s\n' "$*"; }

# Keep only the most recent FilaMind backups of a file so repeated installs/updates don't
# accumulate "<file>.bak.filamind.*" litter. $1 = the backed-up file's path; $2 = an optional
# command prefix (e.g. "sudo") for removing root-owned backups.
prune_backups() {
  local f
  ls -t "$1".bak.filamind.* 2>/dev/null | tail -n +4 | while IFS= read -r f; do ${2:-} rm -f "$f"; done
}

# Repo root, resolved from this script's own location when it exists on disk (every subcommand is
# run from a clone). The curl|bash full install has no file on disk and clones into $APP itself.
SELF="${BASH_SOURCE[0]:-}"
REPO_ROOT=""
if [ -n "$SELF" ] && [ -f "$SELF" ]; then
  REPO_ROOT="$(cd "$(dirname "$SELF")/.." && pwd)"
fi

# -- sudoers grant content (shared by the `sudoers` install + the `update` self-heal) ----------
# Emit the passwordless-sudo rule to stdout, resolving each binary's absolute path so the rule
# survives a non-standard $PATH. Single source of truth so a NEW capability the panel needs is
# added in exactly one place and reaches both the fresh-install and update code paths.
render_sudoers() {
  local user_name="$1"
  local systemctl dfu cp chmod fuser journalctl rm_bin timedatectl localectl hostnamectl nmcli ip_bin mkdir_bin
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
  ip_bin="$(command -v ip || echo /usr/sbin/ip)"  # CAN bus control: ip link set up/down/bitrate/params
  mkdir_bin="$(command -v mkdir || echo /bin/mkdir)"  # host-MCU -r auto-fix: create the klipper-mcu drop-in dir
  local apt_get dpkg_bin bash_bin flow_home flow_install
  apt_get="$(command -v apt-get || echo /usr/bin/apt-get)"
  dpkg_bin="$(command -v dpkg || echo /usr/bin/dpkg)"
  bash_bin="$(command -v bash || echo /bin/bash)"
  flow_home="$(getent passwd "$user_name" 2>/dev/null | cut -d: -f6)" || flow_home=""
  flow_install="${flow_home:-/home/$user_name}/filamind-flow/scripts/install.sh"
  cat <<EOF
# Managed by FilaMind Flow (scripts/install.sh) - firmware flashing + Host Control. Auto-refreshed
# on each update, so a new capability the panel needs reaches every install without a manual step.
$user_name ALL=(root) NOPASSWD: $systemctl, $dfu, $cp, $chmod, $fuser, $journalctl, $rm_bin, $timedatectl, $localectl, $hostnamectl, $nmcli, $ip_bin, $mkdir_bin
# Native touch-app install (FilaMind screen .deb kiosk): package + WebKit runtime via apt/dpkg, and
# the Flow kiosk unit-writer. Wider than the base grant - enables one-click native install.
$user_name ALL=(root) NOPASSWD: $apt_get, $dpkg_bin, $bash_bin $flow_install kiosk *
EOF
}

# Keep the passwordless-sudo grant current on EVERY update without a manual re-run: regenerate the
# rule and install it via the panel's already-granted `sudo -n cp`/`chmod`, so a new capability
# (e.g. CAN-bus `ip` control) reaches the whole fleet automatically on the next Moonraker update.
# Best-effort + silent: if the grant was never set up (no passwordless cp), or sudo/visudo is
# missing, the existing grant is left untouched. `visudo -cf` validates BEFORE installing, so a bad
# rule can never lock the user out of sudo, and the file is written at 0440 root-owned in one shot.
refresh_sudoers_on_update() {
  local dest="/etc/sudoers.d/filamind"
  local user_name="${SUDO_USER:-$(id -un)}"
  command -v visudo >/dev/null 2>&1 || return 0
  command -v sudo >/dev/null 2>&1 || return 0
  local cp_bin chmod_bin tmp
  cp_bin="$(command -v cp || echo /bin/cp)"
  chmod_bin="$(command -v chmod || echo /bin/chmod)"
  tmp="$(mktemp)" || return 0
  render_sudoers "$user_name" >"$tmp"
  chmod 0440 "$tmp" 2>/dev/null || true
  if visudo -cf "$tmp" >/dev/null 2>&1 && sudo -n "$cp_bin" "$tmp" "$dest" 2>/dev/null; then
    sudo -n "$chmod_bin" 0440 "$dest" 2>/dev/null || true
    echo "FilaMind Flow: refreshed the passwordless-sudo grant (CAN control + any new capabilities)."
  fi
  rm -f "$tmp"
}

# The Firmware Manager builds + flashes Klipper firmware, which needs the host build toolchain (make
# + the MCU cross-compilers). Install it AUTOMATICALLY + idempotently on install/update so a user
# never has to run apt by hand (issue #558). Reuses the passwordless apt-get grant the sudoers
# already carries. Best-effort: an offline / apt-busy failure never breaks the update - it just
# retries on the next one. Once `make` + the Arm compiler are present this is two cheap checks.
ensure_build_toolchain() {
  command -v apt-get >/dev/null 2>&1 || return 0
  # Already installed? make = the base blocker; arm-none-eabi-gcc = the common STM32/RP2040 compiler.
  if command -v make >/dev/null 2>&1 && command -v arm-none-eabi-gcc >/dev/null 2>&1; then
    return 0
  fi
  local sudo_pfx=""
  if [ "$(id -u)" -ne 0 ]; then
    if sudo -n true 2>/dev/null; then
      sudo_pfx="sudo -n"          # update hook: the panel's passwordless apt-get grant is active
    elif [ -t 0 ]; then
      sudo_pfx="sudo"             # interactive install: prompt once if needed
    else
      return 0                    # no grant + no terminal: defer to the next update
    fi
  fi
  echo "FilaMind Flow: installing the firmware build tools (one-time; this can take a few minutes)…"
  $sudo_pfx apt-get update -qq >/dev/null 2>&1 || true
  # Arm (STM32 / RP2040 / SAM) + AVR (atmega) compilers + dfu-util - Klipper's firmware build deps.
  $sudo_pfx apt-get install -y --no-install-recommends \
    build-essential \
    gcc-arm-none-eabi binutils-arm-none-eabi libnewlib-arm-none-eabi \
    gcc-avr avr-libc binutils-avr avrdude \
    dfu-util >/dev/null 2>&1 || true
  if command -v make >/dev/null 2>&1; then
    echo "FilaMind Flow: firmware build tools ready."
  else
    echo "FilaMind Flow: could not install the firmware build tools automatically" \
      "(host offline or apt busy) - will retry on the next update." >&2
  fi
}

# -- update: refresh the backend virtualenv (Moonraker update_manager hook) -----
do_update() {
  local dir="${REPO_ROOT:-$APP}"
  cd "$dir/backend"
  # Rebuild the venv when it's missing OR broken (no pip), not just when the directory is absent.
  # Moonraker's `update_manager recover` runs `git clean`, which DELETES the git-ignored .venv that
  # the systemd unit's ExecStart points at; an interrupted earlier run can also leave a pip-less
  # stub. Testing for the pip binary (not merely the dir) self-heals both, so a plain `update`
  # always restores a runnable backend instead of leaving the service crash-looping.
  if [ ! -x .venv/bin/pip ]; then
    rm -rf .venv
    python3 -m venv .venv || {
      echo "Could not create the Python venv. Install your python3's venv module" \
        "(e.g. sudo apt install python3-venv) and re-run." >&2
      exit 1
    }
  fi
  ./.venv/bin/pip install -q -U pip
  ./.venv/bin/pip install -q -r requirements.txt
  echo "FilaMind Flow: backend dependencies up to date."
  # Self-heal the passwordless-sudo grant so new privileged capabilities apply on update alone.
  refresh_sudoers_on_update
  # Auto-install the firmware build toolchain so users never run apt by hand (after the sudoers
  # refresh above, the passwordless apt-get grant it needs is guaranteed current).
  ensure_build_toolchain
}

# -- sudoers: grant the narrow passwordless-sudo rights the panel needs ---------
# Firmware flashing (systemctl, dfu-util, cp, chmod, fuser) + Host Control (journalctl, rm,
# timedatectl, localectl, hostnamectl, nmcli, ip). rm is path-guarded in the backend to
# /etc/systemd/system; nmcli covers the network (IP DHCP/static) controls; ip covers CAN-bus
# control (link up/down + bitrate), restricted in the backend to discovered CAN interfaces.
do_sudoers() {
  local user_name="${1:-${SUDO_USER:-$(id -un)}}"
  local sudoers_file="/etc/sudoers.d/filamind"
  [ "$(id -u)" -eq 0 ] || { echo "This must run as root. Try: sudo bash $0 sudoers $user_name" >&2; exit 1; }

  # NOT `local`: the EXIT trap below fires at *script* exit - after this function has returned -
  # so $tmp must still be in scope, and ${tmp:-} keeps the trap safe under `set -u`.
  tmp="$(mktemp)"
  trap 'rm -f "${tmp:-}"' EXIT  # always clean up, even if `install` fails under set -e
  render_sudoers "$user_name" > "$tmp"  # single source of truth (see render_sudoers above)
  # Validate syntax BEFORE installing so a mistake can never lock you out of sudo.
  if visudo -cf "$tmp"; then
    install -m 0440 -o root -g root "$tmp" "$sudoers_file"
    echo "Installed $sudoers_file - '$user_name' can flash firmware and manage the host without a password."
  else
    echo "sudoers validation failed - not installed." >&2
    exit 1
  fi

  # DFU access: let the user talk to STM32 ROM bootloaders (0483:df11) without sudo.
  local rule="${REPO_ROOT:-$APP}/deploy/99-stm32-dfu.rules"
  local udev_rule="/etc/udev/rules.d/99-stm32-dfu.rules"
  if [ -f "$rule" ]; then
    install -m 0644 -o root -g root "$rule" "$udev_rule"
    udevadm control --reload-rules 2>/dev/null || true
    udevadm trigger 2>/dev/null || true
    echo "Installed $udev_rule - STM32 DFU boards are reachable without sudo."
  fi
}

# -- kiosk: turn the printer's touchscreen into the fullscreen native FilaMind app ---
# Auto-detects X11 (Xorg/xinit) vs Wayland (cage on KMS) by reading KlipperScreen.service and writes a
# `filamind-kiosk` unit that launches an installed NATIVE app binary (the Tauri .deb touch app) and
# Conflicts= KlipperScreen (starting one stops the other). Not enabled at boot - FilaMind toggles the
# swap. Best-effort (no errexit). install-native.sh discovers the binary path (dpkg -L) and passes it.
#   kiosk --bin PATH [user] [url] [unit-name]   |   kiosk --uninstall [unit-name]
do_kiosk() {
  set +e
  local SCREEN_UNIT="KlipperScreen.service"
  log() { echo "[kiosk] $*"; }
  die() { echo "[kiosk] ERROR: $*" >&2; exit 1; }

  # --bin <path> is the installed native binary to launch (install-native.sh discovers it via dpkg -L).
  local NATIVE_BIN=""
  while :; do
    case "${1:-}" in
      --bin) NATIVE_BIN="${2:-}"; shift 2 ;;
      *) break ;;
    esac
  done

  [ "$(id -u)" -eq 0 ] || die "must run as root - try: sudo bash $0 kiosk $*"

  # Two FilaMind kiosks can coexist (the selector switches between them):
  #   filamind-kiosk         -> the FilaMind Flow native touch app (widget control)
  #   filamind-screen-kiosk  -> the FilaMind screen native touch app (print control)
  local NAME UNIT
  if [ "${1:-}" = "--uninstall" ]; then
    NAME="${2:-filamind-kiosk}"
    systemctl stop "$NAME.service" 2>/dev/null
    systemctl disable "$NAME.service" 2>/dev/null
    rm -f "/etc/systemd/system/$NAME.service"
    systemctl daemon-reload
    systemctl enable "$SCREEN_UNIT" 2>/dev/null
    systemctl start "$SCREEN_UNIT" 2>/dev/null
    log "Removed $NAME and restored KlipperScreen."
    exit 0
  fi

  local USER_NAME URL USER_UID DISTRO
  USER_NAME="${1:-${SUDO_USER:-$(id -un)}}"
  # An empty URL = no HTTP origin to wait on (the screen app talks Moonraker directly); a set URL
  # (flow-touch needs nginx :8090) keeps the reachability wait below.
  URL="${2:-}"
  NAME="${3:-filamind-kiosk}"
  UNIT="/etc/systemd/system/$NAME.service"
  id "$USER_NAME" >/dev/null 2>&1 || die "user '$USER_NAME' not found - pass it: sudo bash $0 kiosk --bin <path> <user>"
  USER_UID="$(id -u "$USER_NAME")"
  DISTRO="unknown"
  [ -r /etc/os-release ] && DISTRO="$(. /etc/os-release && echo "${PRETTY_NAME:-$ID}")"
  log "user=$USER_NAME uid=$USER_UID url=${URL:-<none>}"
  log "distro=$DISTRO"

  [ -n "$NATIVE_BIN" ] || die "kiosk needs --bin <path-to-installed-native-binary> (install the .deb first)"
  [ -x "$NATIVE_BIN" ] || log "warning: $NATIVE_BIN is not executable yet - install the .deb first."
  log "native binary=$NATIVE_BIN"

  local KS_UNIT_TEXT KS_USER KS_TTY TTY
  KS_UNIT_TEXT="$(systemctl cat "$SCREEN_UNIT" 2>/dev/null || true)"
  KS_USER="$(printf '%s\n' "$KS_UNIT_TEXT" | sed -n 's/^User=//p' | head -1)"
  KS_TTY="$(printf '%s\n' "$KS_UNIT_TEXT" | sed -n 's/^TTYPath=//p' | head -1)"
  [ -n "$KS_USER" ] && USER_NAME="$KS_USER" && USER_UID="$(id -u "$USER_NAME")"
  TTY="${KS_TTY:-/dev/tty1}"
  if [ -n "$KS_UNIT_TEXT" ]; then
    log "found KlipperScreen.service (User=${KS_USER:-?}, TTYPath=${TTY})"
  else
    log "KlipperScreen.service not found via systemctl - continuing with defaults"
  fi

  local uses_x11=0 uses_wayland=0
  if printf '%s\n' "$KS_UNIT_TEXT" | grep -qiE 'xinit|startx|/usr/bin/X|DISPLAY=:'; then uses_x11=1; fi
  if command -v xinit >/dev/null 2>&1 || command -v Xorg >/dev/null 2>&1; then uses_x11=1; fi
  if printf '%s\n' "$KS_UNIT_TEXT" | grep -qiE 'cage|sway|labwc|weston|wayfire|wayland'; then uses_wayland=1; fi

  local APT
  APT="$(command -v apt-get || true)"
  apt_install() {
    [ -n "$APT" ] || { log "no apt-get - install '$*' manually, then re-run"; return 0; }
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "$@" 2>/dev/null \
      && log "installed: $*" || log "could not install: $* (may be unavailable in this image's repos)"
  }

  [ -n "$APT" ] && DEBIAN_FRONTEND=noninteractive apt-get update -qq 2>/dev/null || true

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

  # Launch the native app fullscreen. X11: bare X server, no window manager - the fullscreen Tauri
  # window owns the screen, with an explicit vtN matching TTYPath so Xorg never grabs the wrong VT
  # (the likeliest black-screen). Wayland: cage kiosk compositor. WEBKIT_DISABLE_COMPOSITING_MODE=1
  # by default for the Mali/panfrost GPU (fall back to LIBGL_ALWAYS_SOFTWARE=1 if it renders black).
  local XDG_ENV
  XDG_ENV=$'Environment=XDG_RUNTIME_DIR=/run/user/'"$USER_UID"
  if [ "$MODE" = "x11" ]; then
    command -v xinit >/dev/null 2>&1 || apt_install xserver-xorg xinit
    command -v xinit >/dev/null 2>&1 || die "X11 detected but 'xinit' is missing and could not be installed."
    XINIT="$(command -v xinit)"
    local VTNUM VT
    VTNUM="$(printf '%s' "$TTY" | grep -oE '[0-9]+$' || true)"
    VT="vt${VTNUM:-1}"
    EXEC="$XINIT $NATIVE_BIN -- :0 $VT -nocursor"
    ENV_LINES="$XDG_ENV"$'\nEnvironment=WEBKIT_DISABLE_COMPOSITING_MODE=1'
  elif [ "$MODE" = "wayland" ]; then
    command -v cage >/dev/null 2>&1 || apt_install cage
    command -v cage >/dev/null 2>&1 || die "Wayland path needs 'cage' but it isn't installed and couldn't be added."
    CAGE="$(command -v cage)"
    EXEC="$CAGE -- $NATIVE_BIN"
    ENV_LINES="$XDG_ENV"$'\nEnvironment=XDG_SESSION_TYPE=wayland\nEnvironment=WEBKIT_DISABLE_COMPOSITING_MODE=1'
  else
    die "Could not detect a usable display stack (no Xorg/xinit, and no cage + /dev/dri). Tell us your setup - 'systemctl cat KlipperScreen.service' shows how your screen is driven."
  fi
  log "display mode=$MODE"

  local g
  for g in video render input tty seat; do usermod -aG "$g" "$USER_NAME" 2>/dev/null || true; done

  # Conflict with every OTHER touch UI so starting this kiosk stops the rest (one screen, one UI).
  local u CONFLICTS=""
  for u in KlipperScreen.service guppyscreen.service filamind-kiosk.service filamind-screen-kiosk.service; do
    [ "$u" != "$NAME.service" ] && CONFLICTS="$CONFLICTS $u"
  done

  # OOM guards: more-killable than Moonraker (OOMScoreAdjust>0 so the kernel reaps the replaceable
  # kiosk first under pressure), kill the whole cgroup on OOM, and cap any crash-loop. MemoryMax is
  # deliberately NOT set - it needs an on-device RSS measurement (a too-low cap would crash-loop the
  # webview); see ROADMAP-NATIVE-UIS P7. The reachability wait only applies when there's an HTTP origin
  # ($URL): flow-touch needs nginx; the screen app talks Moonraker directly.
  local UNIT_EXTRA SVC_OOM EXECPRE=""
  UNIT_EXTRA=$'StartLimitIntervalSec=120\nStartLimitBurst=5'
  [ -n "$URL" ] && UNIT_EXTRA="After=filamind-flow.service nginx.service"$'\n'"$UNIT_EXTRA"
  SVC_OOM=$'OOMScoreAdjust=200\nOOMPolicy=kill'
  if [ -n "$URL" ]; then
    EXECPRE="# Give the web bundle a moment to be reachable before we open it."$'\n'"ExecStartPre=/bin/sh -c 'command -v curl >/dev/null 2>&1 && { for i in \$(seq 1 30); do curl -sf \"$URL\" >/dev/null 2>&1 && exit 0; sleep 1; done; }; sleep 3'"
  fi

  cat >"$UNIT" <<EOF
# Managed by FilaMind Flow (scripts/install.sh kiosk).
# Fullscreen native touch app ($MODE)${URL:+, backend $URL}. Conflicts with the other touch UIs so
# starting one stops the others - FilaMind toggles the swap. Not enabled at boot by default.
[Unit]
Description=FilaMind kiosk: $NAME (native)
Conflicts=$CONFLICTS
After=multi-user.target systemd-user-sessions.target network-online.target
Wants=network-online.target
$UNIT_EXTRA

[Service]
Type=simple
User=$USER_NAME
PAMName=login
TTYPath=$TTY
StandardInput=tty-fail
StandardOutput=journal
StandardError=journal
$ENV_LINES
$SVC_OOM
$EXECPRE
ExecStart=$EXEC
Restart=on-failure
RestartSec=5

[Install]
WantedBy=graphical.target
EOF

  systemctl daemon-reload
  cat <<EOF

[kiosk] Installed $UNIT  (mode: $MODE, native: $NATIVE_BIN, user: $USER_NAME, tty: $TTY)

KlipperScreen is still your boot default. To put FilaMind on the screen:
  - from FilaMind Flow:  Screen Manager > Touch UI > "Use"
  - or over SSH:         sudo systemctl start $NAME

Restore KlipperScreen:   sudo systemctl start KlipperScreen   (or the widget's "Restore" button)
EOF
  exit 0
}

# -- install: the full one-line install (clone + venv + service + nginx + sidebar + update + sudo) --
do_install() {
  [ "$(id -u)" -eq 0 ] && { echo "Please run as your printer user, not root."; exit 1; }
  local c
  # nginx (and other daemons) live in /usr/sbin, which is not in a normal user's PATH on Debian /
  # Pi OS - look there too so an installed nginx is detected when run as the printer user.
  export PATH="$PATH:/usr/sbin:/sbin"
  for c in git python3 nginx; do
    command -v "$c" >/dev/null || { echo "Missing dependency: $c (install it first, e.g. sudo apt install $c)"; exit 1; }
  done

  info "Fetching FilaMind Flow into $APP"
  if [ -d "$APP/.git" ]; then git -C "$APP" pull --ff-only; else git clone "$REPO" "$APP"; fi

  info "Backend virtualenv"
  cd "$APP/backend"
  # python3's venv module ships as a SEPARATE apt package on Debian / Pi OS (python3-venv); without
  # it, `python3 -m venv` leaves a broken, pip-less .venv. Test for pip (not just the dir) so a
  # partial venv from an earlier failed run is rebuilt, and install the venv package if creation
  # fails, so the one-line install just works.
  if [ ! -x .venv/bin/pip ]; then
    rm -rf .venv
    if ! python3 -m venv .venv 2>/dev/null; then
      info "Installing python3-venv (the backend environment needs it)"
      sudo apt-get install -y python3-venv 2>/dev/null || true
      python3 -m venv .venv || { echo "Could not create the Python venv. Install your python3's venv module (e.g. sudo apt install python3-venv) and re-run."; exit 1; }
    fi
  fi
  ./.venv/bin/pip install -q -U pip
  ./.venv/bin/pip install -q -r requirements.txt

  # Firmware build toolchain, so a fresh install can build/flash straight away (sudo is already warm
  # from the venv step above). Best-effort - if it can't run now, the update hook installs it later.
  ensure_build_toolchain

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

  # nginx workers (www-data) must be able to TRAVERSE into the home dir to read the bundle. Newer
  # distros default the home dir to 0750, which blocks them - the API keeps working but the UI 403s.
  # Grant traverse-only (o+x, NOT o+r) along the path to dist; harmless where it's already 0755.
  chmod o+x "$HOME" "$APP" "$APP/frontend" "$APP/frontend/dist" 2>/dev/null || true
  if command -v curl >/dev/null 2>&1 \
     && [ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$UI_PORT/" 2>/dev/null)" = "403" ]; then
    info "WARNING: the UI returned 403 - nginx can't read $APP/frontend/dist. Check permissions on $HOME."
  fi

  info "Subpath integration on the host's primary web server"
  # Expose FilaMind under /filamind/ on whatever server already answers on :80 (Mainsail /
  # Fluidd). That server is the one a remote reverse proxy or a Cloudflare tunnel already
  # forwards, so the panel becomes reachable on LAN, by IP, AND through the tunnel with ONE
  # host-relative link - no extra port to expose, no mDNS. The marker-guarded block proxies
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
    if sudo python3 - "$PRIMARY_SITE" "$UI_PORT" <<'PY'
import os, re, sys, time
path = sys.argv[1]
port = sys.argv[2] if len(sys.argv) > 2 else '8090'
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
      if sudo nginx -t 2>/dev/null; then
        sudo systemctl reload nginx && SUBPATH_OK=1
      else
        # The injected block isn't valid on this host (e.g. the primary site lacks the
        # $connection_upgrade map) - revert from the backup so nginx is never left broken.
        latest_bak="$(ls -t "$PRIMARY_SITE".bak.filamind.* 2>/dev/null | head -1)"
        [ -n "$latest_bak" ] && sudo cp "$latest_bak" "$PRIMARY_SITE" \
          && info "  subpath skipped (nginx config check failed) - reverted $PRIMARY_SITE"
      fi
      [ -n "$PRIMARY_SITE" ] && prune_backups "$PRIMARY_SITE" sudo
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
    # Open in the SAME tab (not a new one): the sidebar link should navigate Mainsail to FilaMind
    # Flow in place, like every other sidebar entry, rather than spawning a second tab.
    NAVI_HREF="http://$NAVI_HOST:$UI_PORT"; NAVI_TARGET="_self"
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
    prune_backups "$MCONF"
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

  info "Granting the panel its passwordless-sudo rights (firmware + Host Control + native installs)"
  # Do it as part of the install so timezone/locale/hostname/network/cleanup/firmware all work
  # out of the box - no separate manual step. (Re-grant later with: sudo bash scripts/install.sh sudoers)
  sudo bash "$APP/scripts/install.sh" sudoers "$USER" || true
  # VERIFY the grant actually landed. The Setup widget installs the 3D agent + the screen .deb
  # HEADLESSLY (no terminal to type a password), so a silently-missing grant would break one-click
  # installs later with a confusing "a password is required". Probe a granted command (systemctl);
  # if it still needs a password, this install ran without a terminal - surface the one-time fix.
  if ! sudo -n systemctl --version >/dev/null 2>&1; then
    info "NOTE: passwordless sudo did not activate (did this install run non-interactively?)."
    info "      Run once over SSH so the Setup widget can install apps without a prompt:"
    info "      sudo bash $APP/scripts/install.sh sudoers $USER"
  fi

  # Opt-in: also install the rest of the FilaMind suite (the 3D agent + the screen native app) so
  # the suite-gated widgets unlock and the touchscreen can run the native app. OFF by default - it
  # clones two more repos and the screen app can take over the display, so it's an explicit choice.
  # Turn it on for a fresh install:  FILAMIND_WITH_SUITE=1 curl -fsSL .../install.sh | bash
  # Or add it to an existing install any time:  bash scripts/install.sh suite
  [ "${FILAMIND_WITH_SUITE:-0}" = "1" ] && do_suite || true

  info "Done."
  if [ "$SUBPATH_OK" = 1 ]; then
    echo "  Open:    <your printer URL>/filamind/   (same host as Mainsail; also in the sidebar)"
  else
    echo "  Open:    http://${NAVI_HOST:-$(hostname -I 2>/dev/null | awk '{print $1}')}:$UI_PORT   (also in the Mainsail sidebar)"
  fi
  echo "  Service: sudo systemctl status $SERVICE"
}

# -- suite: also install the other FilaMind suite services next to flow (best effort) ------------
# Clones filamind-3d + filamind-screen beside this repo and runs each one's OWN installer:
#   filamind-3d     -> deploy/install-agent.sh   (the web-control backend as a managed service)
#   filamind-screen -> deploy/install-native.sh  (the native touch app .deb + the kiosk unit)
# Each step is isolated and NON-FATAL: a failure is reported and skipped, never aborting the rest,
# so this can extend a flow install with the suite but can never break it.
do_suite() {
  [ "$(id -u)" -eq 0 ] && { echo "Run as your printer user, not root." >&2; exit 1; }
  local org base d
  org="${FILAMIND_ORG:-https://github.com/filamind-app}"
  base="$(dirname "$APP")"
  info "Installing FilaMind suite services beside flow (best effort)"

  if (
    set -e
    d="$base/filamind-3d"
    # Full clone (not --depth 1) so tags come too - Moonraker's update_manager needs them for a real version.
    if [ -d "$d/.git" ]; then git -C "$d" pull --ff-only; else git clone "$org/filamind-3d.git" "$d"; fi
    bash "$d/deploy/install-agent.sh"
  ); then
    info "  filamind-3d agent: installed"
  else
    info "  filamind-3d agent: SKIPPED (it failed above) - retry with: bash $APP/scripts/install.sh suite"
  fi

  if (
    set -e
    d="$base/filamind-screen"
    # Full clone (not --depth 1) so tags come too - Moonraker's update_manager needs them for a real version.
    if [ -d "$d/.git" ]; then git -C "$d" pull --ff-only; else git clone "$org/filamind-screen.git" "$d"; fi
    bash "$d/deploy/install-native.sh"
  ); then
    info "  filamind-screen native: installed"
  else
    info "  filamind-screen native: SKIPPED (it failed above)"
  fi

  info "Suite step done - the flow Setup widget + Moonraker managed_services show what's installed."
}

# -- uninstall: reverse the full install (run as your printer user; uses sudo for /etc) ----------
do_uninstall() {
  [ "$(id -u)" -eq 0 ] && { echo "Please run as your printer user, not root."; exit 1; }

  info "Stopping and removing the service"
  sudo systemctl disable --now ${SERVICE} 2>/dev/null || true
  sudo rm -f /etc/systemd/system/${SERVICE}.service
  sudo systemctl daemon-reload || true

  info "Removing the nginx site + the /filamind/ subpath block"
  sudo rm -f /etc/nginx/sites-enabled/${SERVICE} /etc/nginx/sites-available/${SERVICE}
  for cand in /etc/nginx/sites-available/*; do
    [ -f "$cand" ] || continue
    if grep -q 'filamind-flow subpath' "$cand" 2>/dev/null; then
      sudo sed -i '/# >>> filamind-flow subpath >>>/,/# <<< filamind-flow subpath <<</d' "$cand" || true
    fi
  done
  sudo nginx -t >/dev/null 2>&1 && sudo systemctl reload nginx 2>/dev/null || true

  info "Removing the Mainsail sidebar entry + Moonraker registration"
  local navi="$PRINTER_DATA/config/.theme/navi.json"
  local mconf="$PRINTER_DATA/config/moonraker.conf"
  local asvc="$PRINTER_DATA/moonraker.asvc"
  if [ -f "$navi" ]; then
    python3 - "$navi" <<'PY' || true
import json, sys
p = sys.argv[1]
try:
    data = json.load(open(p))
except Exception:
    sys.exit(0)
if isinstance(data, list):
    data = [e for e in data if not (isinstance(e, dict) and e.get("title") == "FilaMind Flow")]
    with open(p, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
PY
  fi
  if [ -f "$mconf" ] && grep -q "update_manager ${SERVICE}" "$mconf"; then
    cp "$mconf" "$mconf.bak.filamind.$(date +%s)" || true
    prune_backups "$mconf"
    python3 - "$mconf" <<'PY' || true
import re, sys
p = sys.argv[1]
src = open(p).read()
with open(p, "w") as f:
    f.write(re.sub(r"\n\[update_manager filamind-flow\][^\[]*", "\n", src))
PY
  fi
  [ -f "$asvc" ] && sed -i "/^${SERVICE}\$/d" "$asvc" 2>/dev/null || true
  sudo systemctl restart moonraker 2>/dev/null || true

  info "Removing the sudo + udev rules"
  sudo rm -f /etc/sudoers.d/filamind /etc/udev/rules.d/99-stm32-dfu.rules
  sudo udevadm control --reload-rules 2>/dev/null || true

  info "Done - system integration removed. The app files are still at $APP."
  echo "  Delete them too with:  rm -rf \"$APP\""
}

# -- dispatch -------------------------------------------------------------------
CMD="${1:-install}"
case "$CMD" in
  sudoers) shift; do_sudoers "$@" ;;
  kiosk) shift; do_kiosk "$@" ;;
  native) shift; exec bash "$(cd "$(dirname "$0")/.." && pwd)/deploy/install-native.sh" "$@" ;;
  update) do_update ;;
  install) do_install ;;
  suite) shift; do_suite ;;
  uninstall) do_uninstall ;;
  *)
    echo "Unknown command: $CMD" >&2
    echo "Usage: install.sh [install|suite|uninstall|sudoers [user]|kiosk [user] [url]|kiosk --uninstall|native [--uninstall]|update]" >&2
    exit 2
    ;;
esac
