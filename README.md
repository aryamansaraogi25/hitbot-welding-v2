# Hitbot Welding

A lightweight FastAPI dashboard for controlling a Hitbot welding robot from a browser.

## Features
- Robot status and control interface
- Web-based dashboard UI
- Simulated mode for local testing without a live robot
- API layer for robot communication and command handling

## Requirements
- Python 3.10+
- pip
- A reachable robot controller for live operation

## Quick Start
```bash
cd hitbotwelding
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Run the app
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open the dashboard in your browser:
```text
http://127.0.0.1:8000/
```

## Run tests
```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q
```

## Notes
- If the robot is not connected, the app can still run in simulated mode.
- For real welding operations, confirm the controller is available on the network and the setup is safe.
