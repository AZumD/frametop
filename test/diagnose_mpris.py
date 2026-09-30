#!/usr/bin/env python3
"""Diagnose MPRIS visibility for the Frametop Media bridge.

Run on the Frame:
  python3 test/diagnose_mpris.py
"""
from __future__ import annotations

import os
import subprocess
import sys
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


def pids_matching(substr: str) -> list[int]:
    out = []
    for p in Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        try:
            cmd = (p / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            continue
        if substr in cmd:
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
        return p.stdout + p.stderr
    except Exception as e:
        return f"busctl failed: {e}"


def main() -> int:
    mpris = pids_matching("ft-mpris.py")
    print(f"ft-mpris pids: {mpris}")
    if not mpris:
        print("NO_MPRIS_RUNNING")
        return 1
    menv = read_environ(mpris[0])
    bus = menv.get("DBUS_SESSION_BUS_ADDRESS", "")
    print(f"mpris bus: {bus}")
    names = busctl_list(bus)
    mpris_names = [ln for ln in names.splitlines() if "org.mpris.MediaPlayer2" in ln]
    print(f"mpris names ({len(mpris_names)}):")
    for ln in mpris_names[:40]:
        print(" ", ln)
    if not mpris_names:
        print(" (none on nested bus)")

    for label, needle in (
        ("chromium", "chrom"),
        ("firefox", "firefox"),
        ("brave", "brave"),
    ):
        ps = pids_matching(needle)
        print(f"{label} pids: {ps[:8]}")
        for pid in ps[:3]:
            try:
                env = read_environ(pid)
            except OSError:
                continue
            pbus = env.get("DBUS_SESSION_BUS_ADDRESS", "")
            same = pbus == bus
            print(f"  pid {pid}: same_bus={same} bus={pbus[:80]}")
            cmd = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")[:120]
            print(f"    cmd={cmd}")

    # Also ask the bridge socket directly
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "session"))
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "ft_mpris", Path(__file__).resolve().parents[1] / "session" / "ft-mpris.py"
        )
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader
        # Don't exec serve — just probe via socket
    except Exception:
        pass
    import socket

    cli = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    cli.settimeout(1.0)
    try:
        cli.bind("\0")
        cli.sendto(b"state", "\0frametop_mpris")
        print("bridge state:", cli.recvfrom(512)[0])
    except Exception as e:
        print("bridge fail:", e)
    finally:
        cli.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
