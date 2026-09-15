# Hitbot Welding Dashboard

A lightweight FastAPI and HTML/JS/Tailwind dashboard for controlling a Hitbot S922 welding robot over a TCP/IP command bridge.

## Features
- Free-drive toggle
- Weaving pattern configuration
- Taught waypoint capture for P1 through P4
- 4-point box weld workflow with sequential linear motion and arc trigger sequencing
- Modular backend structure with a small robot controller abstraction

## Run locally (no virtualenv needed)
```bash
cd /home/xp/hitbotwelding
python3 -m pip install --user --break-system-packages -r requirements.txt
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open http://127.0.0.1:8000/ in your browser.

## Robot connection (Fairino SDK)
The S922 is a 6-axis cobot on the Fairino controller, so the backend drives it
by talking **XML-RPC directly to the controller on port 20003** (see
`app/robot_controller.py`). Pressing **Free Drive** switches the arm to manual
mode and enters drag teaching:

- ON  -> `Mode(1)` then `DragTeachSwitch(1)`
- OFF -> `DragTeachSwitch(0)` then `Mode(0)`

Click **Connect** in the dashboard to open the connection on demand; the status
pill shows Connected/Disconnected (hover it for the controller version, or the
error on failure). Setting `ROBOT_CONNECT=1` additionally auto-connects at
startup. Without either, the app runs in simulated mode (commands are echoed,
not sent):

```bash
export ROBOT_CONNECT=1          # auto-connect at startup
export ROBOT_IP=192.168.58.2    # controller IP (Fairino default)
export ROBOT_TOOL=0             # tool coordinate id for MoveL (default 0)
export ROBOT_USER=0             # user coordinate id for MoveL (default 0)
export ROBOT_SPEED=20           # default MoveL velocity percent (default 20)
export ROBOT_TIMEOUT=5          # per-call socket timeout, seconds (default 5)
export ROBOT_MOTION_TIMEOUT=120 # timeout for blocking MoveL/arc calls, seconds
```

Before any motion the box weld runs `RobotEnable(1)` → `DragTeachSwitch(0)` →
`Mode(0)`, because after Free Drive the arm is left in manual/drag mode where
`MoveL` is ignored. If the app is not connected, Execute runs in **simulated**
mode (the arm does not move) and the dashboard says so.

Every Fairino call returns an error code (`0` = success); the `/api/free-drive`
and `/api/execute-box-weld` responses report each step so failures are visible.

### Welding execution
The **Execute 4-Point Box Weld** button runs this sequence (`app/state.py`):

1. Rapid to the seam start **P1 with the arc OFF**
2. `WeaveSetPara` + `ARCStart` + `WeaveStart` (weave only if amplitude & frequency > 0)
3. Weld the seam **P2 → P3 → P4 → P1** (`MoveL`, oriented pose)
4. `WeaveEnd` + `ARCEnd`

**Uncheck "Arc On" for a dry run** — the full motion path with no arc, for
validating taught waypoints safely. Teach P1–P4 by hand first (Free Drive →
Teach); teaching now captures full 6-DOF pose (position **and** torch
orientation), which `MoveL` replays.

Welder settings are site-specific — set to match your welding setup before
firing a live arc:

```bash
export ROBOT_ARC_IOTYPE=0       # 0=controller I/O, 1=extended I/O
export ROBOT_ARC_NUM=0          # welder profile number
export ROBOT_ARC_TIMEOUT=10000  # arc ignition/extinguish timeout, ms
export ROBOT_WEAVE_NUM=0        # weave param config number
export ROBOT_WEAVE_TYPE=0       # 0=planar triangle (see Fairino WeaveSetPara)
```

### Networking
The controller is reached over a **direct ethernet link**, not WiFi. Give the
PC's wired interface an IP on the robot's subnet and verify before connecting:

```bash
sudo ip addr add 192.168.58.1/24 dev <eth>   # robot is 192.168.58.2 by default
ping -c3 192.168.58.2
python3 scripts/diagnose_robot.py            # layer-by-layer check (moves the arm!)
```

> Note: we talk raw XML-RPC rather than using the vendored Fairino SDK because
> the current SDK build requires the CNDE state port (20005), which FR5 v3.8.x
> firmware does not serve. `app/fairino/` remains vendored for reference only.
