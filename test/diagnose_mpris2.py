#!/usr/bin/env python3
"""Diagnose nested-session MPRIS vs browser D-Bus (Frame)."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


def read_environ(pid: int) -> dict[str, str]:
    raw = Path(f"/proc/{pid}/environ").read_bytes()
    out = {}
    for part in raw.split(b"\0"):
        if b"=" not in part:
            continue
        k, v = part.split(b"=", 1)
        out[k.decode(errors="replace")] = v.decode(errors="replace")
    return out


def cmdline(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
    except OSError:
        return ""


def all_pids() -> list[int]:
    out = []
    for p in Path("/proc").iterdir():
        if p.name.isdigit():
            out.append(int(p.name))
    return out


def busctl_list(bus: str) -> str:
    env = os.environ.copy()
    env["DBUS_SESSION_BUS_ADDRESS"] = bus
    try:
        p = subprocess.run(
            ["busctl", "--user", "list"],
            capture_output=True,
            text=True,
            timeout=5,
            env=env,
        )
        return (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return f"ERR {e}"


def main() -> int:
    mpris_pids = [p for p in all_pids() if "ft-mpris.py" in cmdline(p) and "python" in cmdline(p)]
    print("mpris_python_pids", mpris_pids)
    if not mpris_pids:
        print("NO_MPRIS")
        return 1
    pid = mpris_pids[0]
    env = read_environ(pid)
    bus = env.get("DBUS_SESSION_BUS_ADDRESS", "")
    print("mpris_pid", pid)
    print("mpris_bus", bus)
    names = busctl_list(bus)
    mpris = [ln for ln in names.splitlines() if "org.mpris.MediaPlayer2" in ln]
    print("mpris_names", len(mpris))
    for ln in mpris[:30]:
        print(" ", ln.strip())
    interesting = [
        ln
        for ln in names.splitlines()
        if any(s in ln.lower() for s in ("chrom", "firefox", "brave", "plasma", "media", "vlc", "mpv"))
    ]
    print("interesting_names", len(interesting))
    for ln in interesting[:40]:
        print(" ", ln.strip())

    browsers = []
    for p in all_pids():
        cmd = cmdline(p).lower()
        if any(s in cmd for s in ("chromium", "chrome", "firefox", "brave")) and "zygote" not in cmd:
            if "type=" in cmd and "type=zygote" in cmd:
                continue
            browsers.append(p)
    # Also include main browser procs more loosely
    for p in all_pids():
        cmd = cmdline(p)
        low = cmd.lower()
        if "steamwebhelper" in low:
            continue
        if any(s in low for s in ("chromium", "/usr/bin/chrome", "firefox", "brave-browser")):
            browsers.append(p)
    browsers = sorted(set(browsers))
    print("browser_pids", browsers[:20])
    for p in browsers[:12]:
        e = read_environ(p)
        pbus = e.get("DBUS_SESSION_BUS_ADDRESS", "")
        print(f" pid={p} same={pbus == bus}")
        print(f"  bus={pbus}")
        print(f"  cmd={cmdline(p)[:140]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
