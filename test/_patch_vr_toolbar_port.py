#!/usr/bin/env python3
"""Surgically port spatial toolbar inheritance into screens/vr.cpp (customized-main)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VR = ROOT / "screens" / "vr.cpp"
text = VR.read_text(encoding="utf-8")
orig = text

# 1) GazeKind: add Dock + Toolbar
old_gaze = "enum class GazeKind {\n    None, Screen, Bar, Curve, Roll, Resize, Anchor, Slot, Instrument\n};"
new_gaze = "enum class GazeKind {\n    None, Screen, Bar, Curve, Roll, Resize, Anchor, Slot, Instrument, Dock, Toolbar\n};"
if old_gaze not in text:
    raise SystemExit("GazeKind block not found")
text = text.replace(old_gaze, new_gaze, 1)

# 2) Insert ChromeStyle + spatial.inc before struct Screen
marker = "// A popup or dialog of a floating window: a small panel over it, cut from the same buffer."
if marker not in text:
    raise SystemExit("Screen prelude marker not found")
inject = r'''// Shared SteamVR-inspired chrome ratios (also used by toolbar_dock.inc).
namespace ChromeStyle {
constexpr double kGapFrac = 0.06;
constexpr double kBarHalfHFrac = 12.0 / 256.0;
}  // namespace ChromeStyle

#include "spatial.inc"

'''
if '#include "spatial.inc"' not in text:
    text = text.replace(marker, inject + marker, 1)

# 3) Change Screen to inherit; remove duplicated follow/attention/drag fields
old_screen_start = """struct Screen {
    vr::VROverlayHandle_t overlay = vr::k_ulOverlayHandleInvalid, bar = vr::k_ulOverlayHandleInvalid,
                          handle = vr::k_ulOverlayHandleInvalid, curveButton = vr::k_ulOverlayHandleInvalid,
                          rollButton = vr::k_ulOverlayHandleInvalid,
                          anchorButton = vr::k_ulOverlayHandleInvalid,
                          dockButton = vr::k_ulOverlayHandleInvalid,
                          closeButton = vr::k_ulOverlayHandleInvalid;  // dock/close: floating windows
    vr::VROverlayHandle_t slotButton[kSlotCount] = {};
    int width = 0, height = 0;    // DMA-BUF / OpenVR mouse scale (buffer pixels)
    int surfaceWidth = 0, surfaceHeight = 0;  // Wayland surface-local logical size
    double outputScale = 1.0;     // KWin output scale (Display Settings); for pointer seat map
    double metres = 1;
    double curve = 0;             // cylinder radius in metres; 0 = flat
    const void *shown = nullptr;  // a frame arrived
    bool visible = false;         // shown in VR right now
    const void *key = nullptr;    // the client buffer on it now, and its dmabuf (for cutouts)
    ft_dmabuf buf{};
    vr::SharedTextureHandle_t plain = 0;  // that buffer's SteamVR import
    bool cutting = false;         // showing a cutout buffer (side by side) instead
    bool alone = false;           // concealed: kept off the headset (windows stay on the screen)
    // Attention-aware opacity: final = attentionResolved * visibilityFade.
    // Legacy single "opacity" maps to active=idle=X with attention off.
    float activeOpacity = 1.f;
    float idleOpacity = 1.f;
    float attentionResolved = 1.f;  // smoothed idle↔active
    float visibilityFade = 1.f;
    bool attentionEnabled = false;
    double attentionInMs = 150;     // fade toward active
    double attentionOutMs = 250;    // fade toward idle
    double attentionDwellMs = 80;   // gaze must stick before activating
    double attentionHoldMs = 400;   // stay active briefly after gaze leaves / sample drop
    double attentionFocusMs = 0;    // time currently focused / unfocused accumulator
    bool attentionFocused = false;
    AnchorMode anchor = AnchorMode::World;
    vr::TrackedDeviceIndex_t pinned = kNone;  // rigid tracked-device pin only
    Mat pinRel = Identity();                  // reference/device -> screen
    Mat pose = Identity();                    // room pose (smoothed for soft follow)
    // Soft-follow dead zone: small head motion keeps a locked reference so you can
    // glance at a screen corner without the panel chasing. Past the threshold the
    // lock is pushed (excess only), so intentional turns still follow.
    bool followDeadzone = false;
    double followDeadzoneDeg = 15;            // head / yaw-follow
    double followDeadzoneM = 0.15;            // position-follow (+ head translation)
    bool followLockValid = false;
    Mat followLock = Identity();              // last soft-follow reference frame
    Drag drag = Drag::None;
    vr::TrackedDeviceIndex_t dragDevice = kNone;
    Mat dragRel = Identity();                 // device -> screen, while moving
    double grabX = 0, grabY = 0;              // resize: the grab point relative to the corner
    Mat rollFrom = Identity();                // roll: the pose at the press (pinRel when pinned)
    double rollAngle = 0;                     // the laser's angle around the centre then
    bool hover[4] = {};                       // bar, curve, roll, resize
    bool hoverAnchor = false;
    bool hoverDock = false, hoverClose = false;
"""

# Fix - the rollAngle comment might differ. Let me read exact text from file.
# We'll search for a unique smaller block instead.

new_screen_head = """struct Screen : FollowState, AttentionState, MoveDrag {
    vr::VROverlayHandle_t overlay = vr::k_ulOverlayHandleInvalid, bar = vr::k_ulOverlayHandleInvalid,
                          handle = vr::k_ulOverlayHandleInvalid, curveButton = vr::k_ulOverlayHandleInvalid,
                          rollButton = vr::k_ulOverlayHandleInvalid,
                          anchorButton = vr::k_ulOverlayHandleInvalid,
                          dockButton = vr::k_ulOverlayHandleInvalid,
                          closeButton = vr::k_ulOverlayHandleInvalid;  // float dock/close; also toolbar dock
    vr::VROverlayHandle_t slotButton[kSlotCount] = {};
    int width = 0, height = 0;    // DMA-BUF / OpenVR mouse scale (buffer pixels)
    int surfaceWidth = 0, surfaceHeight = 0;  // Wayland surface-local logical size
    double outputScale = 1.0;     // KWin output scale (Display Settings); for pointer seat map
    double metres = 1;
    double curve = 0;             // cylinder radius in metres; 0 = flat
    const void *shown = nullptr;  // a frame arrived
    bool visible = false;         // shown in VR right now
    const void *key = nullptr;    // the client buffer on it now, and its dmabuf (for cutouts)
    ft_dmabuf buf{};
    vr::SharedTextureHandle_t plain = 0;  // that buffer's SteamVR import
    bool cutting = false;         // showing a cutout buffer (side by side) instead
    bool alone = false;           // concealed: kept off the headset (windows stay on the screen)
    float visibilityFade = 1.f;
    double grabX = 0, grabY = 0;              // resize: the grab point relative to the corner
    Mat rollFrom = Identity();                // roll: the pose at the press (pinRel when pinned)
    double rollAngle = 0;                     // the laser's angle around the centre then
    bool hover[4] = {};                       // bar, curve, roll, resize
    bool hoverAnchor = false;
    bool hoverDock = false, hoverClose = false;
    // Docked to the spatial toolbar (toolbar → dock anchor → screen).
    bool docked = false;
    int dockSlot = 0;
    FollowState preDock;
"""

# Extract exact Screen start from current file between "struct Screen {" and "bool hoverDock"
import re
m = re.search(
    r"struct Screen \{.*?bool hoverDock = false, hoverClose = false;\n",
    text,
    flags=re.S,
)
if not m:
    raise SystemExit("Could not match Screen struct head")
# Also need to remove the follow/attention/drag fields that are between alone and hoverDock
# The regex above already includes everything - we replace the whole match.
text = text[: m.start()] + new_screen_head + text[m.end() :]

# Remove leftover inherited fields if still present (anchor/pinned/.../dragRestore block after hoverClose was already in match)
# After replacement, there may still be dragRestore etc if they were AFTER hoverClose
# Check - in original, after hoverClose came hoverSlot. The inherited fields were BEFORE hover. Good.

# Remove dragRestore if it's still a Screen field after drag was removed - dragRestore was with drag fields
# Looking at original: dragRestore is after onWrist. Keep those. dragRestore is in MoveDrag now!
# Need to remove: dragRestore from Screen if still there
text2 = text
# Remove duplicate MoveDrag::dragRestore line if present as Screen field
text = re.sub(
    r"\n    AnchorMode dragRestore = AnchorMode::World;  // soft/yaw/pos follow reapplied after a move",
    "",
    text,
    count=1,
)

# 4) Instrument inheritance
m = re.search(
    r"struct Instrument \{\n    std::string id;",
    text,
)
if not m:
    raise SystemExit("Instrument struct not found")
text = text[: m.start()] + "struct Instrument : FollowState, AttentionState, MoveDrag {\n    Instrument() {\n        idleOpacity = 0.35f;\n        attentionEnabled = true;\n    }\n    std::string id;" + text[m.end() :]

# Remove Instrument's duplicated follow/attention/drag field block
inst_dup = re.search(
    r"(struct Instrument : FollowState.*?\n    double metres = 0\.35;\n)"
    r"    float activeOpacity = 1\.f;\n"
    r"    float idleOpacity = 0\.35f;\n"
    r"    float attentionResolved = 1\.f;\n"
    r"    bool attentionEnabled = true;\n"
    r"    double attentionInMs = 150;\n"
    r"    double attentionOutMs = 250;\n"
    r"    double attentionDwellMs = 80;\n"
    r"    double attentionHoldMs = 400;\n"
    r"    double attentionFocusMs = 0;\n"
    r"    bool attentionFocused = false;\n"
    r"    AnchorMode anchor = AnchorMode::World;\n"
    r"    vr::TrackedDeviceIndex_t pinned = kNone;\n"
    r"    Mat pinRel = Identity\(\);\n"
    r"    Mat pose = Identity\(\);\n"
    r"    bool followDeadzone = false;\n"
    r"    double followDeadzoneDeg = 15;\n"
    r"    double followDeadzoneM = 0\.15;\n"
    r"    bool followLockValid = false;\n"
    r"    Mat followLock = Identity\(\);\n"
    r"    Drag drag = Drag::None;\n"
    r"    vr::TrackedDeviceIndex_t dragDevice = kNone;\n"
    r"    Mat dragRel = Identity\(\);\n"
    r"    AnchorMode dragRestore = AnchorMode::World;\n"
    r"(    bool hoverBar = false;)",
    text,
    flags=re.S,
)
if not inst_dup:
    raise SystemExit("Instrument duplicate fields not found")
text = text[: inst_dup.start()] + inst_dup.group(1) + inst_dup.group(2) + text[inst_dup.end() :]

# 5) Forward decls after g_imports / before hand cutouts
fwd = """
bool ScreenDocked(const Screen &s) { return s.docked; }

// desktop_toolbar.inc (included near the end of this namespace).
bool ToolbarWanted();
void EndToolbarDragsBy(vr::TrackedDeviceIndex_t dev);
void ToggleScreenDock(int index);
bool StartToolbarDrag(vr::TrackedDeviceIndex_t dev);
void PickToolbarGaze(const Mat &ray, const double origin[3], GazeTarget *best);

"""
needle = "std::map<const void *, vr::SharedTextureHandle_t> g_imports;\n\n// Hand cutouts"
if needle not in text:
    raise SystemExit("g_imports / hand cutouts marker not found")
if "bool ToolbarWanted()" not in text:
    text = text.replace(needle, "std::map<const void *, vr::SharedTextureHandle_t> g_imports;\n" + fwd + "// Hand cutouts", 1)

# 6) ApplyScreenTransform helper near SetAbsolute
if "void ApplyScreenTransform" not in text:
    text = text.replace(
        "void SetAbsolute(Screen &s, const Mat &pose) {\n    s.anchor = AnchorMode::World;\n    s.pinned = kNone;\n    s.pose = pose;\n    vr::VROverlay()->SetOverlayTransformAbsolute(s.overlay, vr::TrackingUniverseStanding, &pose);\n    PlaceChrome(s);\n}",
        "void ApplyScreenTransform(Screen &s) {\n    Mat p;\n    if (!ScreenPose(s, &p)) return;\n    if (s.pinned != kNone)\n        vr::VROverlay()->SetOverlayTransformTrackedDeviceRelative(s.overlay, s.pinned, &s.pinRel);\n    else\n        vr::VROverlay()->SetOverlayTransformAbsolute(s.overlay, vr::TrackingUniverseStanding, &p);\n    PlaceChrome(s);\n}\n\nvoid SetAbsolute(Screen &s, const Mat &pose) {\n    SetWorldPose(s, pose);\n    ApplyScreenTransform(s);\n}",
        1,
    )

# 7) Include desktop_toolbar.inc before SteamInFront / near end of namespace — find a stable spot
# Insert before "// Steam in front" if present, else before extern "C" command section.
if '#include "desktop_toolbar.inc"' not in text:
    if "// Steam in front:" in text:
        text = text.replace("// Steam in front:", '#include "desktop_toolbar.inc"\n\n// Steam in front:', 1)
    else:
        # Fall back: before first "extern \"C\"" that has HandleCommand-ish — look for ControlCommand
        # Insert before UpdateSteamInFront's SteamInFront comment alternative: before `}  // extern "C"` of commands is too late
        # Find "bool SteamInFront" 
        if "bool SteamInFront()" in text:
            text = text.replace("bool SteamInFront()", '#include "desktop_toolbar.inc"\n\nbool SteamInFront()', 1)
        else:
            raise SystemExit("Could not find insertion point for desktop_toolbar.inc")

# 8) Command dispatch for toolbar/dock
old_unknown = """    } else {
        std::snprintf(reply, size, "error unknown command");
    }
}

}  // extern "C"
"""
new_unknown = """    } else if (std::strncmp(cmd, "toolbar ", 8) == 0 || !std::strcmp(cmd, "toolbar")) {
        ToolbarCommand(cmd + (std::strncmp(cmd, "toolbar ", 8) == 0 ? 8 : 7), reply, size);
    } else if (std::strncmp(cmd, "dock ", 5) == 0) {
        DockCommand(cmd + 5, reply, size);
    } else {
        std::snprintf(reply, size, "error unknown command");
    }
}

}  // extern "C"
"""
if "ToolbarCommand(" not in text:
    if old_unknown not in text:
        raise SystemExit("unknown-command trailer not found")
    text = text.replace(old_unknown, new_unknown, 1)

# 9) PickToolbarGaze at end of PickGazeTarget
if "PickToolbarGaze(" not in text.split("GazeTarget PickGazeTarget")[1][:5000]:
    # Insert before `return best;` of PickGazeTarget — find the function's return best
    idx = text.find("GazeTarget PickGazeTarget")
    if idx < 0:
        raise SystemExit("PickGazeTarget not found")
    # find "return best;\n}" after idx — first occurrence that closes the function
    sub = text[idx:]
    ret = sub.find("    return best;\n}")
    if ret < 0:
        raise SystemExit("PickGazeTarget return not found")
    text = text[: idx + ret] + "    PickToolbarGaze(ray, origin, &best);\n" + text[idx + ret :]

# 10) UpdateVisibility dock yield
old_vis = """        bool visible = s.shown && (shared || s.drag != Drag::None) && !s.alone;
        // A floating window's panel: while a window floats on it, its output is on, and the
        // window isn't minimized (and once it has a crop). alone/conceal stays for real screens.
        if (s.floating) visible = visible && s.floatOn && s.outputOn && !s.minimized && s.cropW > 0;
