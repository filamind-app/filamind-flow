from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.config import Settings, get_settings
from app.models.schemas import (
    AxesMapResult,
    BeltComparison,
    NoiseResult,
    ResonanceFile,
    ResonanceFilesResponse,
    ShaperAnalysis,
    StaticExcitationResult,
)
from app.services import resonance_service, shaper_service

router = APIRouter(prefix="/shaper", tags=["shaper"])


@router.post("/analyze", response_model=ShaperAnalysis)
async def analyze_resonance(
    request: Request,
    scv: float = Query(5.0, description="Square corner velocity (mm/s)"),
    max_freq: float = Query(200.0, description="Maximum frequency to analyse (Hz)"),
    max_smoothing: float | None = Query(None, description="Cap on shaper smoothing"),
    damping_ratio: float | None = Query(None, description="Override the damping ratio"),
    axis: str | None = Query(None, description="Axis this CSV belongs to (x / y)"),
) -> ShaperAnalysis:
    """Analyses an uploaded resonance CSV → recommended input shaper + plot data.

    The request body is the raw ``.csv`` (Klipper PSD ``freq,psd_x,…`` or raw
    accelerometer ``time,accel_x,…``). Stateless: no printer or data dir needed.
    """
    raw = await request.body()
    try:
        result = shaper_service.analyze(
            raw,
            scv=scv,
            max_freq=max_freq,
            max_smoothing=max_smoothing,
            damping_ratio=damping_ratio,
            axis=axis,
        )
    except shaper_service.ShaperAnalysisError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ShaperAnalysis(**result)


@router.get("/files", response_model=ResonanceFilesResponse)
async def list_resonance_files(
    settings: Settings = Depends(get_settings),
) -> ResonanceFilesResponse:
    """Lists the resonance CSVs Klipper has written on the printer host."""
    return ResonanceFilesResponse(
        files=[ResonanceFile(**f) for f in resonance_service.list_files(settings.resonance_dirs)],
        dirs=resonance_service.resolve_dirs(settings.resonance_dirs),
    )


@router.post("/analyze-file", response_model=ShaperAnalysis)
async def analyze_resonance_file(
    path: str = Query(..., description="Host path of a resonance CSV (within the allowed dirs)"),
    axis: str | None = Query(None),
    scv: float = Query(5.0),
    max_freq: float = Query(200.0),
    settings: Settings = Depends(get_settings),
) -> ShaperAnalysis:
    """Analyses a resonance CSV that already exists on the printer host (no upload)."""
    try:
        result = resonance_service.analyze_file(
            settings.resonance_dirs, path, axis=axis, scv=scv, max_freq=max_freq
        )
    except shaper_service.ShaperAnalysisError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ShaperAnalysis(**result)


@router.post("/live-test", response_model=ShaperAnalysis)
async def live_resonance_test(
    axis: str = Query("x", description="Axis to excite: x or y"),
    scv: float = Query(5.0),
    max_freq: float = Query(200.0),
    settings: Settings = Depends(get_settings),
) -> ShaperAnalysis:
    """Runs a live ``TEST_RESONANCES`` on the printer, then analyses the result.

    **Moves the toolhead.** Print-guarded and requires a configured resonance
    tester; returns HTTP 400 with a clear message if either check fails.
    """
    try:
        result = await resonance_service.run_live_test(
            settings.moonraker_url, settings.resonance_dirs, axis=axis, scv=scv, max_freq=max_freq
        )
    except shaper_service.ShaperAnalysisError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ShaperAnalysis(**result)


@router.post("/noise", response_model=NoiseResult)
async def measure_axes_noise(settings: Settings = Depends(get_settings)) -> NoiseResult:
    """Runs ``MEASURE_AXES_NOISE`` to validate the accelerometer mount before testing.

    **Does not move the toolhead** (it dwells while reading the sensor). Print-guarded
    and requires a configured resonance tester; returns HTTP 400 with a clear message
    if either check fails.
    """
    try:
        result = await resonance_service.measure_noise(settings.moonraker_url)
    except shaper_service.ShaperAnalysisError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return NoiseResult(**result)


@router.post("/compare-belts", response_model=BeltComparison)
async def compare_belts(
    scv: float = Query(5.0),
    max_freq: float = Query(200.0),
    settings: Settings = Depends(get_settings),
) -> BeltComparison:
    """Runs a resonance test on each CoreXY belt diagonal and returns both captures.

    **Moves the toolhead** (two sweeps along the (1,1) and (1,-1) directions).
    Print-guarded and requires a configured resonance tester.
    """
    try:
        result = await resonance_service.compare_belts(
            settings.moonraker_url, settings.resonance_dirs, scv=scv, max_freq=max_freq
        )
    except shaper_service.ShaperAnalysisError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BeltComparison(
        belt_a=ShaperAnalysis(**result["belt_a"]),
        belt_b=ShaperAnalysis(**result["belt_b"]),
    )


@router.post("/axes-map", response_model=AxesMapResult)
async def calibrate_axes_map(
    z_height: float = Query(20.0, description="Z height for the strokes (mm)"),
    speed: float = Query(80.0, description="Stroke speed (mm/s)"),
    accel: float = Query(1500.0, description="Acceleration for the strokes (mm/s²)"),
    travel_speed: float = Query(120.0, description="Travel speed to the start point (mm/s)"),
    settings: Settings = Depends(get_settings),
) -> AxesMapResult:
    """Detects the accelerometer's ``axes_map`` by jogging the toolhead +X/+Y/+Z.

    **Moves the toolhead** (three 30 mm strokes + a 30 mm Z rise). Print-guarded and
    requires a configured resonance tester; returns HTTP 400 with a clear message if a
    check fails.
    """
    try:
        result = await resonance_service.calibrate_axes_map(
            settings.moonraker_url,
            settings.resonance_dirs,
            z_height=z_height,
            speed=speed,
            accel=accel,
            travel_speed=travel_speed,
        )
    except shaper_service.ShaperAnalysisError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AxesMapResult(**result)


@router.post("/excitate", response_model=StaticExcitationResult)
async def excitate_axis(
    axis: str = Query("x", description="Axis to excite: x or y"),
    freq: float = Query(50.0, description="Frequency to hold (Hz)"),
    duration: float = Query(15.0, description="Hold duration (s)"),
    max_freq: float = Query(200.0, description="Max frequency for the spectrogram (Hz)"),
    settings: Settings = Depends(get_settings),
) -> StaticExcitationResult:
    """Holds an axis vibrating near ``freq`` for ``duration`` s so you can touch parts
    to find what rattles, then returns a spectrogram + energy timeline.

    **Moves the toolhead** (buzzes in place at the probe point). Print-guarded and
    requires a configured resonance tester.
    """
    try:
        result = await resonance_service.run_static_excitation(
            settings.moonraker_url,
            settings.resonance_dirs,
            axis=axis,
            freq=freq,
            duration=duration,
            max_freq=max_freq,
        )
    except shaper_service.ShaperAnalysisError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StaticExcitationResult(**result)
