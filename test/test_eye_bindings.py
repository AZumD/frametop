#!/usr/bin/env python3
"""Validate SteamVR eye-gaze action/binding manifests for ft-screens."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCREENS = ROOT / "screens"


def load(name: str) -> dict:
    path = SCREENS / name
    assert path.is_file(), f"missing {path}"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def test_actions_manifest() -> None:
    d = load("actions.json")
    actions = {a["name"]: a for a in d["actions"]}
    assert "/actions/frametop/in/EyeGaze" in actions
    assert actions["/actions/frametop/in/EyeGaze"]["type"] == "eyetracking"
    sets = {s["name"] for s in d["action_sets"]}
    assert "/actions/frametop" in sets
    by_type = {b["controller_type"]: b["binding_url"] for b in d["default_bindings"]}
    assert by_type["frame_hmd"] == "bindings_frame_hmd.json"
    assert by_type["hmd"] == "bindings_hmd.json"
    for url in by_type.values():
        assert (SCREENS / url).is_file(), f"default binding missing: {url}"


def test_binding_eyetracking_array(name: str, controller_type: str) -> None:
    d = load(name)
    assert d["controller_type"] == controller_type
    block = d["bindings"]["/actions/frametop"]
    # SteamVR parses a top-level "eyetracking" array (not sources/mode).
    assert "eyetracking" in block, f"{name}: need bindings./actions/frametop.eyetracking array"
    assert isinstance(block["eyetracking"], list) and block["eyetracking"], f"{name}: empty eyetracking"
    entry = block["eyetracking"][0]
    assert entry.get("path") == "/user/head/eyetracking", f"{name}: path must be /user/head/eyetracking (driver component /eyetracking)"
    assert entry.get("output") == "/actions/frametop/in/EyeGaze"
    # Old wrong shape must not creep back in.
    for src in block.get("sources", []):
        assert src.get("mode") != "eyetracking", f"{name}: eyetracking must not use sources/mode"


def main() -> int:
    test_actions_manifest()
    test_binding_eyetracking_array("bindings_frame_hmd.json", "frame_hmd")
    test_binding_eyetracking_array("bindings_hmd.json", "hmd")
    print("ok: eye gaze action/binding manifests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
