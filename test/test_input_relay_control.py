#!/usr/bin/env python3
"""Automated tests for input-relay control hardening and stuck-key reconcile.

Runs the relay's main() against a fake pass-through keyboard (pipe), with every
socket renamed, no uinput devices, and no grabs. Safe next to a live desktop.

Requires Linux abstract AF_UNIX sockets (Frame host or WSL).

  python3 test/test_input_relay_control.py
"""
from __future__ import annotations

import fcntl
import importlib.util
import json
import os
import socket
import struct
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RELAY_PATH = os.path.join(ROOT, "input", "input-relay.py")

if not hasattr(socket, "AF_UNIX"):
    print("SKIP: AF_UNIX not available on this platform")
    sys.exit(0)

# Probe abstract sockets (Linux / WSL).
try:
    _probe = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    _probe.bind("\0ft_relay_test_probe_%d" % os.getpid())
    _probe.close()
except OSError as e:
    print(f"SKIP: abstract AF_UNIX unavailable ({e})")
    sys.exit(0)

tag = f"ft_relay_test_{os.getpid()}"
with open(RELAY_PATH, encoding="utf-8") as f:
    src = f.read().replace('"\\0frametop_relay"', f'"\\0{tag}_relay"')

relay = importlib.util.module_from_spec(importlib.util.spec_from_loader("relay", loader=None))
relay.__file__ = os.path.abspath(RELAY_PATH)
exec(compile(src, RELAY_PATH, "exec"), relay.__dict__)  # noqa: S102

relay.SCREENS = f"\0{tag}_screens"
relay.HELPER = f"\0{tag}_helper"
relay.KEYS = f"\0{tag}_keys"
relay.log = lambda *a, **k: None


class NoDevice:
    def __init__(self, *args, **kwargs):
        pass

    def emit(self, *args):
        pass

    def sync(self):
        pass


relay.Virtual = NoDevice
relay.read_config = lambda path=None: {"POINTER": "0"}
relay.read_rules = lambda path=None: {"devices": {}, "buttons": {}, "controller_buttons": {}}
relay.notify = lambda *a, **k: None
relay.atexit.register = lambda *a, **k: None
relay.signal.signal = lambda *a, **k: None

kb_r, kb_w = os.pipe()
os.set_blocking(kb_r, False)
FAKE = {"/dev/input/event900": kb_r}
HELD: dict[int, set[int]] = {kb_r: set()}


class Inode:
    st_ino = 1


fake_os = type(os)("os")
fake_os.__dict__.update(os.__dict__)
fake_os.listdir = lambda path: ["event900"] if path == "/dev/input" else os.listdir(path)
fake_os.stat = lambda path, *a, **k: Inode() if path in FAKE else os.stat(path, *a, **k)
# Avoid scanning a missing /dev/input on non-Frame hosts when something slips through.
_real_listdir = os.listdir


def _listdir(path):
    if path == "/dev/input":
        return ["event900"]
    return _real_listdir(path)


fake_os.listdir = _listdir
relay.os = fake_os


