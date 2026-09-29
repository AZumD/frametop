#!/usr/bin/env python3
"""Emergency: restore screen 1 (or argv[1]) to full opacity and attention off."""
import json
import os
import socket
import sys

n = int(sys.argv[1]) if len(sys.argv) > 1 else 1
path = os.path.expanduser("~/.config/frametop-layout.json")
with open(path, encoding="utf-8") as f:
    data = json.load(f)
screens = data.setdefault("screens", [])
while len(screens) < n:
    screens.append({})
entry = dict(screens[n - 1])
entry["opacity"] = 1.0
entry["active_opacity"] = 1.0
entry["idle_opacity"] = 1.0
entry.pop("attention", None)
screens[n - 1] = entry
data["screens"] = screens
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
print(f"wrote {path} screen {n} opacity=1 attention=off")

sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
sock.bind(f"\0ft_opacity_recover_{os.getpid()}")
sock.settimeout(2.0)
for cmd in (f"opacity {n} 1.000 1.000", f"attention {n} off"):
    try:
        sock.sendto(cmd.encode(), "\0ft_screens")
        print(cmd, "->", sock.recv(4096).decode(errors="replace"))
    except OSError as e:
        print(cmd, "-> live failed:", e, "(layout file still fixed; re-apply or restart desktop)")
