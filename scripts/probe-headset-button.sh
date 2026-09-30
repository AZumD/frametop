#!/usr/bin/env bash
# Identify Steam Frame physical button candidates (gpio-keys, pmic, steamos-manager).
set -euo pipefail
python3 - <<'PY'
import os, struct, fcntl, array, glob

EVIOCGBIT = lambda et, n: 0x80004520 | ((n & 0xfff) << 16) | ((et & 0xff) << 8)  # wrong, use ioctl constants
# Use EVIOCGBIT from linux/input.h: _IOC(_IOC_READ,'E',0x20+ev,...) 
import ctypes, ctypes.util
EV_KEY = 1
KEY_MAX = 0x2ff

def eviocgbit(ev, size):
    # _IOR('E', 0x20 + ev, size bytes)
    return 0x80004500 | ((size & 0xfff) << 16) | (0x20 + ev)

def bits(fd, size):
    buf = array.array('B', [0]*size)
    try:
        fcntl.ioctl(fd, eviocgbit(EV_KEY, size), buf, True)
    except OSError as e:
        return set()
    out=set()
    for i,b in enumerate(buf):
        for bit in range(8):
            if b & (1<<bit):
                out.add(i*8+bit)
    return out

NAMES = {
    116: "KEY_POWER", 114: "KEY_VOLUMEDOWN", 115: "KEY_VOLUMEUP",
    125: "KEY_LEFTMETA", 139: "KEY_MENU", 172: "KEY_HOMEPAGE",
    582: "KEY_VOICECOMMAND",  # guess
    240: "KEY_UNKNOWN",
}
# Common Steam Deck / Frame-ish
for k,v in [(113,"KEY_MUTE"),(163,"KEY_NEXTSONG"),(165,"KEY_PREVIOUSSONG"),
            (166,"KEY_STOPCD"),(164,"KEY_PLAYPAUSE"),(152,"KEY_COFFEE"),
            (438,"KEY_PROG1"),(439,"KEY_PROG2"),(226,"KEY_MEDIA"),
            (59,"KEY_F1"),(60,"KEY_F2"),(90,"KEY_F10")]:
    NAMES[k]=v

print("Scanning /dev/input/event*")
for path in sorted(glob.glob("/dev/input/event*"), key=lambda p: int(p.replace("/dev/input/event",""))):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    except OSError as e:
        print(path, "open fail", e)
        continue
    name = "?"
    try:
        buf = array.array('B', [0]*256)
        # EVIOCGNAME
        fcntl.ioctl(fd, 0x81004506, buf, True)
        name = bytes(buf).split(b'\0',1)[0].decode('utf-8','replace')
    except OSError:
        pass
    keys = sorted(bits(fd, (KEY_MAX+7)//8))
    os.close(fd)
    if not keys:
        continue
    labeled = [f"{k}:{NAMES.get(k,'?')}" for k in keys]
    print(f"{path} name={name!r} keys={labeled}")
PY

echo "=== try reading gpio-keys / steamos-manager briefly (2s) — press headset button now ==="
timeout 2s cat /dev/input/event3 2>/dev/null | xxd | head -20 || true
echo "(done waiting)"
