"""Red-Team Lab & Demo Mode endpoints.

Every run goes through the REAL pipeline (rule matrix -> AI output ->
independent Python validation -> Trust Gate -> security timeline). Scenarios
that need a specific incorrect AI answer use a clearly labelled prepared
fixture ("simulation-fixture"); the detection, scoring and blocking shown in
the results are always genuinely computed by the engines.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..audit import log_action
from ..database import get_db
from ..models import User
from ..schemas import LabRunRequest
from ..security import require_staff
from ..services.simulation import (
    DEMO_SCENARIOS,
    REDTEAM_SCENARIOS,
    SIMULATION_NOTE,
    list_scenarios,
    run_scenario,
)

router = APIRouter(prefix="/api", tags=["lab"])


def _run(
    db: Session,
    request: Request,
    user: User,
    scenarios: list[dict],
    scenario_id: str,
    registry: str,
) -> dict:
    if not any(scenario["id"] == scenario_id for scenario in scenarios):
        raise HTTPException(status_code=404, detail=f"Unknown scenario '{scenario_id}'")
    result = run_scenario(db, scenarios, scenario_id, registry, user.id)
    log_action(
        db,
        f"lab.{registry}_run",
        "complaint",
        result["complaint"]["code"],
        {
            "scenario": scenario_id,
            "expected": result["outcome"]["expected"],
            "actual": result["outcome"]["actual"],
            "matched": result["outcome"]["matched"],
        },
        user=user,
        request=request,
    )
    return result


@router.get("/redteam/scenarios")
def redteam_scenarios(user: User = Depends(require_staff)):
    return {
        "registry": "redteam",
        "note": SIMULATION_NOTE,
        "scenarios": list_scenarios(REDTEAM_SCENARIOS, "redteam"),
    }


@router.post("/redteam/run")
def redteam_run(
    payload: LabRunRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    return _run(db, request, user, REDTEAM_SCENARIOS, payload.scenario_id, "redteam")


@router.get("/demo/scenarios")
def demo_scenarios(user: User = Depends(require_staff)):
    return {
        "registry": "demo",
        "note": SIMULATION_NOTE,
        "scenarios": list_scenarios(DEMO_SCENARIOS, "demo"),
    }


@router.post("/demo/run")
def demo_run(
    payload: LabRunRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    return _run(db, request, user, DEMO_SCENARIOS, payload.scenario_id, "demo")
