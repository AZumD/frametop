#!/usr/bin/env python3
"""Wire handcut into screens/vr.cpp for Phase 3C (no pointer gestures)."""
from pathlib import Path

path = Path("/mnt/c/Users/Antho/Projects/frametop-customized-main/screens/vr.cpp")
t = path.read_text(encoding="utf-8")
orig = t

def must_replace(old: str, new: str, label: str):
    global t
    if old not in t:
        raise SystemExit(f"missing block for {label}")
    if t.count(old) != 1:
        raise SystemExit(f"expected 1 occurrence for {label}, got {t.count(old)}")
    t = t.replace(old, new, 1)
    print("ok", label)

# 1) file header note
must_replace(
    "//   - the catcher: a button pressed on a screen is released in KWin even when the laser\n",
    "//   - hand cutouts (handcut.cpp): where ft-hands (hands/) tracks a hand between an eye and a\n"
    "//     screen, that eye sees through the screen (to Room View). Only then is the screen\n"
    "//     drawn by us into a side-by-side buffer; otherwise its client buffer is shown as is.\n"
    "//     Floating windows skip cutouts (texture-bounds crops). Tracking is opt-in (ft-handsctl).\n"
    "//   - the catcher: a button pressed on a screen is released in KWin even when the laser\n",
    "header",
)

# 2) include
must_replace(
    '#include "keyboard.h"\n',
    '#include "handcut.h"\n#include "keyboard.h"\n',
    "include",
)

# 3) Screen fields after shown/visible
must_replace(
    "    const void *shown = nullptr;  // a frame arrived\n"
    "    bool visible = false;         // shown in VR right now\n"
    "    bool alone = false;           // concealed: kept off the headset (windows stay on the screen)\n",
    "    const void *shown = nullptr;  // a frame arrived\n"
    "    bool visible = false;         // shown in VR right now\n"
    "    const void *key = nullptr;    // the client buffer on it now, and its dmabuf (for cutouts)\n"
    "    ft_dmabuf buf{};\n"
    "    vr::SharedTextureHandle_t plain = 0;  // that buffer's SteamVR import\n"
    "    bool cutting = false;         // showing a cutout buffer (side by side) instead\n"
    "    bool alone = false;           // concealed: kept off the headset (windows stay on the screen)\n",
    "screen-fields",
)

# 4) globals after g_imports
must_replace(
    "std::map<const void *, vr::SharedTextureHandle_t> g_imports;\n",
    "std::map<const void *, vr::SharedTextureHandle_t> g_imports;\n"
    "\n"
    "// Hand cutouts (optional; inert until ft-hands publishes /run/user/UID/frametop-hands/hands).\n"
    "bool g_cutouts = true;          // the cutouts command turns them off\n"
    "handcut::Hands g_hands;\n"
    "handcut::Renderer g_cutter;\n"
    "int g_cutterState = 0;          // 0 not tried, 1 ready, -1 unavailable\n"
    "std::map<const void *, vr::SharedTextureHandle_t> g_cutImports;\n",
    "globals",
)

