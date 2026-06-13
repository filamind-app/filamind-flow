# Deploying FilaMind Flow

These templates install FilaMind Flow next to an existing Klipper + Moonraker
setup. Adjust the user (`pi`), paths, and host (`printer.local`) to your machine.

## Quick install (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/filamind-app/filamind-flow/main/scripts/install.sh | bash
```

That single command performs everything below (service, nginx, sidebar, update
manager). The steps that follow are for a manual install or to understand what it does.

## 1. Get the code on the host

```bash
cd ~ && git clone https://github.com/filamind-app/filamind-flow.git
```

The UI ships pre-built in `frontend/dist`, so no Node.js is needed on the printer.

## 2. Backend service (systemd)

```bash
sudo cp deploy/filamind-flow.service /etc/systemd/system/
sudoedit /etc/systemd/system/filamind-flow.service   # check User + paths
sudo systemctl daemon-reload
sudo systemctl enable --now filamind-flow
curl http://localhost:8000/api/health                # {"status":"ok",...}
```

## 3. Serve the frontend (nginx)

```bash
sudo cp deploy/nginx-filamind-flow.conf /etc/nginx/sites-available/filamind-flow
# edit `root` to .../filamind-flow/frontend/dist
sudo ln -s /etc/nginx/sites-available/filamind-flow /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
# open http://<your-printer-ip>:8090
```

The nginx template runs in **reverse-proxy mode**: it serves the SPA and proxies
Moonraker (`/server`, `/printer`, `/access`, `/machine`, `/websocket`) and the
backend (`/api`) on the same origin, so no CORS is involved. Serve the pre-built
`frontend/dist` **as-is** — it resolves Moonraker, the websocket and the backend
from `window.location`, so it works at whatever host/IP you reach it by. Do **not**
set any `VITE_*` override (that would hardcode a host and break other clients).

> **Direct mode (alternative):** skip the Moonraker proxy blocks and let the
> browser hit Moonraker on `:7125` directly. Then add the panel's origin to
> Moonraker's `[authorization] cors_domains` so the requests are allowed.

## 4. Auto-updates (Moonraker)

Append `deploy/moonraker-update_manager.conf` to your `moonraker.conf` so the
panel appears in Mainsail/Fluidd's update manager and updates with one click.

## 5. Sidebar link

### Mainsail

Mainsail supports custom sidebar links via `navi.json`. Place
`deploy/mainsail-navi.json` at `~/printer_data/config/.theme/navi.json` (merge into
the existing array if the file is already there) and set `href` to your panel URL.
Prefer the **LAN IP** (ideally a DHCP-reserved one) over `<hostname>.local` — mDNS
fails on many clients (Windows without Bonjour, Android, other subnets, VPN). The
one-line installer uses the LAN IP by default; override with `FILAMIND_PUBLIC_HOST`.
The `icon` field is an SVG path string on a 24×24 viewBox (Material-Design-Icon
style); the bundled entry uses a brutalist "F". Docs:
[Mainsail → Navigation](https://docs.mainsail.xyz/settings/navigation/).

> Host-preserving tip: serve FilaMind Flow at a subpath on Mainsail's own origin and
> use a relative `href` (e.g. `/filamind/`) so the link works regardless of the
> hostname/IP used to reach the printer.

### Fluidd

Fluidd does **not** support custom sidebar links yet — it is an open feature request
([fluidd-core/fluidd#472](https://github.com/fluidd-core/fluidd/issues/472)). Its
`.fluidd-theme` folder customizes only styling/logo, not navigation. Until native
support lands, reach the panel by URL (`http://<your-printer-ip>:8090`) — a bookmark or
browser start page works well. (Editing Fluidd's built assets to inject a link is
possible but not recommended: it breaks on every update.)

## 6. FilaMind Kiosk (optional — run FilaMind on the touchscreen)

To put FilaMind Flow **on the printer's physical touchscreen** instead of (or alongside)
KlipperScreen, install the kiosk once on the host:

```bash
sudo bash deploy/install-kiosk.sh            # user + http://localhost:8090 by default
sudo bash deploy/install-kiosk.sh biqu http://localhost:8090
sudo bash deploy/install-kiosk.sh --uninstall
```

It **auto-detects** how your screen is driven — **X11** (Xorg/`xinit`, how most KlipperScreen
images run) or **Wayland** (`cage` on KMS) — by reading `KlipperScreen.service`, installs Chromium +
the right compositor, and writes a `filamind-kiosk` systemd service that **conflicts with
KlipperScreen** (starting one stops the other). It is **not** enabled at boot — KlipperScreen stays
the default. The installer prints the detected mode/browser and stops with a clear message if it
can't find a browser or a usable display stack. Switch from the app
(**KlipperScreen Studio → Kiosk**) or over SSH:

```bash
sudo systemctl start filamind-kiosk     # FilaMind takes the screen
sudo systemctl start KlipperScreen      # hand it back (also recovers a dark screen)
```

A plain switch is reboot-recoverable; "Make FilaMind the default" in the widget (or
`sudo systemctl enable filamind-kiosk && sudo systemctl disable KlipperScreen`) persists it.
The app's toggle uses the same passwordless-sudo rule as the flasher (`deploy/setup-sudoers.sh`).

If the screen stays dark after switching, inspect why:

```bash
systemctl status filamind-kiosk --no-pager
journalctl -u filamind-kiosk -b --no-pager | tail -40
```

## Notes

- `install.sh` requires Node.js and Python 3.10+ on the host.
- For a fully offline host, self-host the fonts (see `docs/ARCHITECTURE.md`).
