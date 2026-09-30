#!/usr/bin/env python3
"""Hot-reload session/ft-mpris.py inside the nested dbus-run-session without a full desktop restart."""
from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path


def cmdline(pid: int) -> str:
    return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")


def environ(pid: int) -> dict[str, str]:
    out = {}
    for part in Path(f"/proc/{pid}/environ").read_bytes().split(b"\0"):
        if b"=" in part:
            k, v = part.split(b"=", 1)
            out[k.decode(errors="replace")] = v.decode(errors="replace")
    return out


def main() -> int:
    script = Path.home() / "dev/frametop/session/ft-mpris.py"
    if not script.is_file():
        script = Path("/home/steamos/frametop/session/ft-mpris.py")
    old = None
    for p in Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        c = cmdline(int(p.name))
        if c.startswith("python3 ") and "ft-mpris.py" in c:
            old = int(p.name)
            break
    if old is None:
        print("no running ft-mpris")
        return 1
    env = environ(old)
    bus = env.get("DBUS_SESSION_BUS_ADDRESS", "")
    print(f"restarting pid={old} bus={bus}")
    os.kill(old, signal.SIGTERM)
    time.sleep(0.4)
    log = open("/tmp/frametop-mpris.log", "ab", buffering=0)
    proc = subprocess.Popen(
        ["python3", str(script)],
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    print(f"started pid={proc.pid}")
    time.sleep(0.5)
    # Quick socket check
    import socket

    cli = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    cli.settimeout(1.5)
    try:
        cli.bind("\0")
        cli.sendto(b"state", "\0frametop_mpris")
        print("state", cli.recvfrom(512)[0])
    except Exception as e:
        print("state fail", e)
        return 2
    finally:
        cli.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
