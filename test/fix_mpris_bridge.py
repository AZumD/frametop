#!/usr/bin/env python3
"""Kill stale ft-mpris processes and ensure one live bridge on the nested bus."""
from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path


def cmdline(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
    except OSError:
        return ""


def environ(pid: int) -> dict[str, str]:
    out = {}
    try:
        raw = Path(f"/proc/{pid}/environ").read_bytes()
    except OSError:
        return out
    for part in raw.split(b"\0"):
        if b"=" in part:
            k, v = part.split(b"=", 1)
            out[k.decode(errors="replace")] = v.decode(errors="replace")
    return out


def main() -> int:
    pys = []
    for p in Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        c = cmdline(int(p.name))
        if c.startswith("python3 ") and "ft-mpris.py" in c:
            pys.append(int(p.name))
    print("found", pys)
    # Prefer a process whose bus is a /tmp/dbus-* private session (nested).
    nested = []
    for pid in pys:
        bus = environ(pid).get("DBUS_SESSION_BUS_ADDRESS", "")
        print(f" pid={pid} bus={bus}")
        if "/tmp/dbus-" in bus:
            nested.append(pid)
    # Kill everyone first so @frametop_mpris is free.
    for pid in pys:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    time.sleep(0.5)
    for pid in pys:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    time.sleep(0.2)

    # Find nested dbus from plasmashell / startplasma env
    bus = ""
    for p in Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        c = cmdline(int(p.name))
        if "plasmashell" in c or "startplasma-wayland" in c:
            bus = environ(int(p.name)).get("DBUS_SESSION_BUS_ADDRESS", "")
            if "/tmp/dbus-" in bus:
                break
    if not bus:
        print("no nested bus found")
        return 1
    script = "/home/steamos/dev/frametop/session/ft-mpris.py"
    env = os.environ.copy()
    env["DBUS_SESSION_BUS_ADDRESS"] = bus
    log = open("/tmp/frametop-mpris.log", "ab", buffering=0)
    proc = subprocess.Popen(
        ["python3", script],
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    print(f"started {proc.pid} on {bus}")
    time.sleep(0.6)
    import socket

    cli = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    cli.settimeout(1.5)
    try:
        cli.bind("\0")
        cli.sendto(b"state", "\0frametop_mpris")
        print("state", cli.recvfrom(512)[0])
    except Exception as e:
        print("fail", e)
        return 2
    finally:
        cli.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
