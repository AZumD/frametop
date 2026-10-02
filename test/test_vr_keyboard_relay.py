#!/usr/bin/env python3
"""Phase 2: Frametop's keyboard in the input relay.

Covers (against input/input-relay.py, with every socket renamed, no uinput, no grabs):
  - the constants: keyboard_toggle in ACTIONS (before "key"), VR_KEYBOARD_MODES, docstrings
  - uinput detection from sysfs (Node.uinput, Node.describe) through the real probe()
  - "textfield 1|0" for each vr_keyboard mode and vr_keyboard_persist, including the default
    (no_keyboard, persist on) and "a program's uinput keyboard doesn't count"
  - keyboard_toggle from a Frame controller button ("vrbtn") and from a mouse button, and
    "never" turning it off
  - the Phase 1 hardening still holds: malformed datagrams don't kill the relay

Requires Linux abstract AF_UNIX sockets (Frame host or WSL).

  python3 test/test_vr_keyboard_relay.py
"""
from __future__ import annotations

import fcntl
import importlib.util
import json
import os
import socket
import struct
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RELAY_PATH = os.path.join(ROOT, "input", "input-relay.py")

if not hasattr(socket, "AF_UNIX"):
    print("SKIP: AF_UNIX not available on this platform")
    sys.exit(0)
try:
    _probe = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    _probe.bind("\0ft_vrkb_test_probe_%d" % os.getpid())
    _probe.close()
except OSError as e:
    print(f"SKIP: abstract AF_UNIX unavailable ({e})")
    sys.exit(0)

tag = f"ft_vrkb_test_{os.getpid()}"
with open(RELAY_PATH, encoding="utf-8") as f:
    SOURCE = f.read()
src = SOURCE.replace('"\\0frametop_relay"', f'"\\0{tag}_relay"')

relay = importlib.util.module_from_spec(importlib.util.spec_from_loader("relay", loader=None))
relay.__file__ = os.path.abspath(RELAY_PATH)
exec(compile(src, RELAY_PATH, "exec"), relay.__dict__)  # noqa: S102

relay.SCREENS = f"\0{tag}_screens"
relay.HELPER = f"\0{tag}_helper"
relay.KEYS = f"\0{tag}_keys"
relay.log = lambda *a, **k: None

failures: list[str] = []


def check(label, ok, detail=""):
    print(("ok    " if ok else "FAIL  ") + label + ("" if ok or not detail else f": {detail}"), flush=True)
    if not ok:
        failures.append(label)


# ---------------------------------------------------------------- constants (no relay running)

def test_constants():
    acts = relay.ACTIONS
    check("keyboard_toggle in ACTIONS", "keyboard_toggle" in acts)
    check("keyboard_toggle comes before key", acts.index("keyboard_toggle") < acts.index("key"))
    check("key and none still last", acts[-2:] == ("key", "none"), repr(acts[-3:]))
    check("VR_KEYBOARD_MODES", relay.VR_KEYBOARD_MODES == ("always", "no_keyboard", "button", "never"),
          repr(relay.VR_KEYBOARD_MODES))
    check("module docstring names keyboard_toggle", "keyboard_toggle" in relay.__dict__.get("__doc__", "")
          or "keyboard_toggle" in SOURCE.split('"""', 2)[1])
    check("module docstring names textfield", "textfield 1|0" in SOURCE.split('"""', 2)[1])
    doc = relay.read_rules.__doc__
    check("read_rules docstring names vr_keyboard", "vr_keyboard" in doc and "vr_keyboard_persist" in doc, doc)
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "rules.json")
        check("read_rules missing file keeps shape",
              relay.read_rules(path) == {"devices": {}, "buttons": {}, "controller_buttons": {}})
        with open(path, "w") as f:
            json.dump({"vr_keyboard": "button", "vr_keyboard_persist": False}, f)
        r = relay.read_rules(path)
        check("read_rules passes vr_keyboard through", r["vr_keyboard"] == "button" and r["vr_keyboard_persist"] is False)


# ---------------------------------------------------------------- uinput detection through probe()