def ioctl(fd, request, arg=0, *rest):
    if fd in HELD and request == relay.EVIOCGKEY:
        for c in HELD[fd]:
            arg[c // 8] |= 1 << (c % 8)
        return 0
    if request in (relay.EVIOCGRAB,):
        return 0
    return fcntl.ioctl(fd, request, arg, *rest)


fake_fcntl = type(fcntl)("fcntl")
fake_fcntl.__dict__.update(fcntl.__dict__)
fake_fcntl.ioctl = ioctl
relay.fcntl = fake_fcntl


def probe(path):
    return relay.Node(path, kb_r, "test keyboard", relay.BUS_USB, 1, 2, "", False, True)


relay.probe = probe

screens = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
screens.bind(relay.SCREENS)
screens.settimeout(0.05)
EVENT = struct.Struct("llHHi")

failures: list[str] = []


def check(label, ok, detail=""):
    print(("ok    " if ok else "FAIL  ") + label + ("" if ok or not detail else f": {detail}"), flush=True)
    if not ok:
        failures.append(label)


def ask(cmd: bytes, timeout=2.0):
    c = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    c.bind("")
    c.settimeout(timeout)
    c.sendto(cmd, f"\0{tag}_relay")
    try:
        return c.recv(65536)
    finally:
        c.close()


def typed(wait=0.0):
    if wait:
        time.sleep(wait)
    got = []
    while True:
        try:
            got.append(screens.recv(256).decode())
        except socket.timeout:
            return got


def send_key(code, value):
    held = HELD[kb_r]
    (held.add if value else held.discard)(code)
    os.write(kb_w, EVENT.pack(0, 0, relay.EV_KEY, code, value) + EVENT.pack(0, 0, 0, 0, 0))
    time.sleep(0.05)


def tell_desktop():
    """ft-screens tells the relay typing goes to the desktop (grabs passthrough)."""
    c = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    c.sendto(b"keyboard desktop", f"\0{tag}_relay")
    c.close()
    time.sleep(0.1)


def run_tests():
    # Wait for first scan + startup modifier sanitation traffic.
    time.sleep(1.2)
    typed()  # drain startup Meta/Ctrl/Alt/Shift releases

    # --- malformed control datagram ---
    raw = ask(b"devices")
    msg = json.loads(raw.decode())
    check("devices before malformed", msg.get("t") == "devices", repr(msg)[:120])

    # Must not kill the relay (no reply expected; watch abc raises ValueError).
    c = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    c.bind("")
    c.settimeout(0.3)
    try:
        c.sendto(b"watch abc", f"\0{tag}_relay")
        try:
            c.recv(4096)
        except socket.timeout:
            pass
    finally:
        c.close()
    time.sleep(0.2)

    raw2 = ask(b"devices")
    msg2 = json.loads(raw2.decode())
    check("devices after malformed", msg2.get("t") == "devices", repr(msg2)[:120])
    check("relay survived malformed watch", True)

    # --- normal press/release ---
    tell_desktop()
    typed()
    KEY_A = 30
    send_key(KEY_A, 1)
    send_key(KEY_A, 0)
    got = typed(0.15)
    check("normal key down+up", got == [f"key {KEY_A} 1", f"key {KEY_A} 0"], repr(got))

    # --- lost release: physical EVIOCGKEY clears without an up event ---
    tell_desktop()
    typed()
    send_key(KEY_A, 1)
    got = typed(0.1)
    check("lost-release press reached desktop", got == [f"key {KEY_A} 1"], repr(got))
    HELD[kb_r].discard(KEY_A)  # simulate lost up / kernel no longer reports held
    # Wait for next device scan (~1s) to reconcile.
    deadline = time.monotonic() + 2.5
    released = []
    while time.monotonic() < deadline:
        released.extend(typed(0.2))
        if f"key {KEY_A} 0" in released:
            break
    check("lost release reconciled", f"key {KEY_A} 0" in released, repr(released))

    # --- stuck modifiers ---
    tell_desktop()
    typed()
    for code in (29, 42, 56, 125):  # Ctrl, Shift, Alt, Meta
        send_key(code, 1)
    typed(0.1)
    HELD[kb_r].clear()
    deadline = time.monotonic() + 2.5
    released = []
    while time.monotonic() < deadline:
        released.extend(typed(0.2))
        if all(f"key {c} 0" in released for c in (29, 42, 56, 125)):
            break
    check(
        "stuck modifiers reconciled",
        all(f"key {c} 0" in released for c in (29, 42, 56, 125)),
        repr(released),
    )

    # --- device disappearance (close the node so the relay drops it; last test) ---
    tell_desktop()
    typed()
    META = 125
    send_key(META, 1)
    got = typed(0.1)
    check("meta press before vanish", f"key {META} 1" in got, repr(got))
    HELD.pop(kb_r, None)
    fake_os.listdir = lambda path: [] if path == "/dev/input" else _real_listdir(path)
    os.close(kb_w)  # EOF on the reader → relay drops the node; reconcile frees screens_down
    deadline = time.monotonic() + 2.5
    released = []
    while time.monotonic() < deadline:
        released.extend(typed(0.2))
        if f"key {META} 0" in released:
            break
    check("device vanish releases meta on desktop", f"key {META} 0" in released, repr(released))


def main():
    t = threading.Thread(target=relay.main, kwargs={}, daemon=True)
    # --no-grab so apply_roles never tries real EVIOCGRAB paths that need more stubs.
    sys.argv = [RELAY_PATH, "--no-grab"]
    t.start()
    try:
        run_tests()
    finally:
        # Daemon thread dies with process.
        pass
    if failures:
        print(f"{len(failures)} failure(s)", file=sys.stderr)
        sys.exit(1)
    print("all input-relay control/reconcile checks passed")


if __name__ == "__main__":
    main()