"""
new_vis = """        bool visible = s.shown && (shared || s.drag != Drag::None) && !s.alone;
        // A floating window's panel: while a window floats on it, its output is on, and the
        // window isn't minimized (and once it has a crop). alone/conceal stays for real screens.
        if (s.floating) visible = visible && s.floatOn && s.outputOn && !s.minimized && s.cropW > 0;
        // Docked screens are one group with the toolbar: they hide and return with it.
        if (s.docked && !ToolbarWanted()) visible = false;
"""
if "s.docked && !ToolbarWanted()" not in text:
    if old_vis not in text:
        raise SystemExit("UpdateVisibility block not found")
    text = text.replace(old_vis, new_vis, 1)

old_chrome_keep = """        if (!visible && shared && s.shown && !s.alone && s.controls > 0.02f &&
            (!s.floating || s.floatOn))
            visible = true, visFade = 0.f;
        if (yield && visible && !ScreenKeepsThroughDashboard(i, s)) {
"""
new_chrome_keep = """        if (!visible && shared && s.shown && !s.alone && s.controls > 0.02f &&
            (!s.floating || s.floatOn) && (!s.docked || ToolbarWanted()))
            visible = true, visFade = 0.f;
        if (yield && visible && !s.docked && !ScreenKeepsThroughDashboard(i, s)) {
"""
if "(!s.docked || ToolbarWanted())" not in text:
    if old_chrome_keep not in text:
        raise SystemExit("chrome keep visibility block not found")
    text = text.replace(old_chrome_keep, new_chrome_keep, 1)

# 11) StartDrag docked → toolbar
old_start = """void StartDrag(Screen &s, Drag mode, vr::TrackedDeviceIndex_t dev) {
    Mat d, p;
    if (dev == kNone || !DevicePose(dev, &d) || !ScreenPose(s, &p)) return;
"""
new_start = """void StartDrag(Screen &s, Drag mode, vr::TrackedDeviceIndex_t dev) {
    if (s.docked && mode == Drag::Move) {
        StartToolbarDrag(dev);
        return;
    }
    if (s.docked && mode == Drag::Roll) return;
    Mat d, p;
    if (dev == kNone || !DevicePose(dev, &d) || !ScreenPose(s, &p)) return;
"""
if "StartToolbarDrag(dev)" not in text:
    if old_start not in text:
        raise SystemExit("StartDrag head not found")
    text = text.replace(old_start, new_start, 1)

# 12) EndDragsBy → EndToolbarDragsBy
old_end = """void EndDragsBy(vr::TrackedDeviceIndex_t dev) {
    keyboard::EndDragBy(dev);
    for (auto &[index, s] : g_screens)
        if (s.drag != Drag::None && s.dragDevice == dev) FinishDrag(s, index);
    EndInstrumentDragsBy(dev);
}
"""
new_end = """void EndDragsBy(vr::TrackedDeviceIndex_t dev) {
    keyboard::EndDragBy(dev);
    for (auto &[index, s] : g_screens)
        if (s.drag != Drag::None && s.dragDevice == dev) FinishDrag(s, index);
    EndInstrumentDragsBy(dev);
    EndToolbarDragsBy(dev);
}
"""
if "EndToolbarDragsBy(dev)" not in text:
    if old_end not in text:
        raise SystemExit("EndDragsBy not found")
    text = text.replace(old_end, new_end, 1)

# 13) Gaze kind string cases — add Dock/Toolbar where Instrument case exists in switches
for pat in [
    (
        'case GazeKind::Instrument: kind = "instrument"; break;\n            default: break;',
        'case GazeKind::Instrument: kind = "instrument"; break;\n            case GazeKind::Dock: kind = "dock"; break;\n            case GazeKind::Toolbar: kind = "toolbar"; break;\n            default: break;',
    ),
    (
        'case GazeKind::Instrument: kind = "instrument"; break;\n                default: break;',
        'case GazeKind::Instrument: kind = "instrument"; break;\n                case GazeKind::Dock: kind = "dock"; break;\n                case GazeKind::Toolbar: kind = "toolbar"; break;\n                default: break;',
    ),
]:
    if pat[0] in text and "GazeKind::Toolbar: kind" not in text.split(pat[0])[0][-200:]:
        text = text.replace(pat[0], pat[1])

# Also printf gaze switches that list Instrument without default immediately
text = text.replace(
    'case GazeKind::Instrument: kind = "instrument"; break;\n        }',
    'case GazeKind::Instrument: kind = "instrument"; break;\n            case GazeKind::Dock: kind = "dock"; break;\n            case GazeKind::Toolbar: kind = "toolbar"; break;\n        }',
)

if text == orig:
    raise SystemExit("No changes made — unexpected")

VR.write_text(text, encoding="utf-8")
print(f"patched {VR} ({len(orig)} -> {len(text)} bytes)")
