#!/usr/bin/env bash
# Who holds gpio-keys / event3 on the Frame?
set -euo pipefail
name=$(cat /sys/class/input/event3/device/name 2>/dev/null || echo missing)
echo "event3 name=$name"
python3 - <<'PY'
import os
path = "/dev/input/event3"
for pid in os.listdir("/proc"):
    if not pid.isdigit():
        continue
    fd_dir = f"/proc/{pid}/fd"
    try:
        fds = os.listdir(fd_dir)
    except OSError:
        continue
    for fd in fds:
        try:
            t = os.readlink(f"{fd_dir}/{fd}")
        except OSError:
            continue
        if t == path or t.endswith("/event3"):
            try:
                cmd = open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\0", b" ").decode(errors="replace")[:140]
            except OSError:
                cmd = "?"
            print(f"pid={pid} fd={fd} {cmd!r}")
PY
echo "=== gpio-keys keys ==="
# KEY bits already known; list volume/select
python3 - <<'PY'
import os, fcntl, array
EV_KEY=1
KEY_MAX=0x2ff
def eviocgbit(ev, size):
    return 0x80004500 | ((size & 0xfff) << 16) | (0x20 + ev)
fd=os.open("/dev/input/event3", os.O_RDONLY|os.O_NONBLOCK)
buf=array.array("B",[0]*((KEY_MAX+7)//8))
fcntl.ioctl(fd, eviocgbit(EV_KEY, len(buf)), buf, True)
keys=sorted(i for i,b in enumerate(buf) for bit in range(8) if (i*8+bit)<=KEY_MAX and b&(1<<bit))
print("keys", keys)
os.close(fd)
PY