def probe_with_sysfs(sysfs_target):
    """Run the real probe() on /dev/null with evdev ioctls and the sysfs lookup faked."""
    class Path:
        def __getattr__(self, name):
            return getattr(os.path, name)

        def realpath(self, p):
            return sysfs_target if p.startswith("/sys/class/input/") else os.path.realpath(p)

    class FakeOs:
        path = Path()

        def __getattr__(self, name):
            return getattr(os, name)

    def ioctl(fd, request, arg=0, *rest):
        kind, nr, size = (request >> 8) & 0xFF, request & 0xFF, (request >> 16) & 0x3FFF
        if kind != ord("E"):
            return 0
        if nr == 0x06:  # EVIOCGNAME
            arg[:19] = b"uinput test keybd\0\0"
        elif nr == 0x02:  # EVIOCGID: bus, vendor, product, version
            arg[:8] = struct.pack("HHHH", relay.BUS_USB, 0x1234, 0x5678, 1)
        elif nr == 0x08:  # EVIOCGUNIQ
            pass
        elif nr == 0x20 + relay.EV_KEY:  # key bits: KEY_A
            arg[relay.KEY_A // 8] |= 1 << (relay.KEY_A % 8)
        return 0

    class FakeFcntl:
        pass

    ff = FakeFcntl()
    ff.__dict__.update(fcntl.__dict__)
    ff.ioctl = ioctl
    real = relay.__dict__["os"], relay.__dict__["fcntl"]
    relay.os, relay.fcntl = FakeOs(), ff
    try:
        node = relay.probe("/dev/null")
    finally:
        relay.os, relay.fcntl = real
    return node


def test_uinput_detection():
    n = probe_with_sysfs("/sys/devices/virtual/input/input42/event7")
    check("probe: virtual sysfs path means uinput", n is not None and n.uinput is True)
    check("probe: describe() carries uinput", n is not None and n.describe().get("uinput") is True)
    check("probe: keyboard recognised", n is not None and n.is_keyboard and n.candidate)
    if n:
        os.close(n.fd)
    n = probe_with_sysfs("/sys/devices/platform/soc/usb1/1-1/input/input3/event3")
    check("probe: platform sysfs path is a real device", n is not None and n.uinput is False)
    check("probe: describe() carries uinput false", n is not None and n.describe().get("uinput") is False)
    if n:
        os.close(n.fd)
    # Bluetooth LE devices come through uhid, under virtual/misc: real devices, not uinput.
    n = probe_with_sysfs("/sys/devices/virtual/misc/uhid/0005:1234:5678.0001/input/input9/event9")
    check("probe: uhid under virtual/misc is a real BT device, not uinput",
          n is not None and n.uinput is False)
    if n:
        os.close(n.fd)
    n = relay.Node("/dev/input/event1", -1, "x", relay.BUS_USB, 1, 2, "", False, True)
    check("Node default uinput False", n.uinput is False and n.describe()["uinput"] is False)


# ---------------------------------------------------------------- relay running

NODES: dict[str, dict] = {}  # path -> {"r": fd, "w": fd, "uinput": bool, "mouse": bool}
LISTING: list[str] = []


def add_node(path, uinput, name):
    r, w = os.pipe()
    os.set_blocking(r, False)
    NODES[path] = {"r": r, "w": w, "uinput": uinput, "name": name}
    LISTING.append(os.path.basename(path))


class NoDevice:
    def __init__(self, *args, **kwargs):
        pass

    def emit(self, *args):
        pass

    def sync(self):
        pass


RULES: dict = {"devices": {}, "buttons": {}, "controller_buttons": {}}
CONF: dict = {"POINTER": "1"}


def start_relay():
    relay.Virtual = NoDevice
    relay.read_config = lambda path=None: dict(CONF)
    relay.read_rules = lambda path=None: json.loads(json.dumps(RULES))
    relay.notify = lambda *a, **k: None
    relay.atexit.register = lambda *a, **k: None
    relay.signal.signal = lambda *a, **k: None

    class Inode:
        st_ino = 1

    fake_os = type(os)("os")
    fake_os.__dict__.update(os.__dict__)
    real_listdir, real_stat = os.listdir, os.stat
    fake_os.listdir = lambda p: list(LISTING) if p == "/dev/input" else real_listdir(p)
    fake_os.stat = lambda p, *a, **k: Inode() if p.startswith("/dev/input/event") else real_stat(p, *a, **k)
    relay.os = fake_os

    def ioctl(fd, request, arg=0, *rest):
        if request in (relay.EVIOCGKEY, relay.EVIOCGRAB):
            return 0
        return fcntl.ioctl(fd, request, arg, *rest)

    fake_fcntl = type(fcntl)("fcntl")
    fake_fcntl.__dict__.update(fcntl.__dict__)
    fake_fcntl.ioctl = ioctl
    relay.fcntl = fake_fcntl

    def probe(path):
        spec = NODES.get(path)
        if not spec:
            return None
        return relay.Node(path, spec["r"], spec["name"], relay.BUS_USB, 1, 2 + int(spec["uinput"]), "",
                          False, True, uinput=spec["uinput"])

    relay.probe = probe
    t = threading.Thread(target=relay.main, daemon=True)
    sys.argv = [RELAY_PATH, "--no-grab"]
    t.start()


screens = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
screens.bind(relay.SCREENS)
screens.settimeout(0.05)


def keyboard_cmds(wait=0.0):
    """The vrkeyboard datagrams that reached ft-screens since last time."""
    if wait:
        time.sleep(wait)
    got = []
    while True:
        try:
            msg = screens.recv(256).decode()
        except socket.timeout:
            return got
        if msg.startswith("vrkeyboard"):
            got.append(msg)


def relay_send(cmd: bytes):
    c = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    c.sendto(cmd, f"\0{tag}_relay")
    c.close()


def ask(cmd: bytes, timeout=2.0):
    c = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    c.bind("")
    c.settimeout(timeout)
    c.sendto(cmd, f"\0{tag}_relay")
    try:
        return c.recv(65536)
    finally:
        c.close()


def set_rules(**rules):
    RULES.clear()
    RULES.update({"devices": {}, "buttons": {}, "controller_buttons": {}}, **rules)
    ask(b"reload")  # answered once load_config() has re-read the rules
    keyboard_cmds(0.1)


def textfield(focused):
    relay_send(b"textfield 1" if focused else b"textfield 0")
    return keyboard_cmds(0.25)


EVENT = struct.Struct("llHHi")


def key_event(path, code, value):
    os.write(NODES[path]["w"], EVENT.pack(0, 0, relay.EV_KEY, code, value) + EVENT.pack(0, 0, 0, 0, 0))
    return keyboard_cmds(0.25)


def wait_for_nodes(count, timeout=3.5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        devs = json.loads(ask(b"devices"))
        if len([n for n in devs["nodes"]]) == count:
            return devs
        time.sleep(0.2)
    return json.loads(ask(b"devices"))


def run_relay_tests():
    time.sleep(1.3)  # first scan
    devs = wait_for_nodes(1)
    check("devices lists the fake keyboard", len(devs["nodes"]) == 1, repr(devs)[:160])
    check("devices JSON carries uinput", devs["nodes"] and devs["nodes"][0].get("uinput") is False,
          repr(devs["nodes"])[:160])
    check("pointer mode is on for the button tests", devs.get("pointer_mode") is True)

    # --- Phase 1: a malformed datagram doesn't end the relay ---
    relay_send(b"watch abc")
    relay_send(b"textfield")  # no argument: ignored by the length check
    relay_send(b"vrbtn nonsense 1")
    time.sleep(0.2)
    check("textfield with no argument sends nothing", keyboard_cmds() == [])
    check("relay survived malformed datagrams", json.loads(ask(b"devices")).get("t") == "devices")

    # --- defaults: no_keyboard + persist on ---
    set_rules()
    check("default (no_keyboard): a real keyboard is connected, so no keyboard opens",
          textfield(True) == [], "")
    check("default persist: losing focus does not hide", textfield(False) == [])

    # --- always ---
    set_rules(vr_keyboard="always")
    check("always: text field opens the keyboard", textfield(True) == ["vrkeyboard show"])
    check("always + persist default: focus lost leaves it open", textfield(False) == [])
    set_rules(vr_keyboard="always", vr_keyboard_persist=False)
    check("always + persist off: focus lost hides it", textfield(False) == ["vrkeyboard hide"])
    check("always + persist off: text field still opens it", textfield(True) == ["vrkeyboard show"])

    # --- button / never: a text field doesn't open it ---
    set_rules(vr_keyboard="button")
    check("button: text field does not open it", textfield(True) == [])
    set_rules(vr_keyboard="never")
    check("never: text field does not open it", textfield(True) == [])
    set_rules(vr_keyboard="bogus-mode")
    check("unknown mode falls back to no_keyboard (keyboard connected: nothing)", textfield(True) == [])

    # --- keyboard_toggle from a Frame controller button ---
    set_rules(vr_keyboard="no_keyboard", controller_buttons={"right/a": "keyboard_toggle"})
    relay_send(b"vrbtn right/a 1")
    check("controller button press toggles the keyboard", keyboard_cmds(0.25) == ["vrkeyboard toggle"])
    relay_send(b"vrbtn right/a 0")
    check("controller button release does nothing", keyboard_cmds(0.25) == [])
    set_rules(vr_keyboard="never", controller_buttons={"right/a": "keyboard_toggle"})
    relay_send(b"vrbtn right/a 1")
    check("never: the button does nothing either", keyboard_cmds(0.25) == [])
    set_rules(vr_keyboard="button", controller_buttons={"right/a": "keyboard_toggle"})
    relay_send(b"vrbtn right/a 1")
    check("button mode: the button opens it", keyboard_cmds(0.25) == ["vrkeyboard toggle"])
    # The relay tells the pointer helper which controller buttons to take: keyboard_toggle is one.
    helper = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    helper.bind(relay.HELPER)
    helper.settimeout(0.3)
    relay_send(b"vrhello")
    bound = None
    try:
        while True:
            msg = helper.recv(512).decode()
            if msg.startswith("vrbind"):
                bound = msg
    except socket.timeout:
        pass
    helper.close()
    check("vrbind includes the keyboard_toggle button", bound is not None and "right/a" in bound, repr(bound))

    # --- keyboard_toggle from a mouse button ---
    node_id = "usb:0001:0002:test keyboard"
    BTN_SIDE = 0x113
    set_rules(vr_keyboard="button", devices={node_id: {"role": "pointer"}},
              buttons={node_id: {str(BTN_SIDE): "keyboard_toggle"}})
    got = key_event("/dev/input/event900", BTN_SIDE, 1)
    check("mouse button press toggles the keyboard", got == ["vrkeyboard toggle"], repr(got))
    got = key_event("/dev/input/event900", BTN_SIDE, 0)
    check("mouse button release does nothing", got == [], repr(got))
    set_rules(vr_keyboard="never", devices={node_id: {"role": "pointer"}},
              buttons={node_id: {str(BTN_SIDE): "keyboard_toggle"}})
    got = key_event("/dev/input/event900", BTN_SIDE, 1)
    check("never: the mouse button does nothing", got == [], repr(got))
    set_rules()

    # --- no_keyboard with only a uinput keyboard: it doesn't count as connected ---
    add_node("/dev/input/event901", True, "frame-voice virtual keyboard")
    LISTING.remove("event900")
    os.close(NODES["/dev/input/event900"]["w"])  # EOF: the relay drops the real keyboard
    deadline = time.monotonic() + 4
    devs = {}
    while time.monotonic() < deadline:
        devs = json.loads(ask(b"devices"))
        if [n["path"] for n in devs["nodes"]] == ["/dev/input/event901"]:
            break
        time.sleep(0.2)
    check("only the uinput keyboard remains",
          [n["path"] for n in devs.get("nodes", [])] == ["/dev/input/event901"], repr(devs)[:200])
    check("uinput node is described as uinput", devs["nodes"] and devs["nodes"][0]["uinput"] is True)
    set_rules(vr_keyboard="no_keyboard")
    check("no_keyboard: a program's uinput keyboard doesn't count, the keyboard opens",
          textfield(True) == ["vrkeyboard show"])

    # --- a real keyboard set to Ignore doesn't count either; one that passes through does ---
    add_node("/dev/input/event902", False, "second keyboard")
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline and len(json.loads(ask(b"devices"))["nodes"]) < 2:
        time.sleep(0.2)
    check("second (real) keyboard appeared", len(json.loads(ask(b"devices"))["nodes"]) == 2)
    set_rules(vr_keyboard="no_keyboard")
    check("no_keyboard: a pass-through keyboard is connected, nothing opens", textfield(True) == [])
    set_rules(vr_keyboard="no_keyboard", devices={"usb:0001:0002:second keyboard": {"role": "ignore"}})
    check("no_keyboard: an Ignore keyboard doesn't count, the keyboard opens",
          textfield(True) == ["vrkeyboard show"])
    set_rules(vr_keyboard="no_keyboard", devices={"usb:0001:0002:second keyboard": {"role": "pointer"}})
    check("no_keyboard: a pointer-role keyboard doesn't count either", textfield(True) == ["vrkeyboard show"])

    check("relay still answers at the end", json.loads(ask(b"devices")).get("t") == "devices")


def main():
    test_constants()
    test_uinput_detection()
    add_node("/dev/input/event900", False, "test keyboard")
    start_relay()
    run_relay_tests()
    if failures:
        print(f"{len(failures)} failure(s): {failures}", file=sys.stderr)
        sys.exit(1)
    print("all vr-keyboard relay checks passed")


if __name__ == "__main__":
    main()
