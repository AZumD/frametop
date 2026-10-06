#!/usr/bin/env python3
"""Apply surgical FramePanel / pressKey / up changes to ft-pointer.cpp."""
from pathlib import Path

path = Path("/mnt/c/Users/Antho/Projects/frametop-customized-main/pointer/helper/ft-pointer.cpp")
t = path.read_text(encoding="utf-8")
orig = t

# 1. FramePanel before SendTo
frame_panel = '''// A Frametop desktop panel the laser can drag across: a screen (frametop.screen.N), a floating
// window (frametop.float.N), or a floating window's popup (frametop.float.N.sub.K), not a
// control of theirs.
bool FramePanel(const std::string &key) {
    for (const char *prefix : {"frametop.screen.", "frametop.float."}) {
        if (key.rfind(prefix, 0) != 0) continue;
        const std::string rest = key.substr(std::strlen(prefix));
        const size_t dot = rest.find('.');
        return dot == std::string::npos || rest.compare(dot, 5, ".sub.") == 0;
    }
    return false;
}

'''

if "bool FramePanel" not in t:
    needle = "void SendTo(int fd, const char *name, const std::string &msg) {"
    if needle not in t:
        raise SystemExit("SendTo not found")
    t = t.replace(needle, frame_panel + needle, 1)

# 2. pressKey / pressPose decls
decls_old = """    bool leftHeld = false, tilting = false, tiltStart = false, swallowedRight = false;
    double tiltYaw = 0, tiltPitch = 0;
    double dragDistance = 0, lastDistance = 1.5;  // drag lock: distance from the anchor at the press
"""
decls_new = """    bool leftHeld = false, tilting = false, tiltStart = false, swallowedRight = false;
    double tiltYaw = 0, tiltPitch = 0;
    double dragDistance = 0, lastDistance = 1.5;  // drag lock: distance from the anchor at the press
    // While left is held on a FramePanel that hasn't moved yet, retarget dragDistance across
    // other FramePanels (floating windows span multiple overlays). Cleared once the pressed
    // panel moves (title-bar carry / screen drag).
    std::string pressKey;
    vr::HmdMatrix34_t pressPose{};
"""
if "pressKey" not in t:
    if decls_old not in t:
        raise SystemExit("leftHeld decls not found")
    t = t.replace(decls_old, decls_new, 1)

# 3. pressLeft: capture press pose
press_old = """        nudging = false;
        leftHeld = true;
        dragDistance = lastDistance;
        tiltYaw = tiltPitch = 0;  // a new drag starts untilted
        dropHoldUntil = {};
        pulseAt = Clock::now();
        SendTo(out, "ft_pointer", "btn trigger 1");
    };
"""
press_new = """        nudging = false;
        leftHeld = true;
        dragDistance = lastDistance;
        pressKey.clear();
        if (FramePanel(lastHit)) {
            vr::ETrackingUniverseOrigin uo;
            auto it = handles.find(lastHit);
            if (it != handles.end() &&
                overlay->GetOverlayTransformAbsolute(it->second, &uo, &pressPose) == vr::VROverlayError_None)
                pressKey = lastHit;
        }
        tiltYaw = tiltPitch = 0;  // a new drag starts untilted
        dropHoldUntil = {};
        pulseAt = Clock::now();
        SendTo(out, "ft_pointer", "btn trigger 1");
    };
"""
if "if (FramePanel(lastHit))" not in t:
    if press_old not in t:
        raise SystemExit("pressLeft body not found")
    t = t.replace(press_old, press_new, 1)

