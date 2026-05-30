# Deploying FilaMind Flow

These templates install FilaMind Flow next to an existing Klipper + Moonraker
setup. Adjust the user (`pi`), paths, and host (`printer.local`) to your machine.

## 1. Get the code on the host

```bash
cd ~
git clone https://github.com/your-org/filamind-flow.git
cd filamind-flow
chmod +x deploy/install.sh
./deploy/install.sh        # builds frontend/dist and the backend venv
```

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

Mainsail can show a custom sidebar entry. Place `deploy/mainsail-navi.json` as
`~/printer_data/config/.theme/navi.json` (merge if the file already exists) and
set `href` to your panel URL. Verify the field names against the current
[Mainsail docs](https://docs.mainsail.xyz/) — the custom-navigation format can
change between releases.

### Fluidd

Fluidd does not use the same `navi.json` mechanism. Until a native entry is added,
bookmark the panel URL (`http://printer.local:8080`) or add it via any available
custom-link feature in your Fluidd version.

## Notes

- `install.sh` requires Node.js and Python 3.10+ on the host.
- For a fully offline host, self-host the fonts (see `docs/ARCHITECTURE.md`).
