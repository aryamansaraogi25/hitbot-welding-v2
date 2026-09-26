from fastapi.testclient import TestClient

from app.main import app
from app.robot_controller import RobotController


client = TestClient(app)


def test_move_linear_reports_controller_timeout_without_raising(monkeypatch):
    controller = RobotController()
    controller.proxy = object()

    def raise_timeout(*args, **kwargs):
        raise TimeoutError("controller did not respond")

    monkeypatch.setattr(controller, "_call", raise_timeout)

    result = controller.move_linear(1.0, 2.0, 3.0, speed=25.0)

    assert result["simulated"] is False
    assert result["command"].startswith("MoveL([1.0, 2.0, 3.0")
    assert result["error"] == "TimeoutError: controller did not respond"


def test_status_endpoint_reports_defaults():
    response = client.get("/api/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["free_drive"] is False
    assert payload["weave"] == {"amplitude": 0.0, "frequency": 0.0, "duty_cycle": 0.0}
    assert len(payload["waypoints"]) == 4
    assert payload["robot"]["activity"] in {"disconnected", "ready"}


def test_waypoint_submission_and_box_weld_execution():
    response = client.post(
        "/api/waypoints/P1",
        json={"x": 10.0, "y": 20.0, "z": 30.0},
    )
    assert response.status_code == 200

    response = client.post(
        "/api/execute-box-weld",
        json={
            "weave": {"amplitude": 1.5, "frequency": 3.0, "duty_cycle": 0.45},
            "arc_on": True,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["plan"][0]["id"] == "P1"
    assert payload["plan"][-1]["id"] == "P1"
    assert payload["arc_sequence"][0]["state"] == "ON"
    assert payload["arc_sequence"][-1]["state"] == "OFF"
    # Moves go through the Fairino XML-RPC MoveL; arc fires via ARCStart/ARCEnd.
    commands = [e["command"] for e in payload["execution_log"]]
    move_cmds = [c for c in commands if c.startswith("MoveL")]
    assert len(move_cmds) == 5  # approach P1, then weld P2->P3->P4->P1
    assert move_cmds[0].startswith("MoveL([10.0, 20.0, 30.0")
    # Arc must ignite AFTER reaching the seam start and end AFTER the last move.
    kinds = [c.split("(")[0] for c in commands]
    assert kinds.index("ARCStart") > kinds.index("MoveL")  # approach happens first
    assert kinds.index("ARCEnd") == len(kinds) - 1          # arc off is the final step
    assert kinds.index("ARCStart") < kinds.index("ARCEnd")


def test_box_weld_dry_run_has_no_arc():
    response = client.post("/api/execute-box-weld", json={"arc_on": False})
    assert response.status_code == 200
    commands = [e["command"] for e in response.json()["execution_log"]]
    # No arc or weave in a dry run (prepare-for-motion + MoveL steps only).
    assert not any(c.startswith(("ARCStart", "ARCEnd", "Weave")) for c in commands)
    assert sum(c.startswith("MoveL") for c in commands) == 5


def test_clear_waypoints_resets_state():
    response = client.post("/api/waypoints/reset")
    assert response.status_code == 200
    payload = response.json()
    assert payload["waypoints"]["P1"] == {"x": 0.0, "y": 0.0, "z": 0.0, "rx": 0.0, "ry": 0.0, "rz": 0.0}
    assert payload["next_teach_point"] == 1


def test_free_drive_toggle_sends_manual_mode_command():
    response = client.post("/api/free-drive", json={"enabled": True})
    assert response.status_code == 200
    payload = response.json()
    assert payload["free_drive"] is True
    assert payload["robot"]["activity"] == "free_drive"
    # Enter drag mode: manual mode first, then drag teach on (Fairino).
    steps = [s["command"] for s in payload["command_result"]["steps"]]
    assert steps == ["Mode(1)", "DragTeachSwitch(1)"]

    response = client.post("/api/free-drive", json={"enabled": False})
    payload = response.json()
    assert payload["free_drive"] is False
    steps = [s["command"] for s in payload["command_result"]["steps"]]
    assert steps == ["DragTeachSwitch(0)", "Mode(0)"]


def test_set_current_home_position_updates_controller_home():
    response = client.post("/api/home/current")
    assert response.status_code == 200
    payload = response.json()
    assert "home_joints" in payload
    assert len(payload["home_joints"]) == 6
    assert isinstance(payload["home_joints"][0], float)


def test_estop_and_disconnect_endpoints_are_supported():
    response = client.post("/api/estop")
    assert response.status_code == 200
    payload = response.json()
    assert payload["robot"]["connected"] is False

    response = client.post("/api/disconnect")
    assert response.status_code == 200
    payload = response.json()
    assert payload["robot"]["connected"] is False