# 4. releaseLeft: send up
rel_old = """    auto releaseLeft = [&] {
        leftHeld = false;
        tilting = false;
        // Hold the drag pose (tilt, frozen distance) while SteamVR finishes the drop.
        dropHoldUntil = Clock::now() + std::chrono::milliseconds(500);
        SendTo(out, "ft_pointer", "btn trigger 0");
        if (gazeBack) gazeOwns = true, gazeBack = false;
    };
"""
rel_new = """    auto releaseLeft = [&] {
        leftHeld = false;
        tilting = false;
        // Hold the drag pose (tilt, frozen distance) while SteamVR finishes the drop.
        dropHoldUntil = Clock::now() + std::chrono::milliseconds(500);
        SendTo(out, "ft_pointer", "btn trigger 0");
        // ft-screens releases a button held on its screens in KWin even when SteamVR hands
        // the release to some other overlay (its catcher usually gets it; this is the backstop).
        SendTo(out, "ft_screens", "up");
        if (gazeBack) gazeOwns = true, gazeBack = false;
    };
"""
if 'SendTo(out, "ft_screens", "up")' not in t:
    if rel_old not in t:
        raise SystemExit("releaseLeft not found")
    t = t.replace(rel_old, rel_new, 1)

# 5. Cross-panel retarget while press panel is still
still_block = """
            // While left is held on a still FramePanel, let the locked ray retarget across other
            // FramePanels (floating windows / their popups). Once that panel moves, the lock holds.
            if (leftHeld && !pressKey.empty()) {
                vr::ETrackingUniverseOrigin uo;
                vr::HmdMatrix34_t now{};
                auto it = handles.find(pressKey);
                bool still = it != handles.end() &&
                             overlay->GetOverlayTransformAbsolute(it->second, &uo, &now) == vr::VROverlayError_None;
                for (int i = 0; still && i < 3; ++i)
                    for (int j = 0; j < 4; ++j)
                        if (std::fabs(now.m[i][j] - pressPose.m[i][j]) > 0.001f) still = false;
                if (still) {
                    Hit h;
                    for (const auto &[key, handle] : handles) {
                        if (!visible[key] || !FramePanel(key)) continue;
                        vr::VROverlayIntersectionParams_t params{};
                        params.vSource = {float(anchor.x), float(anchor.y), float(anchor.z)};
                        params.vDirection = {float(dir.x), float(dir.y), float(dir.z)};
                        params.eOrigin = vr::TrackingUniverseStanding;
                        vr::VROverlayIntersectionResults_t r{};
                        if (overlay->ComputeOverlayIntersection(handle, &params, &r) && r.fDistance > 0.05f &&
                            r.fDistance < h.along)
                            h.along = r.fDistance, h.key = key;
                    }
                    if (h.along < 1e8) dragDistance = h.along, lastHit = h.key;
                } else {
                    pressKey.clear();  // carried: the lock holds for the rest of this press
                }
            }
"""

marker = """            // While dragging: keep the press-time distance and show the non-interactive marker.
            // On a scene-graph plane or a panel's edge: the laser-catching dot goes 5 cm behind it.
            double distance = dragging ? dragDistance : (best < 1e8 ? best : freeDistance);
"""
if "leftHeld && !pressKey.empty()" not in t:
    if marker not in t:
        raise SystemExit("drag distance marker not found")
    # Insert still_block before the distance line. Hit struct is already defined above.
    # But Hit is defined inside the else-if block before nearest - good, still_block uses Hit.
    # Problem: still_block is inserted AFTER bestKey logic but Hit is in scope. Good.
    # However still_block references `dir` and `anchor` which exist. Good.
    t = t.replace(marker, still_block + "\n" + marker, 1)

# 6. Comment about frametop panels
t = t.replace(
    "// ft-screens' panels (frametop.screen.N, the keyboard) are 0x0 and absolute too",
    "// ft-screens' panels (frametop.screen.N, frametop.float.N, the keyboard) are 0x0 and absolute too",
)

# 7. POINTER_IGNORE comment mention floats
t = t.replace(
    "    if (key.rfind(\"frametop.\", 0) == 0) return false;  // screens, keyboard, future panels",
    "    if (key.rfind(\"frametop.\", 0) == 0) return false;  // screens, floats, keyboard, instruments",
)

if t == orig:
    raise SystemExit("no changes applied")
path.write_text(t, encoding="utf-8")
print("patched", path)
print("FramePanel", t.count("FramePanel"))
print("pressKey", t.count("pressKey"))
print("ft_screens up", t.count('SendTo(out, "ft_screens", "up")'))
