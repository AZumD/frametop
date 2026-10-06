#!/usr/bin/env python3
"""Port desktop_actions / current_desktops / shown_in into ft_desktop.py."""
from __future__ import annotations

import re
from pathlib import Path

SRC = Path("/mnt/c/Users/Antho/Projects/frametop-stage1-chrome/layout/ft_desktop.py")
DST = Path(__file__).resolve().parents[1] / "layout" / "ft_desktop.py"

src = SRC.read_text(encoding="utf-8")
dst = DST.read_text(encoding="utf-8")

for name in ("current_desktops", "shown_in", "desktop_actions"):
    if f"def {name}(" in dst:
        print(name, "already present")
        continue
    m = re.search(rf"^def {name}\(.*?(?=^def |\Z)", src, flags=re.M | re.S)
    if not m:
        raise SystemExit(f"missing {name}")
    m2 = re.search(r"^def applications_dirs\(.*?(?=^def )", dst, flags=re.M | re.S)
    if not m2:
        raise SystemExit("applications_dirs missing")
    insert_at = m2.end()
    dst = dst[:insert_at] + m.group(0).rstrip() + "\n\n" + dst[insert_at:]
    print("added", name)

# StartupWMClass / categories if stage1 parse has them and ours doesn't
if "startup_wm_class" not in dst and "StartupWMClass" in src:
    # Replace our parse_desktop_file with stage1's if significantly richer — too risky.
    # Instead patch the key mapping if we have a simple keys dict.
    print("NOTE: StartupWMClass not in customized ft_desktop — Start menu matching may be weaker")

DST.write_text(dst, encoding="utf-8")
print("wrote", DST)
