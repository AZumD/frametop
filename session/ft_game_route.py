#!/usr/bin/env python3
"""Steam→Tovakai launch-route helpers (classification, chooser FSM, markers).

Steam-facing UI lives in steam-ui-patches/game-route (steam-frame-nix shape).
This module is dependency-light and unit-tested without Steam.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from ft_game_run import (  # noqa: F401 — re-export for callers
    already_wrapped,
    host_runtime_dir,
    marker_path,
    parse_app_id_from_game_id,
    wrap_launch_options,
)

Route = Literal["steamvr", "tovakai", "cancel"]
Class = Literal["flat", "vr_only", "hybrid", "unknown"]
ChooserState = Literal["idle", "pending", "chosen", "launching", "done"]


@dataclass
class LaunchContext:
    game_action_id: int
    game_id: str
    app_id: int
    action: str
    launch_source: int
    name: str = ""
    classification: Class = "unknown"
    original_launch_options: str = ""
    vr_launch_selected: bool = False


@dataclass
class ChooserFSM:
    """One-shot cancel → choose → relaunch state machine."""

    state: ChooserState = "idle"
    bypass_tokens: set[str] = field(default_factory=set)
    pending: LaunchContext | None = None
    choice: Route | None = None
    desktop_mode_fired: bool = False
    log: list[dict[str, Any]] = field(default_factory=list)

    def _push(self, event: str, **kw: Any) -> None:
        row = {"event": event, **kw}
        self.log.append(row)
        if len(self.log) > 200:
            self.log.pop(0)

    def should_bypass(self, game_id: str, app_id: int) -> bool:
        return game_id in self.bypass_tokens or str(app_id) in self.bypass_tokens

    def consume_bypass(self, game_id: str, app_id: int) -> None:
        self.bypass_tokens.discard(game_id)
        self.bypass_tokens.discard(str(app_id))
        self._push("bypass_consumed", game_id=game_id, app_id=app_id)

    def arm_bypass(self, game_id: str, app_id: int) -> None:
        self.bypass_tokens.add(str(game_id))
        self.bypass_tokens.add(str(app_id))
        self._push("bypass_armed", game_id=str(game_id), app_id=app_id)

    def begin_intercept(self, ctx: LaunchContext) -> Literal["cancel", "ignore"]:
        # Bypass must win even while state==launching (our own RunGame).
        if self.should_bypass(ctx.game_id, ctx.app_id):
            self.consume_bypass(ctx.game_id, ctx.app_id)
            self.on_relaunch_started()
            return "ignore"
        if self.state not in ("idle", "done"):
            self._push("busy_ignore", state=self.state, app_id=ctx.app_id)
            return "ignore"
        if ctx.action != "LaunchApp":
            return "ignore"
        if ctx.classification == "vr_only" or ctx.vr_launch_selected:
            self._push("skip_vr", app_id=ctx.app_id, classification=ctx.classification)
            return "ignore"
        self.pending = ctx
        self.choice = None
        self.state = "pending"
        self.desktop_mode_fired = False
        self._push("pending", app_id=ctx.app_id, name=ctx.name)
        return "cancel"

    def choose(self, route: Route) -> bool:
        if self.state != "pending" or not self.pending:
            self._push("choose_invalid", state=self.state, route=route)
            return False
        self.choice = route
        self.state = "chosen"
        self._push("chosen", route=route, app_id=self.pending.app_id)
        if route == "cancel":
            self.state = "done"
            self.pending = None
            return True
        self.state = "launching"
        self.arm_bypass(self.pending.game_id, self.pending.app_id)
        return True

    def on_relaunch_started(self) -> None:
        if self.state == "launching":
            self._push("relaunch_started", choice=self.choice)
            self.state = "done"

    def maybe_fire_desktop_mode(self) -> bool:
        """True once when Tovakai route should switch controller/desktop mode."""
        if self.choice != "tovakai":
            return False
        if self.desktop_mode_fired:
            return False
        if self.state not in ("launching", "done"):
            return False
        self.desktop_mode_fired = True
        self._push("desktop_mode_fire")
        return True

    def reset(self) -> None:
        self.state = "idle"
        self.pending = None
        self.choice = None
        self.desktop_mode_fired = False
        self._push("reset")


def classify_launch(
    *,
    launch_options: list[dict] | None = None,
    details: dict | None = None,
    selected_index: int | None = None,
) -> tuple[Class, bool]:
    """Return (classification, vr_launch_selected).

    Conservative: any config with bIsVRLaunchOption truthy → hybrid if mixed,
    vr_only if all VR; explicit selected VR config → vr_launch_selected True.
    """
    opts = launch_options or []
    details = details or {}
    # Prefer launch-option flags (live Frame AppDetails lacked vr_only fields).
    flags = []
    for o in opts:
        flags.append(bool(o.get("bIsVRLaunchOption") or o.get("vr_only")))
    vr_selected = False
    if selected_index is not None and 0 <= selected_index < len(opts):
        vr_selected = bool(opts[selected_index].get("bIsVRLaunchOption"))
    # details fallbacks if present
    if details.get("vr_only") or details.get("bVROnly"):
        return "vr_only", True
    if not flags:
        if details.get("vr_supported") or details.get("bVRSupported"):
            return "hybrid", vr_selected
        return "flat", False
    if all(flags):
        return "vr_only", True
    if any(flags):
        return "hybrid", vr_selected
    return "flat", False


def write_marker(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def read_marker(path: str) -> dict | None:
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def clear_marker(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def make_marker_payload(
    *,
    app_id: int,
    original: str,
    installed: str,
    name: str = "",
) -> dict:
    return {
        "schema": 1,
        "appId": int(app_id),
        "original": original if original is not None else "",
        "installed": installed,
        "name": name,
        "ts": time.time(),
        "pending": True,
    }
