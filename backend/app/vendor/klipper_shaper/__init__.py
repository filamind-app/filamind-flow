"""Klipper's input-shaper resonance math, vendored from the Klipper firmware
project (``klippy/extras/shaper_calibrate.py`` and ``shaper_defs.py``).

Upstream: https://github.com/Klipper3d/klipper — Copyright (C) 2020-2024
Dmitry Butyugin and Kevin O'Connor, distributed under the GNU GPLv3 (the same
license as FilaMind Flow). The files are kept verbatim except for one import in
``shaper_calibrate.py`` (made relative to this package). They run standalone —
``ShaperCalibrate(printer=None)`` computes serially with only numpy, no Klipper
host and no multiprocessing — which is exactly how this widget uses them.
"""

from . import shaper_calibrate, shaper_defs

__all__ = ["shaper_calibrate", "shaper_defs"]
