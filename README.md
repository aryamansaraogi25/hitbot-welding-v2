# Hitbot Welding Dashboard

A FastAPI web app for controlling a Hitbot S922 welding robot from a browser dashboard.

## Overview
This project provides:
- A browser UI for robot control and status
- Free-drive mode toggling and waypoint teaching
- Weave configuration and 4-point box weld execution
- A simulated mode for testing without a live robot connection
- A Python API layer that can talk to the Fairino controller over XML-RPC

## Requirements
- Python 3.10+
- A network connection to the robot controller
- Optional: a real robot and controller access for live motion testing

## Clone and run
```bash
git clone <your-repository-url>
cd hitbotwelding
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Start the app:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open the dashboard here:
```text
http://127.0.0.1:8000/
```

## Run tests
```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q
```

> This avoids external ROS pytest plugins from being auto-loaded in environments where they are not installed.

## Optional environment variables
```bash
export ROBOT_CONNECT=1
export ROBOT_IP=192.168.58.2
export ROBOT_TOOL=0
export ROBOT_USER=0
export ROBOT_SPEED=20
export ROBOT_TIMEOUT=5
export ROBOT_MOTION_TIMEOUT=120
export ROBOT_ARC_IOTYPE=0
export ROBOT_ARC_NUM=0
export ROBOT_ARC_TIMEOUT=10000
export ROBOT_WEAVE_NUM=0
export ROBOT_WEAVE_TYPE=0
```

## Robot connection notes
The robot is reached over a direct Ethernet link, not Wi-Fi. Use a wired interface on the same subnet as the controller and verify the connection before live motion.

```bash
ping -c3 192.168.58.2
python3 scripts/diagnose_robot.py
```

If the robot is not connected, the app runs in simulated mode and logs commands without sending them to the controller.

## Project structure
```text
.
├── app/
│   ├── fairino/
│   ├── static/
│   ├── api.py
│   ├── main.py
│   ├── robot_controller.py
│   ├── state.py
│   └── __init__.py
├── scripts/
├── tests/
├── README.md
├── requirements.txt
├── pytest.ini
├── .gitignore
└── robot_communication.txt
```

## Notes
- The dashboard is intended for a valid robot configuration and a safe testing setup.
- For live weld operations, verify all waypoints and dry-run the motion before enabling the arc.
- The app includes a simulated fallback so it can be inspected without a connected controller.
