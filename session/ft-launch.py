#!/usr/bin/env python3
"""Frametop launch bridge: nested Plasma session → @frametop_launch for Launcher instruments.

Runs inside the Frametop nested Plasma session (same private D-Bus as apps).
ft-screens (in distrobox) sends datagrams to the abstract socket @frametop_launch:

  desktop <desktop-id>          -> launch Application .desktop entry
  action <semantic-action>      -> ft-layout action NAME (profile.slot.N, …)
  command <json-argv-array>     -> detached exec of argv (no shell)
  shell <text>                  -> /bin/sh -c <text> (explicit expert path)
  ping                          -> ok pong

Replies: ok | error <message>

This process starts *before* Plasma, so its own environ still has the outer
ft-screens WAYLAND_DISPLAY. Each activation reloads plasmashell.env (written by
ft-shell-watch) so apps attach to nested KWin on the existing Frametop displays —
not as extra host-compositor overlays.
"""
from __future__ import annotations

import json
import os
import select
import socket
import subprocess
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
LAYOUT_DIR = os.path.join(HERE, "..", "layout")
sys.path.insert(0, LAYOUT_DIR)
import ft_desktop  # noqa: E402

SOCK_NAME = "\0frametop_launch"
FT_LAYOUT = os.path.join(LAYOUT_DIR, "ft-layout")


def log(*args, **kwargs):
    kwargs.setdefault("flush", True)
    print(*args, **kwargs, file=sys.stderr)


def handle(line: str) -> str:
    line = (line or "").strip()
    if not line:
        return "error empty"
    if line == "ping":
        return "ok pong"
    if line.startswith("desktop "):
        desktop_id = line[8:].strip()
        if not desktop_id:
            return "error desktop wants id"
        try:
            ft_desktop.launch_desktop_id(desktop_id)  # loads plasmashell.env
            return "ok"
        except Exception as e:
            log("desktop launch failed:", e)
            return f"error {e}"
    if line.startswith("action "):
        name = line[7:].strip()
        if not name:
            return "error action wants name"
        try:
            env = ft_desktop.nested_launch_env()
            r = subprocess.run(
                [FT_LAYOUT, "action", name],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                env=env,
                timeout=30,
                check=False,
            )
            if r.returncode != 0:
                err = (r.stderr or b"").decode(errors="replace").strip() or f"exit {r.returncode}"
                return f"error {err}"
            return "ok"
        except Exception as e:
            log("action failed:", e)
            return f"error {e}"
    if line.startswith("command "):
        raw = line[8:].strip()
        try:
            argv = json.loads(raw)
        except json.JSONDecodeError as e:
            return f"error bad command json: {e}"
        if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
            return "error command wants a JSON string array"
        try:
            ft_desktop.launch_command_argv(argv)
            return "ok"
        except Exception as e:
            log("command launch failed:", e)
            return f"error {e}"
    if line.startswith("shell "):
        script = line[6:]  # preserve internal spaces; only strip is the prefix
        if not script.strip():
            return "error empty shell"
        try:
            ft_desktop.launch_command_shell(script)
            return "ok"
        except Exception as e:
            log("shell launch failed:", e)
            return f"error {e}"
    return "error unknown command (want desktop|action|command|shell|ping)"


def main():
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        sock.bind(SOCK_NAME)
    except OSError as e:
        log(f"cannot bind @frametop_launch: {e}")
        return 1
    sock.setblocking(False)
    log("ft-launch listening on @frametop_launch "
        f"(launches use {ft_desktop.plasmashell_env_path()})")
    while True:
        try:
            r, _w, _x = select.select([sock], [], [], 30.0)
            if not r:
                continue
            data, addr = sock.recvfrom(65535)
        except InterruptedError:
            continue
        except OSError as e:
            log("recv error:", e)
            continue
        try:
            line = data.decode("utf-8", errors="replace")
            reply = handle(line)
        except Exception:
            log("handler crash:\n" + traceback.format_exc())
            reply = "error internal"
        try:
            sock.sendto(reply.encode("utf-8", errors="replace"), addr)
        except OSError as e:
            log("send error:", e)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
