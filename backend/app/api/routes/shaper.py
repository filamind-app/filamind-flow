from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.models.schemas import ShaperAnalysis
from app.services import shaper_service

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
