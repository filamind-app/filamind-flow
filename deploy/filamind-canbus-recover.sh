#!/bin/sh
# FilaMind Flow: recover the CAN bus after the USB-CAN adapter (re)appears - installed to
# /usr/local/bin/filamind-canbus-recover by scripts/install.sh, triggered by 99-filamind-canbus.rules.
#
# Flashing the adapter over USB-DFU leaves it needing a power-cycle to re-enumerate; on a host whose
# USB hub can't switch port power in software, that is one physical replug. This makes the replug the
# ONLY step: bring the interface up with the HOST's own settings, then reconnect Klipper - but ONLY
# if it is stuck, so a ready or printing printer is never interrupted.
IFACE="${1:-can0}"

klippy_state() {
  curl -s --max-time 5 http://localhost:7125/printer/info 2>/dev/null |
    python3 -c 'import sys,json; print(json.load(sys.stdin)["result"]["state"])' 2>/dev/null || true
}

firmware_restart() {
  curl -s --max-time 5 -X POST http://localhost:7125/printer/firmware_restart >/dev/null 2>&1 || true
}

iface_up() { ip link show "$1" 2>/dev/null | grep -qw UP; }

# The bus's *configured* bitrate from Moonraker (empty if unavailable) - so a fallback never forces a
# wrong bitrate on a bus that isn't the common 1 Mbit.
configured_bitrate() {
  curl -s --max-time 5 http://localhost:7125/machine/system_info 2>/dev/null |
    python3 -c 'import sys,json; print(json.load(sys.stdin)["result"]["system_info"]["canbus"].get(sys.argv[1],{}).get("bitrate") or "")' "$1" 2>/dev/null || true
}

# 1) Let the host's own mechanism (ifupdown allow-hotplug / systemd-networkd) configure the interface
#    with the user's settings first; only step in if it did NOT come up - so we never clobber a bus
#    already brought up with the right timing. When we do step in, prefer the host's ifupdown stanza
#    (its exact bitrate / sample-point / txqueuelen); otherwise use the bus's configured bitrate from
#    Moonraker (falling back to 1 Mbit only as a last resort) with the CiA-standard sample-point.
sleep 2
if ! iface_up "$IFACE"; then
  if command -v ifup >/dev/null 2>&1 &&
    grep -qs "iface ${IFACE} " /etc/network/interfaces /etc/network/interfaces.d/* 2>/dev/null; then
    ifup "$IFACE" 2>/dev/null || true
  else
    br="$(configured_bitrate "$IFACE")"
    br="${br:-1000000}"
    ip link set "$IFACE" down 2>/dev/null || true
    ip link set "$IFACE" type can bitrate "$br" sample-point 0.875 2>/dev/null || true
    ip link set "$IFACE" txqueuelen 1024 2>/dev/null || true
  fi
  ip link set "$IFACE" up 2>/dev/null || true
fi

# 2) Reconnect Klipper - but only when it is stuck (shutdown/error). A "ready" printer (idle OR
#    printing) is left untouched, so this never interrupts a print; "startup" reconnects on its own
#    once the bus is up. A firmware restart issued as the bus settles can hit a one-off MCU-reset
#    race ("Failed automated reset of MCU ..."), so restart and watch the outcome, retrying (up to
#    3x) until the printer is ready.
sleep 1
case "$(klippy_state)" in
  shutdown | error)
    tries=0
    while [ "$tries" -lt 3 ]; do
      firmware_restart
      settled=0
      n=0
      while [ "$n" -lt 8 ]; do
        sleep 2
        st="$(klippy_state)"
        case "$st" in
          ready | printing | paused)
            settled=1
            break
            ;;
          error) break ;; # race hit - break out to restart again
        esac
        n=$((n + 1))
      done
      [ "$settled" = 1 ] && break
      tries=$((tries + 1))
    done
    ;;
esac
exit 0
