from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_status_endpoint_reports_defaults():
    response = client.get("/api/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["free_drive"] is False
    assert payload["weave"] == {"amplitude": 0.0, "frequency": 0.0, "duty_cycle": 0.0}
    assert len(payload["waypoints"]) == 4


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


def test_free_drive_toggle_sends_manual_mode_command():
    response = client.post("/api/free-drive", json={"enabled": True})
    assert response.status_code == 200
    payload = response.json()
    assert payload["free_drive"] is True
    # Enter drag mode: manual mode first, then drag teach on (Fairino).
    steps = [s["command"] for s in payload["command_result"]["steps"]]
    assert steps == ["Mode(1)", "DragTeachSwitch(1)"]

    response = client.post("/api/free-drive", json={"enabled": False})
    payload = response.json()
    assert payload["free_drive"] is False
    steps = [s["command"] for s in payload["command_result"]["steps"]]
    assert steps == ["DragTeachSwitch(0)", "Mode(0)"]
