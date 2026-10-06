// Pure SteamVR app-activity decision for ft-screens (no OpenVR types).
//
// Visibility and OutsideGames laser ownership must share one higher-level state.
// Flatscreen / gamescope panels are valve.steam.desktopgame[.N] overlays — not scene
// apps. Entering Valve's "Enter gamepad mode" calls hideDashboard and typically hides
// that overlay for a sample or longer; a latch keeps FlatGamePresentation while the
// dashboard stays closed and the desktopgame key remains registered. Leftover hidden
// keys after a real exit do not latch (latch only arms when the overlay was visible).
#pragma once

#include <cstddef>
#include <cstdint>
#include <cstring>

namespace frametop {

enum class AppActivity : uint8_t {
    Desktop = 0,
    VrScene = 1,
    FlatGamePresentation = 2,
};

struct AppActivityState {
    bool flatLatch = false;
    int dashClearTicks = 0;  // consecutive samples: dashboard open, theater not visible
};

inline bool IsDesktopgameOverlayKey(const char *key) {
    if (!key) return false;
    constexpr char prefix[] = "valve.steam.desktopgame";
    constexpr std::size_t prefixLen = sizeof(prefix) - 1;
    const std::size_t len = std::strlen(key);
    if (len < prefixLen || std::strncmp(key, prefix, prefixLen) != 0) return false;
    return len == prefixLen || key[prefixLen] == '.';
}

inline const char *AppActivityName(AppActivity a) {
    switch (a) {
        case AppActivity::VrScene: return "vr_scene";
        case AppActivity::FlatGamePresentation: return "flat_game";
        default: return "desktop";
    }
}

// How many UpdateGame samples (≈0.5 s each) of "dashboard open without a visible
// desktopgame" are required before releasing a flat-game latch. Steam's Enter gamepad
// mode can keep this transition state for more than a second, so hold for ~3 seconds.
// Leftover hidden keys still do not arm a latch on their own.
constexpr int kFlatLatchClearSamples = 6;

// sceneApp: GetCurrentSceneProcessId() != 0
// flatVisible / flatRegistered: valve.steam.desktopgame[.N] FindOverlay + IsOverlayVisible
// dashboardVisible: IsDashboardVisible()
inline AppActivity DecideAppActivity(bool sceneApp, bool flatVisible, bool flatRegistered,
                                     bool dashboardVisible, AppActivityState *st) {
    if (sceneApp) {
        if (!flatRegistered) {
            st->flatLatch = false;
            st->dashClearTicks = 0;
        }
        return AppActivity::VrScene;
    }
    if (flatVisible) {
        st->flatLatch = true;
        st->dashClearTicks = 0;
        return AppActivity::FlatGamePresentation;
    }
    if (!flatRegistered) {
        st->flatLatch = false;
        st->dashClearTicks = 0;
        return AppActivity::Desktop;
    }
    // Registered but not visible: hold ownership only while latched and the dashboard
    // is closed (Steam's Enter gamepad mode path).
    if (st->flatLatch && !dashboardVisible) {
        st->dashClearTicks = 0;
        return AppActivity::FlatGamePresentation;
    }
    if (dashboardVisible) {
        if (++st->dashClearTicks >= kFlatLatchClearSamples) {
            st->flatLatch = false;
            st->dashClearTicks = 0;
        }
    } else {
        st->dashClearTicks = 0;
    }
    return st->flatLatch ? AppActivity::FlatGamePresentation : AppActivity::Desktop;
}

inline bool AppHidesDisplays(AppActivity a) { return a != AppActivity::Desktop; }

// OutsideGames lasers: VR scenes always own controllers. Flat presentation owns them
// only while the dashboard is closed (Enter gamepad mode / diminished). With the
// theater panel up and the dashboard open, Frametop may keep OutsideGames lasers so
// spatial desktop multitasking still works beside the game frame.
inline bool AppBlocksOutsideGamesLasers(AppActivity a, bool dashboardVisible) {
    switch (a) {
        case AppActivity::VrScene: return true;
        case AppActivity::FlatGamePresentation: return !dashboardVisible;
        default: return false;
    }
}

}  // namespace frametop
