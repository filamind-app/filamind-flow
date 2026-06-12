"""A minimal in-process Moonraker stub for end-to-end smoke tests.

Serves just enough of the Moonraker HTTP API — printer info, object queries, the
``config`` file root (in-memory), G-code script, upload/delete — for the real app
to come up against a real HTTP boundary and exercise its read AND gated-write
paths without a printer. State lives in :class:`StubState` so tests can seed
files and inspect what the app wrote.
"""

from __future__ import annotations

import socket
import threading
from dataclasses import dataclass, field
from typing import Any

import uvicorn
from fastapi import FastAPI, Form, Request, UploadFile

PRINTER_CFG = """\
[mcu]
serial: /dev/serial/by-id/usb-Klipper_stm32f103xe_TEST-if00

[printer]
kinematics: corexy
max_velocity: 500
max_accel: 5000

[stepper_x]
step_pin: PB13
dir_pin: PB12
enable_pin: !PB14
microsteps: 16
rotation_distance: 40

[tmc2209 stepper_x]
uart_pin: PC11
run_current: 0.8

[extruder]
step_pin: PB3
dir_pin: PB4
nozzle_diameter: 0.4
"""


def _parsed_config() -> dict[str, Any]:
    """The ``configfile.config`` mapping matching :data:`PRINTER_CFG`."""
    return {
        "mcu": {"serial": "/dev/serial/by-id/usb-Klipper_stm32f103xe_TEST-if00"},
        "printer": {"kinematics": "corexy", "max_velocity": "500", "max_accel": "5000"},
        "stepper_x": {
            "step_pin": "PB13",
            "dir_pin": "PB12",
            "enable_pin": "!PB14",
            "microsteps": "16",
            "rotation_distance": "40",
        },
        "tmc2209 stepper_x": {"uart_pin": "PC11", "run_current": "0.8"},
        "extruder": {"step_pin": "PB3", "dir_pin": "PB4", "nozzle_diameter": "0.4"},
    }


@dataclass
class StubState:
    """Mutable stub state a test can seed and inspect."""

    files: dict[str, str] = field(default_factory=lambda: {"printer.cfg": PRINTER_CFG})
    gcode_scripts: list[str] = field(default_factory=list)
    print_state: str = "standby"


def build_stub(state: StubState) -> FastAPI:
    app = FastAPI()

    @app.get("/server/info")
    async def server_info() -> dict[str, Any]:
        return {"result": {"klippy_state": "ready", "klippy_connected": True}}

    @app.get("/printer/info")
    async def printer_info() -> dict[str, Any]:
        return {
            "result": {
                "state": "ready",
                "state_message": "Printer is ready",
                "software_version": "v0.13.0-stub",
                "hostname": "stub",
            }
        }

    @app.get("/machine/system_info")
    async def system_info() -> dict[str, Any]:
        return {
            "result": {
                "system_info": {
                    "cpu_info": {"model": "stub", "cpu_count": 4},
                    "distribution": {"name": "StubOS"},
                }
            }
        }

    @app.get("/printer/objects/list")
    async def objects_list() -> dict[str, Any]:
        return {
            "result": {
                "objects": [
                    "webhooks",
                    "configfile",
                    "print_stats",
                    "idle_timeout",
                    "toolhead",
                    "mcu",
                    "stepper_enable",
                ]
            }
        }

    @app.get("/printer/objects/query")
    async def objects_query(request: Request) -> dict[str, Any]:
        wanted = request.query_params.keys()
        status: dict[str, Any] = {}
        for name in wanted:
            if name == "print_stats":
                status[name] = {"state": state.print_state, "filename": ""}
            elif name == "idle_timeout":
                status[name] = {"state": "Idle"}
            elif name == "webhooks":
                status[name] = {"state": "ready", "state_message": "Printer is ready"}
            elif name == "configfile":
                status[name] = {"config": _parsed_config(), "settings": _parsed_config()}
            elif name == "mcu":
                status[name] = {"mcu_version": "v0.13.0-stub"}
            elif name == "display_status":
                status[name] = {"progress": 0.0}
            else:
                status[name] = {}
        return {"result": {"status": status}}

    @app.get("/server/gcode_store")
    async def gcode_store() -> dict[str, Any]:
        return {"result": {"gcode_store": []}}

    @app.get("/server/files/list")
    async def files_list(root: str = "config") -> dict[str, Any]:
        if root != "config":
            return {"result": []}
        return {
            "result": [
                {"path": path, "modified": 0.0, "size": len(text), "permissions": "rw"}
                for path, text in sorted(state.files.items())
            ]
        }

    @app.get("/server/files/config/{path:path}")
    async def file_text(path: str) -> Any:
        from fastapi.responses import PlainTextResponse

        if path not in state.files:
            return PlainTextResponse("not found", status_code=404)
        return PlainTextResponse(state.files[path])

    @app.post("/server/files/upload")
    async def upload(
        file: UploadFile, root: str = Form("config"), path: str = Form("")
    ) -> dict[str, Any]:
        name = f"{path}/{file.filename}" if path else (file.filename or "unnamed")
        state.files[name] = (await file.read()).decode("utf-8")
        return {"result": {"item": {"path": name, "root": root}}}

    @app.delete("/server/files/config/{path:path}")
    async def delete(path: str) -> dict[str, Any]:
        state.files.pop(path, None)
        return {"result": {}}

    @app.post("/printer/gcode/script")
    async def gcode(script: str = "") -> dict[str, Any]:
        state.gcode_scripts.append(script)
        return {"result": "ok"}

    return app


class StubServer:
    """Runs the stub on an ephemeral localhost port in a daemon thread."""

    def __init__(self) -> None:
        self.state = StubState()
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        self.url = f"http://127.0.0.1:{self.port}"
        config = uvicorn.Config(
            build_stub(self.state), host="127.0.0.1", port=self.port, log_level="warning"
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)

    def start(self) -> None:
        self._thread.start()
        import time

        for _ in range(200):  # up to ~10 s
            if self._server.started:
                return
            time.sleep(0.05)
        raise RuntimeError("stub Moonraker failed to start")

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=5)
