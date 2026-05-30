# Test printer for FilaMind Flow development

You need a Moonraker instance to develop against. Two options:

## A) Against a real printer (recommended)

Develop against any real Klipper/Moonraker host on your LAN via the Vite dev
proxy — no CORS issues and **no changes to the printer's config** (the proxy
strips the browser Origin; your machine just needs to be in Moonraker's
`trusted_clients`, which LAN IPs usually are).

```bash
# frontend: copy the example and set your printer IP
cp frontend/.env.development.example frontend/.env.development.local
#   MOONRAKER_PROXY_TARGET=http://<printer-ip>:7125
cd frontend && npm run dev          # http://localhost:5173 -> proxy -> printer

# backend (separate terminal): point it at the same printer
cd backend
FILAMIND_MOONRAKER_URL=http://<printer-ip>:7125 FILAMIND_PORT=8001 python -m app
```

Open <http://localhost:5173> — the header badge reads **Connected**.

> Verified against a BigTreeTech CB1 (`klippy_state=ready`) this way.

## B) Simulated printer in Docker (optional)

[`docker-compose.yml`](docker-compose.yml) runs
[mainsail-crew/virtual-klipper-printer](https://github.com/mainsail-crew/virtual-klipper-printer)
— a simulated Klipper (via `simulavr`) + Moonraker on `:7125`.

```bash
cd dev/virtual-printer
docker compose up -d
```

Then point FilaMind at `http://localhost:7125` (the frontend default).

> Caveat: `simulavr` (the simulated AVR MCU) does not run on every kernel — on
> some WSL2 kernels the firmware fails to connect (`mcu 'mcu': Serial connection
> closed`). If `klippy_state` never becomes `ready`, use option A instead.
