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
# open http://printer.local:8080
```

The nginx template runs in **reverse-proxy mode**: it serves the SPA and proxies
Moonraker (`/server`, `/printer`, `/access`, `/machine`, `/websocket`) and the
backend (`/api`) on the same origin, so no CORS is involved. Build the frontend
with the env pointing at this origin (see the header of `nginx-filamind-flow.conf`).

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
support lands, reach the panel by URL (`http://printer.local:8080`) — a bookmark or
browser start page works well. (Editing Fluidd's built assets to inject a link is
possible but not recommended: it breaks on every update.)

## Notes

- `install.sh` requires Node.js and Python 3.10+ on the host.
- For a fully offline host, self-host the fonts (see `docs/ARCHITECTURE.md`).
