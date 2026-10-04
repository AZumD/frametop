#!/usr/bin/env python3
"""Push visibility/scales and print instrument state (live Frame check)."""
import json
import os
import socket
import sys

LAYOUT_PATH = os.path.expanduser("~/.config/frametop-layout.json")
SCREENS = "\0ft_screens"


def ask(cmd, timeout=5.0):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    sock.bind("")
    sock.settimeout(timeout)
    try:
        sock.sendto(cmd.encode(), SCREENS)
        return sock.recv(8192).decode().strip()
    finally:
        sock.close()


def main():
    with open(LAYOUT_PATH) as f:
        layout = json.load(f)
    v = layout.get("visibility") or {}
    mode = v.get("mode", "always")
    cmds = [
        f"visibility {mode}",
        f"wrist {float(v.get('wrist_angle', 60)):.1f}",
        f"gesture {v.get('gesture_hand', 'left')} {float(v.get('gesture_angle', 20)):.1f}",
        f"controllers {v.get('controllers', 'outside_games')}",
        f"ingames {v.get('in_games', 'hide')}",
    ]
    for i, s in enumerate(layout.get("screens") or []):
        scale = float(s.get("scale") or 1)
        cmds.append(f"scale {i + 1} {scale:g}")
    cmds += ["instrument list", "instrument get clock", "head"]
    for cmd in cmds:
        try:
            print(f"{cmd} -> {ask(cmd)}")
        except Exception as e:
            print(f"{cmd} ERR {e}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
