#!/usr/bin/env python3
"""ft-game-run helpers: nested Plasma env load + launch-option wrap/restore.

Used by session/ft-game-run (wrapper) and Stage 3 routing probes.
Conceptual name: tovakai-game-run. Process/script name stays ≤15 chars.
"""
from __future__ import annotations

import os
import re
import time
from typing import Iterable

# Keys copied from plasmashell.env onto Steam's launch environment.
# Leave Steam/Proton/Steam Runtime variables alone. Skip DBUS by default so
# Steam IPC / overlay keep the host session bus; override only display/session.
DISPLAY_OVERRIDE_KEYS = (
    "DISPLAY",
    "WAYLAND_DISPLAY",
    "XDG_RUNTIME_DIR",
    "XDG_SESSION_TYPE",
    "XAUTHORITY",
)

MARKER_DIR_NAME = "frametop-game-route"
MARKER_NAME = "launch-options-backup.json"

_FIELD_SAFE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def host_runtime_dir(env: dict | None = None) -> str:
    env = env or os.environ
    rt = env.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    # If already inside nested frametop runtime, peel to host.
    if rt.rstrip("/").endswith("/frametop"):
        return os.path.dirname(rt.rstrip("/"))
    return rt


def plasmashell_env_path(env: dict | None = None) -> str:
    """Always the nested snapshot: $HOST_RUNTIME/frametop/plasmashell.env."""
    return os.path.join(host_runtime_dir(env), "frametop", "plasmashell.env")


def load_nul_env_file(path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    with open(path, "rb") as f:
        blob = f.read()
    for entry in blob.split(b"\0"):
        if not entry or b"=" not in entry:
            continue
        k, _, v = entry.partition(b"=")
        try:
            key = k.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if not _FIELD_SAFE.match(key):
            continue
        out[key] = v.decode("utf-8", errors="surrogateescape")
    return out


def nested_display_overrides(env_file: str | None = None, env: dict | None = None) -> dict[str, str]:
    """Read plasmashell.env and return only display/session overrides."""
    path = env_file or plasmashell_env_path(env)
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"nested Plasma not ready (no {path}) — start Frametop desktop first")
    loaded = load_nul_env_file(path)
    out: dict[str, str] = {}
    for k in DISPLAY_OVERRIDE_KEYS:
        if k in loaded and loaded[k] != "":
            out[k] = loaded[k]
    wl = out.get("WAYLAND_DISPLAY", "")
    rt = out.get("XDG_RUNTIME_DIR", "")
    if wl.startswith("/") or (wl and not wl.startswith("wayland-")):
        raise RuntimeError(f"bad WAYLAND_DISPLAY in plasmashell.env: {wl!r}")
    if rt and "frametop" not in rt.replace("\\", "/"):
        raise RuntimeError(f"bad XDG_RUNTIME_DIR in plasmashell.env: {rt!r}")
    if "DISPLAY" not in out:
        raise RuntimeError(f"plasmashell.env missing DISPLAY: {path}")
    return out


def apply_overrides(base: dict[str, str], overrides: dict[str, str]) -> dict[str, str]:
    """Copy base env and apply overrides (does not mutate base)."""
    out = dict(base)
    out.update(overrides)
    return out


def marker_path(env: dict | None = None) -> str:
    rt = host_runtime_dir(env)
    return os.path.join(rt, MARKER_DIR_NAME, MARKER_NAME)


def wrap_launch_options(existing: str, wrapper_path: str) -> str:
    """Insert wrapper around %command%, preserving user options.

    Examples:
      "" + wrap -> '/path/ft-game-run %command%'
      'mangohud %command%' -> '/path/ft-game-run mangohud %command%'
      'FOO=1 %command% --bar' -> '/path/ft-game-run FOO=1 %command% --bar'
      'onlyflags' (no %command%) -> '/path/ft-game-run %command% onlyflags'
    """
    existing = (existing or "").strip()
    wrapper_path = os.path.abspath(wrapper_path)
    if " " in wrapper_path or any(c in wrapper_path for c in "\"'`$"):
        # Quote for Steam's launch-option shell-ish parser.
        wrapped = "'" + wrapper_path.replace("'", "'\\''") + "'"
    else:
        wrapped = wrapper_path
    if "%command%" in existing:
        # Put wrapper first so it exec's the rest of Steam's expanded command.
        return f"{wrapped} {existing}"
    if not existing:
        return f"{wrapped} %command%"
    return f"{wrapped} %command% {existing}"


def already_wrapped(options: str, wrapper_path: str) -> bool:
    options = options or ""
    abs_w = os.path.abspath(wrapper_path)
    base = os.path.basename(wrapper_path)
    return abs_w in options or f"/{base} " in options or options.startswith(base + " ")


def parse_app_id_from_game_id(game_id) -> int:
    """gameId from RegisterForGameActionStart → Steam app id (low 32 bits)."""
    try:
        return int(int(game_id) & 0xFFFFFFFF)
    except (TypeError, ValueError):
        s = str(game_id)
        if s.isdigit():
            return int(s) & 0xFFFFFFFF
        raise


def summarize_env(env: dict[str, str], keys: Iterable[str] = DISPLAY_OVERRIDE_KEYS) -> str:
    parts = []
    for k in keys:
        if k in env:
            parts.append(f"{k}={env[k]}")
    return " ".join(parts)
