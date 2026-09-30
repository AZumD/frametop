#!/usr/bin/env python3
from pathlib import Path
import os, subprocess

def env(pid):
    d={}
    for p in Path(f"/proc/{pid}/environ").read_bytes().split(b"\0"):
        if b"=" in p:
            k,v=p.split(b"=",1); d[k.decode(errors="replace")]=v.decode(errors="replace")
    return d

def cmd(pid):
    return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0",b" ").decode(errors="replace")

# Exact python ft-mpris
for p in Path("/proc").iterdir():
    if not p.name.isdigit(): continue
    c=cmd(int(p.name))
    if c.startswith("python3 ") and "ft-mpris.py" in c:
        e=env(int(p.name))
        print("EXACT", p.name, e.get("DBUS_SESSION_BUS_ADDRESS"))
        print(" ", c[:160])
        bus=e.get("DBUS_SESSION_BUS_ADDRESS","")
        out=subprocess.run(["busctl","--user","list"],capture_output=True,text=True,env={**os.environ,"DBUS_SESSION_BUS_ADDRESS":bus},timeout=5)
        ms=[ln for ln in out.stdout.splitlines() if "mpris" in ln.lower()]
        print(" mpris_on_that_bus", ms[:20] or "NONE")
        # list flatpak chromium buses too
        for q in Path("/proc").iterdir():
            if not q.name.isdigit(): continue
            qc=cmd(int(q.name))
            if "/app/chromium/chrome " in qc and "--type=" not in qc:
                qe=env(int(q.name))
                print("CHROME_MAIN", q.name, "bus=", qe.get("DBUS_SESSION_BUS_ADDRESS"))
                print(" ", qc[:160])
                # try list mpris on chrome's bus if any
                cb=qe.get("DBUS_SESSION_BUS_ADDRESS","")
                if cb:
                    o2=subprocess.run(["busctl","--user","list"],capture_output=True,text=True,env={**os.environ,"DBUS_SESSION_BUS_ADDRESS":cb},timeout=5)
                    print(" chrome_bus_mpris", [ln for ln in o2.stdout.splitlines() if "mpris" in ln.lower()][:10] or "NONE")
                # flatpak info
                break
        # Also check host bus
        o3=subprocess.run(["busctl","--user","list"],capture_output=True,text=True,timeout=5)
        print("host_bus_mpris", [ln for ln in o3.stdout.splitlines() if "mpris" in ln.lower()][:10] or "NONE")
        break
else:
    print("no exact mpris python")