# 5) Insert cutout helpers before UpdateCatcher (which exists in ours)
helpers = r'''
void SetScreenTexture(const Screen &s, vr::SharedTextureHandle_t handle) {
    vr::Texture_t tex = {&handle, vr::TextureType_SharedTextureHandle, vr::ColorSpace_Gamma};
    vr::VROverlay()->SetOverlayTexture(s.overlay, &tex);
}

bool CutterReady() {
    if (g_cutterState) return g_cutterState > 0;
    uint64_t mods[64];
    const int n = ft_vr_modifiers(DRM_FORMAT_ABGR8888, mods, 64);
    const bool ok = g_cutter.Init(std::vector<uint64_t>(mods, mods + n), [](const handcut::Output *o) {
        auto it = g_cutImports.find(o);
        if (it == g_cutImports.end()) return;
        vr::VRIPCResourceManager()->UnrefResource(it->second);
        g_cutImports.erase(it);
    });
    g_cutterState = ok ? 1 : -1;
    std::printf(ok ? "hand cutouts ready\n" : "hand cutouts unavailable (see above)\n");
    return ok;
}

vr::SharedTextureHandle_t ImportCutout(const handcut::Output *o) {
    auto it = g_cutImports.find(o);
    if (it != g_cutImports.end()) return it->second;
    vr::DmabufAttributes_t a{};
    a.unWidth = uint32_t(o->buf.width);
    a.unHeight = uint32_t(o->buf.height);
    a.unDepth = a.unMipLevels = a.unArrayLayers = a.unSampleCount = 1;
    a.unFormat = o->buf.format;
    a.ulModifier = o->buf.modifier;
    a.unPlaneCount = uint32_t(o->buf.n_planes);
    for (int i = 0; i < o->buf.n_planes && i < int(vr::MaxDmabufPlaneCount); ++i) {
        a.plane[i].unOffset = o->buf.offset[i];
        a.plane[i].unStride = o->buf.stride[i];
        a.plane[i].nFd = o->buf.fd[i];
    }
    vr::SharedTextureHandle_t h = 0;
    if (!vr::VRIPCResourceManager()->ImportDmabuf(vr::VRApplication_Overlay, &a, &h)) {
        std::fprintf(stderr, "openvr: ImportDmabuf failed for a cutout buffer\n");
        h = 0;
    }
    g_cutImports.emplace(o, h);
    return h;
}

void StopCutting(Screen &s) {
    if (!s.cutting) return;
    vr::VROverlay()->SetOverlayFlag(s.overlay, vr::VROverlayFlags_SideBySide_Parallel, false);
    vr::VROverlay()->SetOverlayFlag(s.overlay, vr::VROverlayFlags_IgnoreTextureAlpha, true);
    if (s.plain) SetScreenTexture(s, s.plain);
    s.cutting = false;
}

// Floating windows don't get cutouts yet: their panel and popups show crops of the client
// buffer (texture bounds), which a side-by-side buffer doesn't match.
void UpdateCutouts() {
    Mat head;
    const bool haveHead = DevicePose(vr::k_unTrackedDeviceIndex_Hmd, &head);
    const bool hands = g_cutouts && haveHead &&
                       g_hands.Update(head, std::chrono::duration_cast<std::chrono::nanoseconds>(
                                                Clock::now().time_since_epoch()).count());
    double eyes[2][3];
    if (hands) handcut::EyePositions(head, eyes);
    for (auto &[i, s] : g_screens) {
        std::vector<handcut::Capsule2D> spots[2];
        Mat p;
        bool cut = hands && s.visible && !s.floating && s.key && s.width > 0 && ScreenPose(s, &p) &&
                   handcut::Project({p, s.metres, s.heightMetres(), s.curve, s.width, s.height}, g_hands.capsules(),
                                    eyes, spots);
        const handcut::Output *out = cut && CutterReady() ? g_cutter.Composite(i, s.key, s.buf, spots) : nullptr;
        const vr::SharedTextureHandle_t h = out ? ImportCutout(out) : 0;
        if (!h) {
            StopCutting(s);
            continue;
        }
        if (!s.cutting) {
            vr::VROverlay()->SetOverlayFlag(s.overlay, vr::VROverlayFlags_IgnoreTextureAlpha, false);
            vr::VROverlay()->SetOverlayFlag(s.overlay, vr::VROverlayFlags_SideBySide_Parallel, true);
            s.cutting = true;
        }
        SetScreenTexture(s, h);
    }
}

'''

must_replace("void UpdateCatcher() {\n", helpers + "void UpdateCatcher() {\n", "helpers")

# 6) present path
must_replace(
    "    vr::SharedTextureHandle_t handle = it->second;\n"
    "    vr::Texture_t tex = {&handle, vr::TextureType_SharedTextureHandle, vr::ColorSpace_Gamma};\n"
    "    vr::VROverlay()->SetOverlayTexture(s.overlay, &tex);\n"
    "    for (const auto &[k, sub] : s.subs) vr::VROverlay()->SetOverlayTexture(sub.overlay, &tex);\n"
    "    s.shown = key;  // UpdateVisibility shows it on the next tick\n"
    "    return true;\n"
    "}\n",
    "    s.key = key, s.buf = *b, s.plain = it->second;\n"
    "    // While cutting, the next tick draws the new buffer with the cutouts (never floating).\n"
    "    if (!s.cutting) SetScreenTexture(s, it->second);\n"
    "    vr::SharedTextureHandle_t handle = it->second;\n"
    "    vr::Texture_t tex = {&handle, vr::TextureType_SharedTextureHandle, vr::ColorSpace_Gamma};\n"
    "    for (const auto &[k, sub] : s.subs) vr::VROverlay()->SetOverlayTexture(sub.overlay, &tex);\n"
    "    s.shown = key;  // UpdateVisibility shows it on the next tick\n"
    "    return true;\n"
    "}\n",
    "present",
)

# 7) forget
must_replace(
    "void ft_vr_forget(const void *key) {\n"
    "    if (!g_vr) return;\n"
    "    auto it = g_imports.find(key);\n"
    "    if (it == g_imports.end()) return;\n"
    "    vr::VRIPCResourceManager()->UnrefResource(it->second);\n"
    "    g_imports.erase(it);\n"
    "}\n",
    "void ft_vr_forget(const void *key) {\n"
    "    if (!g_vr) return;\n"
    "    if (g_cutterState == 1) g_cutter.Forget(key);\n"
    "    for (auto &[i, s] : g_screens)\n"
    "        if (s.key == key) s.key = nullptr;\n"
    "    auto it = g_imports.find(key);\n"
    "    if (it == g_imports.end()) return;\n"
    "    vr::VRIPCResourceManager()->UnrefResource(it->second);\n"
    "    g_imports.erase(it);\n"
    "}\n",
    "forget",
)

# 8) poll: UpdateCutouts before UpdateCatcher
must_replace(
    "    UpdateCatcher();\n",
    "    UpdateCutouts();\n"
    "    UpdateCatcher();\n",
    "poll",
)

