from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, overridable via FILAMIND_* env vars or a .env file."""

    model_config = SettingsConfigDict(env_prefix="FILAMIND_", env_file=".env", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"

    # Base URL of the Moonraker instance this panel sits in front of.
    moonraker_url: str = "http://localhost:7125"

    # Which host this deployment serves: "mainsail" (default sidebar) or "suite" (FilaMind suite).
    # Mirrors the frontend VITE_HOST_MODE; lets the API adjust host-specific policy if needed.
    host_mode: str = "mainsail"

    # FilaMind Setup: GUI-driven install/update/remove run privileged host operations, so they are
    # OFF by default — the catalog + installed-status stay read-only until an operator opts in
    # (FILAMIND_SETUP_WRITES=true) on the host. The filamind-setup CLI is the alternative.
    setup_writes_enabled: bool = False

    # Firmware toolchain locations (Firmware Upgrade widget).
    klipper_dir: str = "~/klipper"
    katapult_dir: str = "~/katapult"

    # KlipperScreen install dir - its themes live under <klipperscreen_dir>/styles/ (outside any
    # Moonraker file root, so the theme builder writes there host-side). KlipperScreen Studio.
    klipperscreen_dir: str = "~/KlipperScreen"

    # FilaMind Kiosk: the on-host URL the touchscreen browser opens when the kiosk takes over the
    # screen (same-origin nginx bundle; scripts/install.sh kiosk bakes this into the systemd unit).
    kiosk_url: str = "http://localhost:8090"

    # Where FilaMind keeps its own data (per-board firmware profiles, etc.).
    data_dir: str = "~/printer_data/config/filamind"

    # Input Shaping archive: how many runs to keep PER KIND under
    # <data_dir>/input-shaper-archive/ (older runs are pruned). Keeps the SD card light.
    shaper_archive_keep_n: int = 20

    # Config Editor: how many pre-save snapshots to keep PER FILE under filamind-backups/
    # in the config root (older ones are pruned on each save). Keeps the SD card light.
    config_backup_keep_n: int = 20

    # Comma-separated dirs to scan for the resonance CSVs Klipper writes.
    # TEST_RESONANCES/SHAPER_CALIBRATE default to /tmp, but many setups also keep
    # captures under printer_data/config. Override with FILAMIND_RESONANCE_DIRS
    # (e.g. when FilaMind runs off the printer host). - Input Shaping widget.
    resonance_dirs: str = "/tmp,~/printer_data/config,~/printer_data/config/input_shaper"

    # Comma-separated browser origins allowed to call this API.
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        """The configured CORS origins as a list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Returns a cached Settings instance."""
    return Settings()
