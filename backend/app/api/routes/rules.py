"""Rules engine: safe-by-default IF-THEN automation. Engine + each rule are opt-in; gcode actions
are gated by the printer guard. Evaluation runs in a background tick (see app lifespan)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from app.config import Settings, get_settings
from app.models.schemas import EngineToggle, Rule, RulesState, RulesView
from app.services import rules_engine

router = APIRouter(prefix="/rules", tags=["rules"])


@router.get("", response_model=RulesView)
async def get_rules(settings: Settings = Depends(get_settings)) -> RulesView:
    """The engine on/off state, the rules, and the recent fire log."""
    state = rules_engine.list_rules(settings.data_dir)
    return RulesView(
        enabled=state["enabled"],
        rules=state["rules"],
        log=rules_engine.read_log(settings.data_dir),
    )


@router.put("/engine", response_model=RulesState)
async def set_engine(req: EngineToggle, settings: Settings = Depends(get_settings)) -> RulesState:
    """Master switch. While off, the background tick is a no-op (nothing fires)."""
    state = rules_engine.set_engine_enabled(settings.data_dir, req.enabled)
    return RulesState(**state)


@router.post("", response_model=Rule)
async def upsert_rule(rule: Rule, settings: Settings = Depends(get_settings)) -> Rule:
    """Create or replace a rule (matched by id). New rules are disarmed until enabled."""
    try:
        stored = rules_engine.upsert_rule(settings.data_dir, rule.model_dump())
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Rule(**stored)


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(rule_id: str, settings: Settings = Depends(get_settings)) -> Response:
    """Remove a rule."""
    if not rules_engine.delete_rule(settings.data_dir, rule_id):
        raise HTTPException(status_code=404, detail="rule not found")
    return Response(status_code=204)