# 9) destroy screen: DropPanel
must_replace(
    "void ft_vr_screen_destroy(int index) {\n"
    "    auto it = g_screens.find(index);\n"
    "    if (it == g_screens.end()) return;\n"
    "    for (auto &[k, sub] : it->second.subs) vr::VROverlay()->DestroyOverlay(sub.overlay);\n"
    "    for (auto o : it->second.All())\n"
    "        if (o != vr::k_ulOverlayHandleInvalid) vr::VROverlay()->DestroyOverlay(o);\n"
    "    g_screens.erase(it);\n"
    "}\n",
    "void ft_vr_screen_destroy(int index) {\n"
    "    auto it = g_screens.find(index);\n"
    "    if (it == g_screens.end()) return;\n"
    "    if (g_cutterState == 1) g_cutter.DropPanel(index);\n"
    "    for (auto &[k, sub] : it->second.subs) vr::VROverlay()->DestroyOverlay(sub.overlay);\n"
    "    for (auto o : it->second.All())\n"
    "        if (o != vr::k_ulOverlayHandleInvalid) vr::VROverlay()->DestroyOverlay(o);\n"
    "    g_screens.erase(it);\n"
    "}\n",
    "destroy",
)

# 10) cutouts command after controllers
must_replace(
    '    } else if (std::sscanf(cmd, "controllers %15s", word) == 1) {\n'
    "        const std::string m = word;\n"
    "        if (m == \"always\") g_lasers = Lasers::Always;\n"
    "        else if (m == \"outside_games\") g_lasers = Lasers::OutsideGames;\n"
    "        else if (m == \"dashboard\") g_lasers = Lasers::Dashboard;\n"
    '        else return (void)std::snprintf(reply, size, "error modes: always outside_games dashboard");\n'
    "        UpdateLasers();\n"
    '        std::snprintf(reply, size, "ok %s", LasersName());\n'
    "    } else if (std::strncmp(cmd, \"state\", 5) == 0) {\n",
    '    } else if (std::sscanf(cmd, "controllers %15s", word) == 1) {\n'
    "        const std::string m = word;\n"
    "        if (m == \"always\") g_lasers = Lasers::Always;\n"
    "        else if (m == \"outside_games\") g_lasers = Lasers::OutsideGames;\n"
    "        else if (m == \"dashboard\") g_lasers = Lasers::Dashboard;\n"
    '        else return (void)std::snprintf(reply, size, "error modes: always outside_games dashboard");\n'
    "        UpdateLasers();\n"
    '        std::snprintf(reply, size, "ok %s", LasersName());\n'
    '    } else if (std::sscanf(cmd, "cutouts %15s", word) == 1) {\n'
    '        char arg[16] = "";\n'
    "        double ms = 0;\n"
    "        if (!std::strcmp(word, \"on\")) g_cutouts = true;\n"
    "        else if (!std::strcmp(word, \"off\")) g_cutouts = false;\n"
    '        else if (!std::strcmp(word, "predict") && std::sscanf(cmd, "cutouts predict %15s", arg) == 1 &&\n'
    '                 (!std::strcmp(arg, "on") || !std::strcmp(arg, "off")))\n'
    '            g_hands.SetPrediction(!std::strcmp(arg, "on"), g_hands.leadMs());\n'
    '        else if (!std::strcmp(word, "lead") && std::sscanf(cmd, "cutouts lead %lf", &ms) == 1)\n'
    "            g_hands.SetPrediction(g_hands.predicting(), ms);\n"
    '        else if (std::strcmp(word, "state") != 0)\n'
    '            return (void)std::snprintf(reply, size, "error cutouts on|off|state|predict on|off|lead <ms>");\n'
    '        std::snprintf(reply, size, "ok %s predict %s lead %.0f ms cutter %d", g_cutouts ? "on" : "off",\n'
    '                      g_hands.predicting() ? "on" : "off", g_hands.leadMs(), g_cutterState);\n'
    "    } else if (std::strncmp(cmd, \"state\", 5) == 0) {\n",
    "cutouts-cmd",
)

# 11) shutdown: unref cut imports
must_replace(
    "        if (auto *ipc = vr::VRIPCResourceManager()) {\n"
    "            for (auto &[k, h] : g_imports) ipc->UnrefResource(h);\n"
    "        }\n"
    "        keyboard::Destroy();\n",
    "        if (auto *ipc = vr::VRIPCResourceManager()) {\n"
    "            for (auto &[k, h] : g_imports) ipc->UnrefResource(h);\n"
    "            for (auto &[k, h] : g_cutImports) ipc->UnrefResource(h);\n"
    "        }\n"
    "        g_cutImports.clear();\n"
    "        keyboard::Destroy();\n",
    "shutdown",
)

if t == orig:
    raise SystemExit("no changes?")
path.write_text(t, encoding="utf-8")
print("wrote", path, "delta", len(t) - len(orig))
