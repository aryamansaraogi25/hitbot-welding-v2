#!/usr/bin/env python3
"""Standalone Fairino / Hitbot S922 connection diagnostic.

Run this ON THE MACHINE physically networked to the robot:

    ROBOT_IP=192.168.58.2 python3 scripts/diagnose_robot.py

It checks, in order: TCP reachability of the XML-RPC command port, the RPC
handshake, robot enable, and a full free-drive (manual + drag) toggle --
printing the raw error code from every call so we can see exactly where it fails.

The app talks XML-RPC on port 20003 (the CNDE state port 20005 used by newer
SDK builds is not required and not served by FR5 v3.8.x firmware).

KEEP THE E-STOP IN REACH: this will attempt to put the arm into drag mode.
"""
import os
import socket
import sys
import time
import xmlrpc.client

IP = os.getenv("ROBOT_IP", "192.168.58.2")
PORT = 20003  # Fairino XML-RPC command port


def check_port(ip: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError as e:
        print(f"    -> {e}")
        return False


def show(label: str, reply) -> int:
    """Print a call reply; Fairino returns int error or [error, ...]."""
    err = reply[0] if isinstance(reply, list) else reply
    print(f"    {label:<28} -> {reply}  ({'ok' if err == 0 else 'ERROR'})")
    return err


def main() -> int:
    print(f"== Fairino S922 diagnostic ==\nController IP: {IP}\n")

    print(f"[1] TCP reachability of XML-RPC port {PORT}")
    if not check_port(IP, PORT):
        print(f"    port {PORT}: UNREACHABLE\n")
        print("FAIL: controller not reachable. Fix networking first:")
        print("  - is the robot powered on and booted?")
        print(f"  - can this machine ping {IP}?  (ping {IP})")
        print("  - is the ethernet cable in and this PC on the robot's subnet")
        print("    (e.g. `sudo ip addr add 192.168.58.1/24 dev <eth>`)?")
        return 1
    print(f"    port {PORT}: OPEN")

    print("\n[2] RPC handshake")
    socket.setdefaulttimeout(5)
    robot = xmlrpc.client.ServerProxy(f"http://{IP}:{PORT}")
    ip_reply = robot.GetControllerIP()
    if show("GetControllerIP()", ip_reply) != 0:
        print("\nFAIL: port open but controller did not answer GetControllerIP.")
        return 1
    show("GetSoftwareVersion()", robot.GetSoftwareVersion())

    print("\n[3] Enable robot")
    show("RobotEnable(1)", robot.RobotEnable(1))

    print("\n[4] Read current pose")
    show("GetActualTCPPose(1)", robot.GetActualTCPPose(1))

    print("\n[5] Enter free-drive (manual mode + drag teach)")
    err_mode = show("Mode(1) [manual]", robot.Mode(1))
    err_drag = show("DragTeachSwitch(1)", robot.DragTeachSwitch(1))
    if err_mode == 0 and err_drag == 0:
        print("\n>>> The arm should now be limp/compliant. Try moving it by hand. <<<")
        print("    Holding for 8 seconds, then exiting drag mode...")
        time.sleep(8)
    else:
        print("\nDrag mode was NOT accepted -- see the error codes above.")

    print("\n[6] Exit free-drive")
    show("DragTeachSwitch(0)", robot.DragTeachSwitch(0))
    show("Mode(0) [auto]", robot.Mode(0))

    print("\n== done ==")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
