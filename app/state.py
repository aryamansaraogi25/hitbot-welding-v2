from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.robot_controller import RobotController


@dataclass
class WeldingState:
    free_drive: bool = False
    speed: float = 20.0
    weave: dict[str, float] = field(
        default_factory=lambda: {"amplitude": 0.0, "frequency": 0.0, "duty_cycle": 0.0}
    )
    waypoints: dict[str, dict[str, float]] = field(
        default_factory=lambda: {
            "P1": {"x": 0.0, "y": 0.0, "z": 0.0, "rx": 0.0, "ry": 0.0, "rz": 0.0},
            "P2": {"x": 100.0, "y": 0.0, "z": 0.0, "rx": 0.0, "ry": 0.0, "rz": 0.0},
            "P3": {"x": 100.0, "y": 100.0, "z": 0.0, "rx": 0.0, "ry": 0.0, "rz": 0.0},
            "P4": {"x": 0.0, "y": 100.0, "z": 0.0, "rx": 0.0, "ry": 0.0, "rz": 0.0},
        }
    )
    last_plan: list[dict[str, Any]] = field(default_factory=list)
    last_arc_sequence: list[dict[str, Any]] = field(default_factory=list)
    last_execution: list[dict[str, Any]] = field(default_factory=list)
    next_teach_point: int = 1  # Track which waypoint to teach next

    def as_status(self) -> dict[str, Any]:
        return {
            "free_drive": self.free_drive,
            "speed": self.speed,
            "weave": self.weave,
            "waypoints": self.waypoints,
            "last_plan": self.last_plan,
            "last_arc_sequence": self.last_arc_sequence,
            "next_teach_point": self.next_teach_point,
        }

    def set_free_drive(
        self, enabled: bool, controller: RobotController | None = None
    ) -> dict[str, Any] | None:
        """Toggle free-drive and, if a controller is given, put the manipulator
        into drag (free-drive / manual) mode via the Hitbot API."""
        self.free_drive = enabled
        if controller is None:
            return None
        return controller.set_free_drive(enabled)

    def set_speed(self, speed: float | None) -> None:
        if speed is None:
            return
        self.speed = float(speed)

    def set_weave(self, weave: dict[str, float]) -> None:
        self.weave = {
            "amplitude": float(weave.get("amplitude", 0.0)),
            "frequency": float(weave.get("frequency", 0.0)),
            "duty_cycle": float(weave.get("duty_cycle", 0.0)),
        }

    def clear_waypoints(self) -> None:
        self.waypoints = {
            "P1": {"x": 0.0, "y": 0.0, "z": 0.0, "rx": 0.0, "ry": 0.0, "rz": 0.0},
            "P2": {"x": 0.0, "y": 0.0, "z": 0.0, "rx": 0.0, "ry": 0.0, "rz": 0.0},
            "P3": {"x": 0.0, "y": 0.0, "z": 0.0, "rx": 0.0, "ry": 0.0, "rz": 0.0},
            "P4": {"x": 0.0, "y": 0.0, "z": 0.0, "rx": 0.0, "ry": 0.0, "rz": 0.0},
        }
        self.next_teach_point = 1

    def set_waypoint(self, point_id: str, point: dict[str, float]) -> None:
        # Preserve any previously-taught orientation when only x/y/z are edited.
        existing = self.waypoints.get(point_id, {})
        self.waypoints[point_id] = {
            "x": float(point.get("x", 0.0)),
            "y": float(point.get("y", 0.0)),
            "z": float(point.get("z", 0.0)),
            "rx": float(point.get("rx", existing.get("rx", 0.0))),
            "ry": float(point.get("ry", existing.get("ry", 0.0))),
            "rz": float(point.get("rz", existing.get("rz", 0.0))),
        }

    def teach_waypoint(self, position: dict[str, float]) -> str:
        """Teach the next waypoint (P1-P4) from current robot position."""
        if self.next_teach_point > 4:
            self.next_teach_point = 1
        point_id = f"P{self.next_teach_point}"
        self.set_waypoint(point_id, position)
        self.next_teach_point += 1
        return point_id

    def build_box_weld_plan(self, arc_on: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        order = ["P1", "P2", "P3", "P4", "P1"]
        plan: list[dict[str, Any]] = []
        for point_id in order:
            point = self.waypoints[point_id]
            plan.append({
                "id": point_id,
                "position": point,
                "move": "LINEAR",
                "weave": self.weave,
            })

        arc_sequence: list[dict[str, Any]] = []
        if arc_on:
            arc_sequence.append({"step": 0, "state": "ON", "target": "P1"})
            for index, point_id in enumerate(order[1:], start=1):
                arc_sequence.append({"step": index, "state": "ON", "target": point_id})
            arc_sequence.append({"step": len(order), "state": "OFF", "target": "P1"})

        self.last_plan = plan
        self.last_arc_sequence = arc_sequence
        return plan, arc_sequence

    def _move_to(
        self, controller: RobotController, pos: dict[str, float], speed: float | None
    ) -> dict[str, Any]:
        return controller.move_linear(
            pos["x"], pos["y"], pos["z"],
            pos.get("rx", 0.0), pos.get("ry", 0.0), pos.get("rz", 0.0),
            speed=speed,
        )

    def execute_box_weld(
        self, controller: RobotController, arc_on: bool, speed: float | None = None
    ) -> list[dict[str, Any]]:
        """Run the 4-point box weld.

        Sequence: rapid to the seam start (P1) with the arc OFF, ignite the arc,
        start weaving if configured, weld the seam P2->P3->P4->P1, then stop
        weaving and extinguish the arc. With arc_on=False it is a dry run --
        the full motion path with no arc, for validating waypoints safely.
        """
        plan, _ = self.build_box_weld_plan(arc_on)
        execution_log: list[dict[str, Any]] = []
        weaving = arc_on and self.weave["amplitude"] > 0 and self.weave["frequency"] > 0
        effective_speed = float(speed) if speed is not None else float(self.speed)
        controller.default_speed = effective_speed
        controller.set_activity("moving")

        # Ensure the arm is enabled, out of drag mode, and in automatic mode so
        # MoveL actually runs (Free Drive leaves it in manual/drag mode).
        execution_log.extend(controller.prepare_for_motion())

        # Approach the seam start with the arc off.
        execution_log.append(self._move_to(controller, plan[0]["position"], effective_speed))

        if arc_on:
            if weaving:
                execution_log.append(
                    controller.weave_set_para(self.weave["frequency"], self.weave["amplitude"])
                )
            execution_log.append(controller.arc_start())
            controller.set_activity("welding")
            if weaving:
                execution_log.append(controller.weave_start())

        # Weld the seam through the remaining corners and back to the start.
        for step in plan[1:]:
            execution_log.append(self._move_to(controller, step["position"], effective_speed))

        if arc_on:
            if weaving:
                execution_log.append(controller.weave_end())
            execution_log.append(controller.arc_end())

        self.last_execution = execution_log
        errors = [step for step in execution_log if step.get("error") not in (None, 0)]
        controller.set_activity("fault" if errors else ("ready" if not arc_on else "ready"))
        return execution_log
