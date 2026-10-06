#!/usr/bin/env python3
"""Probe launcher remove + app availability on the Frame."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.expanduser("~/dev/frametop/layout"))
sys.path.insert(0, os.path.expanduser("~/dev/frametop/display-settings"))

import ft_desktop  # noqa: E402
import ft_layout  # noqa: E402


def main():
    print("applications_dirs:")
    for d in ft_desktop.applications_dirs():
        print(" ", d, "exists" if os.path.isdir(d) else "MISSING")

    apps = ft_desktop.list_applications()
    print(f"list_applications: {len(apps)}")
    for a in apps[:8]:
        found = ft_desktop.find_desktop_by_id(a["id"])
        avail = ft_desktop.application_available(a["id"])
        print(f"  id={a['id']!r} name={a['name']!r} found={bool(found)} avail={avail} path={found}")

    layout = ft_layout.load_layout()
    launchers = [i for i in ft_layout.instruments_from_layout(layout) if i.get("type") == "launcher"]
    print(f"layout launchers: {len(launchers)}")
    for inst in launchers:
        did = inst.get("desktop_id") or ""
        print(
            f"  id={inst['id']} desktop_id={did!r} "
            f"avail={ft_desktop.application_available(did)} "
            f"in_list={any(a['id'] == did for a in apps)}"
        )

    # Simulate Backend card appAvailable
    for inst in launchers:
        card_id = inst["id"]
        # mirror _instrument_card check
        available = True
        if (inst.get("action_kind") or "application") == "application" and inst.get("desktop_id"):
            available = ft_desktop.application_available(inst["desktop_id"])
        print(f"  card {card_id} appAvailable={available}")

    # Dry-run remove of first launcher if present
    if launchers:
        iid = launchers[0]["id"]
        print(f"remove dry-run id={iid} is_launcher={ft_layout.is_launcher_instrument_id(iid)}")
        before = {i["id"] for i in ft_layout.instruments_from_layout(layout)}
        out = ft_layout.remove_instrument(layout, iid)
        after = {i["id"] for i in ft_layout.instruments_from_layout(out)}
        print(f"  before={sorted(before)} after={sorted(after)} removed={iid not in after}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
