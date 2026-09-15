from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.robot_controller import RobotController
from app.state import WeldingState

router = APIRouter(prefix="/api")
state = WeldingState()
controller = RobotController()


class PointPayload(BaseModel):
    x: float
    y: float
    z: float


class WeavePayload(BaseModel):
    amplitude: float = 0.0
    frequency: float = 0.0
    duty_cycle: float = 0.0


class TogglePayload(BaseModel):
    enabled: bool


class WeldRequest(BaseModel):
    weave: WeavePayload | None = None
    arc_on: bool = True
    speed: float | None = None


@router.get("/status")
def get_status() -> dict[str, Any]:
    return {**state.as_status(), "robot": controller.status()}


@router.post("/connect")
def connect_robot() -> dict[str, Any]:
    return {"robot": controller.connect()}


class HomeRequest(BaseModel):
    speed: float | None = None


@router.post("/home")
def go_home(payload: HomeRequest | None = None) -> dict[str, Any]:
    speed = payload.speed if payload else None
    execution_log = [*controller.prepare_for_motion(), controller.go_home(speed)]
    simulated = any(step.get("simulated") for step in execution_log)
    errors = [step for step in execution_log if step.get("error") not in (None, 0)]
    return {
        "execution_log": execution_log,
        "robot": controller.status(),
        "simulated": simulated,
        "ok": not simulated and not errors,
        "errors": errors,
    }


@router.post("/free-drive")
def toggle_free_drive(payload: TogglePayload) -> dict[str, Any]:
    result = state.set_free_drive(payload.enabled, controller)
    return {"free_drive": state.free_drive, "command_result": result}


@router.post("/weave")
def update_weave(payload: WeavePayload) -> dict[str, Any]:
    state.set_weave(payload.model_dump())
    return {"weave": state.weave}


@router.post("/waypoints/{point_id}")
def save_waypoint(point_id: str, payload: PointPayload) -> dict[str, Any]:
    if point_id not in state.waypoints:
        raise HTTPException(status_code=404, detail="Unknown waypoint")
    state.set_waypoint(point_id, payload.model_dump())
    return {"waypoint": point_id, "position": state.waypoints[point_id]}


@router.post("/execute-box-weld")
def execute_box_weld(payload: WeldRequest) -> dict[str, Any]:
    if payload.weave is not None:
        state.set_weave(payload.weave.model_dump())
    plan, arc_sequence = state.build_box_weld_plan(payload.arc_on)
    execution_log = state.execute_box_weld(controller, payload.arc_on, payload.speed)
    simulated = any(step.get("simulated") for step in execution_log)
    errors = [step for step in execution_log if step.get("error") not in (None, 0)]
    return {
        "plan": plan,
        "arc_sequence": arc_sequence,
        "execution_log": execution_log,
        "weave": state.weave,
        "robot": controller.status(),
        "simulated": simulated,
        "ok": not simulated and not errors,
        "errors": errors,
    }


@router.post("/teach")
def teach_waypoint() -> dict[str, Any]:
    """Capture current robot position and save as next waypoint (P1-P4)."""
    if not state.free_drive:
        raise HTTPException(status_code=400, detail="Must enable free drive to teach waypoints")
    
    position = controller.get_current_position()
    point_id = state.teach_waypoint(position)
    
    return {
        "taught_point": point_id,
        "position": state.waypoints[point_id],
        "next_teach_point": state.next_teach_point,
        "waypoints": state.waypoints,
    }
