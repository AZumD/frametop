#!/usr/bin/env python3
"""Dump the exact upstream cutout helper block for porting into our vr.cpp."""
from pathlib import Path
vr = Path("/tmp/up-vr.cpp").read_text()
# Extract from SetScreenTexture through end of UpdateCutouts
start = vr.find("void SetScreenTexture(")
end = vr.find("// Steam in front:", start)
Path("/tmp/up-cutout-block.cpp").write_text(vr[start:end])
print("wrote", end-start, "bytes")
# present fragment around s.key
i = vr.find("bool ft_vr_screen_present")
Path("/tmp/up-present.cpp").write_text(vr[i:i+2200])
i = vr.find("void ft_vr_forget")
Path("/tmp/up-forget.cpp").write_text(vr[i:i+900])
# cutouts command
i = vr.find('sscanf(cmd, "cutouts %15s"')
Path("/tmp/up-cutouts-cmd.cpp").write_text(vr[i-40:i+900])
print("helpers ready")
