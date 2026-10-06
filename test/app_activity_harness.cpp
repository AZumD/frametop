// Compile-time + runtime checks for screens/app_activity.h (no OpenVR).
//   g++ -std=c++17 -I.. -o /tmp/app_activity_harness test/app_activity_harness.cpp && /tmp/app_activity_harness
#include "screens/app_activity.h"

#include <cstdio>
#include <cstdlib>

using frametop::AppActivity;
using frametop::AppActivityState;
using frametop::DecideAppActivity;
using frametop::kFlatLatchClearSamples;

static int fails = 0;

static void expect(const char *name, AppActivity got, AppActivity want) {
    if (got != want) {
        std::printf("FAIL %s: got %s want %s\n", name, frametop::AppActivityName(got),
                    frametop::AppActivityName(want));
        ++fails;
    }
}

static void expectBool(const char *name, bool got, bool want) {
    if (got != want) {
        std::printf("FAIL %s: got %d want %d\n", name, got ? 1 : 0, want ? 1 : 0);
        ++fails;
    }
}

int main() {
    AppActivityState st;

    expect("desktop idle", DecideAppActivity(false, false, false, false, &st), AppActivity::Desktop);
    expectBool("no latch idle", st.flatLatch, false);

    expect("vr scene", DecideAppActivity(true, false, false, false, &st), AppActivity::VrScene);

    st = {};
    expect("theater visible", DecideAppActivity(false, true, true, true, &st),
           AppActivity::FlatGamePresentation);
    expectBool("latch armed", st.flatLatch, true);

    // Enter gamepad mode: dashboard hides, desktopgame often hides, key remains.
    expect("gamepad latch", DecideAppActivity(false, false, true, false, &st),
           AppActivity::FlatGamePresentation);
    expectBool("latch held", st.flatLatch, true);

    // Leftover registered key without latch must not steal Desktop.
    AppActivityState leftover{};
    expect("leftover key", DecideAppActivity(false, false, true, false, &leftover),
           AppActivity::Desktop);

    // Release after confirmed dashboard-open without theater.
    st.flatLatch = true;
    st.dashClearTicks = 0;
    for (int i = 0; i < kFlatLatchClearSamples; ++i)
        DecideAppActivity(false, false, true, true, &st);
    expect("released on dash", DecideAppActivity(false, false, true, true, &st), AppActivity::Desktop);
    expectBool("latch cleared", st.flatLatch, false);

    // One glitchy dash sample while latched must not drop ownership immediately.
    st = {};
    st.flatLatch = true;
    expect("one dash glitch", DecideAppActivity(false, false, true, true, &st),
           AppActivity::FlatGamePresentation);
    expectBool("still latched after one", st.flatLatch, true);

    expectBool("hide vr", frametop::AppHidesDisplays(AppActivity::VrScene), true);
    expectBool("hide flat", frametop::AppHidesDisplays(AppActivity::FlatGamePresentation), true);
    expectBool("show desktop", frametop::AppHidesDisplays(AppActivity::Desktop), false);
    expectBool("block lasers gamepad",
               frametop::AppBlocksOutsideGamesLasers(AppActivity::FlatGamePresentation, false), true);
    expectBool("allow lasers theater+dash",
               frametop::AppBlocksOutsideGamesLasers(AppActivity::FlatGamePresentation, true), false);
    expectBool("allow lasers desktop", frametop::AppBlocksOutsideGamesLasers(AppActivity::Desktop, false),
               false);

    if (fails) {
        std::printf("%d failure(s)\n", fails);
        return 1;
    }
    std::printf("ok app_activity\n");
    return 0;
}
