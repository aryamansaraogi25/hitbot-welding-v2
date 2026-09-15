from __future__ import annotations

import os
import socket
import xmlrpc.client
from typing import Any


class RobotController:
    """Bridge to the Hitbot S922 (Fairino FR-series controller) over its
    XML-RPC command interface on port 20003.

    We talk XML-RPC directly rather than through the vendored Fairino SDK: the
    SDK build we have requires the CNDE state port (20005), which this robot's
    firmware (FR5 v3.8.x) does not serve. XML-RPC carries every command we need
    (enable, mode, drag teach, pose, linear move) and returns simple
    ``[error, ...]`` / ``error`` values, so it is firmware-version-proof and has
    no background reconnect threads that can hang a call.

    A real connection is only opened when ROBOT_CONNECT is truthy or the UI
    Connect button is pressed, so the app runs simulated by default.

    Environment:
      ROBOT_CONNECT=1          auto-connect at startup
      ROBOT_IP=192.168.58.2    controller IP (Fairino default)
      ROBOT_TOOL=0             tool coordinate id used for MoveL (default 0)
      ROBOT_USER=0             user coordinate id used for MoveL (default 0)
      ROBOT_SPEED=20           default MoveL velocity percent (default 20)
      ROBOT_TIMEOUT=5          per-call socket timeout in seconds (default 5)
    """

    XMLRPC_PORT = 20003

    def __init__(self, ip: str | None = None) -> None:
        self.ip = ip or os.getenv("ROBOT_IP", "192.168.58.2")
        self.tool = int(os.getenv("ROBOT_TOOL", "0"))
        self.user = int(os.getenv("ROBOT_USER", "0"))
        self.default_speed = float(os.getenv("ROBOT_SPEED", "20"))
        self.timeout = float(os.getenv("ROBOT_TIMEOUT", "5"))
        # MoveL/arc calls block until the motion finishes, so they need a much
        # longer timeout than a quick status query.
        self.motion_timeout = float(os.getenv("ROBOT_MOTION_TIMEOUT", "120"))
        # Welder/weave config (site-specific — set to match your welding setup).
        self.arc_iotype = int(os.getenv("ROBOT_ARC_IOTYPE", "0"))  # 0=controller IO, 1=extended IO
        self.arc_num = int(os.getenv("ROBOT_ARC_NUM", "0"))        # welder profile number
        self.arc_timeout = int(os.getenv("ROBOT_ARC_TIMEOUT", "10000"))  # ignition/extinguish timeout, ms
        self.weave_num = int(os.getenv("ROBOT_WEAVE_NUM", "0"))    # weave param config number
        self.weave_type = int(os.getenv("ROBOT_WEAVE_TYPE", "0"))  # 0=planar triangle, see Fairino WeaveSetPara
        # Home joint configuration (degrees). Default = all joints at zero.
        self.home_joints = [float(v) for v in os.getenv("ROBOT_HOME_JOINTS", "0,0,0,0,0,0").split(",")]
        self.proxy: xmlrpc.client.ServerProxy | None = None
        self.connected = False
        self.connect_error: str | None = None
        self.controller_version: str | None = None
        if os.getenv("ROBOT_CONNECT", "").lower() in ("1", "true", "yes"):
            self.connect()

    def _call(self, name: str, *args: Any, timeout: float | None = None) -> Any:
        """Invoke an XML-RPC method with a bounded socket timeout so a stalled
        controller never hangs the request forever."""
        old = socket.getdefaulttimeout()
        socket.setdefaulttimeout(timeout or self.timeout)
        try:
            return getattr(self.proxy, name)(*args)
        finally:
            socket.setdefaulttimeout(old)

    def connect(self) -> dict[str, Any]:
        """(Re)connect over XML-RPC. Never raises — the outcome is in the
        returned status so the UI can render success or the exact failure."""
        self.proxy = None
        self.connected = False
        self.connect_error = None
        self.controller_version = None
        try:
            proxy = xmlrpc.client.ServerProxy(f"http://{self.ip}:{self.XMLRPC_PORT}")
            old = socket.getdefaulttimeout()
            socket.setdefaulttimeout(self.timeout)
            try:
                ip_reply = proxy.GetControllerIP()
            finally:
                socket.setdefaulttimeout(old)
            # Fairino replies [0, "<ip>"] on success.
            if not (isinstance(ip_reply, list) and ip_reply and ip_reply[0] == 0):
                self.connect_error = (
                    f"Reached {self.ip}:{self.XMLRPC_PORT} but GetControllerIP returned "
                    f"an unexpected reply: {ip_reply!r}"
                )
                return self.status()

            self.proxy = proxy
            self.connected = True
            try:
                ver = proxy.GetSoftwareVersion()
                if isinstance(ver, list) and ver and ver[0] == 0:
                    self.controller_version = " / ".join(str(v) for v in ver[1:])
            except Exception:  # noqa: BLE001 - version is best-effort, not fatal
                pass

            enable_error = self._call("RobotEnable", 1)
            if enable_error != 0:
                self.connect_error = f"Connected, but RobotEnable(1) returned error {enable_error}"
        except (OSError, xmlrpc.client.Fault, xmlrpc.client.ProtocolError) as exc:
            self.connect_error = (
                f"Could not reach Fairino controller at {self.ip}:{self.XMLRPC_PORT} "
                f"({type(exc).__name__}: {exc}). Check the ethernet link, robot power, and IP."
            )
        except Exception as exc:  # noqa: BLE001 - surface anything else to the UI
            self.connect_error = f"{type(exc).__name__}: {exc}"
        return self.status()

    def status(self) -> dict[str, Any]:
        return {
            "ip": self.ip,
            "connected": self.connected,
            "connect_error": self.connect_error,
            "controller_version": self.controller_version,
        }

    def set_free_drive(self, enabled: bool) -> dict[str, Any]:
        """Enter/exit drag (free-drive / manual) mode on the S922.

        Drag teaching only works in manual mode, so ordering matters:
          enable  -> Mode(1) [manual]  then DragTeachSwitch(1)
          disable -> DragTeachSwitch(0) then Mode(0) [auto]
        Every Fairino call returns an error code (0 = success).
        """
        if enabled:
            steps = [("Mode", 1), ("DragTeachSwitch", 1)]
        else:
            steps = [("DragTeachSwitch", 0), ("Mode", 0)]

        results: list[dict[str, Any]] = []
        for name, state in steps:
            command = f"{name}({state})"
            if self.proxy is None:
                results.append({"simulated": True, "command": command})
                continue
            try:
                error = self._call(name, state)
                results.append({"simulated": False, "command": command, "error": error})
            except Exception as exc:  # noqa: BLE001
                results.append({"simulated": False, "command": command, "error": f"{type(exc).__name__}: {exc}"})
        ok = all(r.get("error", 0) == 0 for r in results)
        return {"steps": results, "ok": ok, "command": f"free_drive({int(bool(enabled))})"}

    def get_current_position(self) -> dict[str, float]:
        """Get current TCP pose. Returns simulated values in sim mode."""
        if self.proxy is None:
            return {"x": 0.0, "y": 0.0, "z": 0.0, "rx": 0.0, "ry": 0.0, "rz": 0.0, "simulated": True}
        reply = self._call("GetActualTCPPose", 1)
        if isinstance(reply, list) and reply and reply[0] == 0:
            _, x, y, z, rx, ry, rz = reply
            return {"x": x, "y": y, "z": z, "rx": rx, "ry": ry, "rz": rz, "simulated": False}
        return {"x": 0.0, "y": 0.0, "z": 0.0, "rx": 0.0, "ry": 0.0, "rz": 0.0, "simulated": False, "error": reply}

    def move_linear(
        self,
        x: float,
        y: float,
        z: float,
        rx: float = 0.0,
        ry: float = 0.0,
        rz: float = 0.0,
        speed: float | None = None,
    ) -> dict[str, Any]:
        vel = self.default_speed if speed is None else speed
        pose = [float(x), float(y), float(z), float(rx), float(ry), float(rz)]
        command = f"MoveL({pose}, vel={vel})"
        if self.proxy is None:
            return {"simulated": True, "command": command}

        # Solve joints for the target pose, then issue the linear move. This
        # mirrors what the Fairino SDK's MoveL() does internally.
        ik = self._call("GetInverseKin", 0, pose, -1)
        if not (isinstance(ik, list) and ik and ik[0] == 0):
            return {"simulated": False, "command": command, "error": f"GetInverseKin failed: {ik!r}"}
        joints = list(ik[1:7])
        # FR5 v3.8.4 MoveL signature (13 positional args):
        #   joint_pos, desc_pos, tool, user, vel, acc, ovl, blendR, blendMode,
        #   exaxis_pos, search, offset_flag, offset_pos
        # MoveL blocks until the move completes -> use the long motion timeout.
        error = self._call(
            "MoveL",
            joints, pose, self.tool, self.user, vel,
            0.0,                                # acc
            100.0,                              # ovl
            -1.0,                               # blendR (blocking, move-to-position)
            0,                                  # blendMode
            [0.0, 0.0, 0.0, 0.0],               # exaxis_pos
            0,                                  # search
            0,                                  # offset_flag
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],     # offset_pos
            timeout=self.motion_timeout,
        )
        return {"simulated": False, "command": command, "error": error}

    def _robot_call(self, command: str, method: str, *args: Any, timeout: float | None = None) -> dict[str, Any]:
        """Invoke one XML-RPC method, wrapping the result as a log entry with the
        error code (0 = success), or the simulated echo when not connected."""
        if self.proxy is None:
            return {"simulated": True, "command": command}
        try:
            error = self._call(method, *args, timeout=timeout)
            return {"simulated": False, "command": command, "error": error}
        except Exception as exc:  # noqa: BLE001
            return {"simulated": False, "command": command, "error": f"{type(exc).__name__}: {exc}"}

    def prepare_for_motion(self) -> list[dict[str, Any]]:
        """Put the robot in a state where remote MoveL will actually run:
        enabled, drag teach off, automatic mode. After using Free Drive the arm
        is left in manual/drag mode, in which motion commands are ignored."""
        return [
            self._robot_call("RobotEnable(1)", "RobotEnable", 1),
            self._robot_call("DragTeachSwitch(0)", "DragTeachSwitch", 0),
            self._robot_call("Mode(0)", "Mode", 0),
        ]

    def arc_start(self) -> dict[str, Any]:
        """Ignite the welding arc using the configured welder profile."""
        cmd = f"ARCStart(ioType={self.arc_iotype}, arcNum={self.arc_num}, timeout={self.arc_timeout})"
        return self._robot_call(cmd, "ARCStart", self.arc_iotype, self.arc_num, self.arc_timeout, timeout=self.motion_timeout)

    def arc_end(self) -> dict[str, Any]:
        """Extinguish the welding arc."""
        cmd = f"ARCEnd(ioType={self.arc_iotype}, arcNum={self.arc_num}, timeout={self.arc_timeout})"
        return self._robot_call(cmd, "ARCEnd", self.arc_iotype, self.arc_num, self.arc_timeout, timeout=self.motion_timeout)

    def weave_set_para(self, frequency: float, amplitude: float) -> dict[str, Any]:
        """Set weave parameters. amplitude -> range (mm), frequency -> Hz."""
        args = (
            self.weave_num, self.weave_type, float(frequency), 0, float(amplitude),
            0.0, 0.0, 0, 0, 0, 0, 0, 0, 0,  # left/right range, stay times, circle ratio, stationary, yaw, rot
        )
        cmd = f"WeaveSetPara(num={self.weave_num}, type={self.weave_type}, freq={frequency}, range={amplitude})"
        return self._robot_call(cmd, "WeaveSetPara", *args)

    def weave_start(self) -> dict[str, Any]:
        return self._robot_call(f"WeaveStart({self.weave_num})", "WeaveStart", self.weave_num)

    def weave_end(self) -> dict[str, Any]:
        return self._robot_call(f"WeaveEnd({self.weave_num})", "WeaveEnd", self.weave_num)

    def go_home(self, speed: float | None = None) -> dict[str, Any]:
        """Joint-move the arm to its home configuration (default all joints 0)."""
        vel = self.default_speed if speed is None else speed
        joints = self.home_joints
        command = f"MoveJ(home={joints}, vel={vel})"
        if self.proxy is None:
            return {"simulated": True, "command": command}
        try:
            # MoveJ needs the matching Cartesian pose; derive it from the joints.
            fk = self._call("GetForwardKin", joints)
            desc = list(fk[1:7]) if isinstance(fk, list) and fk and fk[0] == 0 else [0.0] * 6
            # FR5 v3.8.4 MoveJ (11 args): joint_pos, desc_pos, tool, user, vel,
            #   acc, ovl, exaxis_pos, blendT, offset_flag, offset_pos
            error = self._call(
                "MoveJ",
                joints, desc, self.tool, self.user, vel,
                0.0, 100.0, [0.0, 0.0, 0.0, 0.0], -1.0, 0,
                [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                timeout=self.motion_timeout,
            )
            return {"simulated": False, "command": command, "error": error}
        except Exception as exc:  # noqa: BLE001
            return {"simulated": False, "command": command, "error": f"{type(exc).__name__}: {exc}"}

    def send_command(self, command: str) -> dict[str, Any]:
        """Generic logged step (kept for any non-motion annotations)."""
        return {"simulated": self.proxy is None, "command": command}
