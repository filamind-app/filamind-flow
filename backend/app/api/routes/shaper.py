from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.config import Settings, get_settings
from app.models.schemas import ResonanceFile, ResonanceFilesResponse, ShaperAnalysis
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
