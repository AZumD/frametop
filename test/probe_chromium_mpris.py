#!/usr/bin/env python3
"""Probe Chromium MPRIS properties on the nested Frametop bus."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "session"))


def env(pid: int) -> dict[str, str]:
    d = {}
    for p in Path(f"/proc/{pid}/environ").read_bytes().split(b"\0"):
        if b"=" in p:
            k, v = p.split(b"=", 1)
            d[k.decode(errors="replace")] = v.decode(errors="replace")
    return d


def cmd(pid: int) -> str:
    return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")


def find_mpris_bus() -> str:
    for p in Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        c = cmd(int(p.name))
        if c.startswith("python3 ") and "ft-mpris.py" in c:
            return env(int(p.name)).get("DBUS_SESSION_BUS_ADDRESS", "")
    return ""


def main() -> int:
    bus = find_mpris_bus()
    print("bus", bus)
    os.environ["DBUS_SESSION_BUS_ADDRESS"] = bus
    # Import bridge after setting bus so Gio uses it
    import importlib.util

    spec = importlib.util.spec_from_file_location("ft_mpris", ROOT / "session" / "ft-mpris.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)

    backend = mod.open_backend()
    players = backend.list_players()
    print("list_players", players)
    for name in players:
        info = backend.read_player(name)
        print("read", name, "->", info)
    print("pick", mod.pick_player(backend))
    print("format", mod.format_state(mod.pick_player(backend)))

    # Raw busctl dump for chromium
    for name in players:
        if "chrom" not in name.lower():
            continue
        for prop in ("PlaybackStatus", "CanPlay", "CanPause", "CanGoNext", "CanGoPrevious", "Metadata"):
            p = subprocess.run(
                ["busctl", "--user", "get-property", name, "/org/mpris/MediaPlayer2",
                 "org.mpris.MediaPlayer2.Player", prop],
                capture_output=True, text=True, timeout=5,
            )
            print(f"busctl {prop}: rc={p.returncode} out={(p.stdout or p.stderr).strip()[:300]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
