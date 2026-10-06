// Does SteamVR hit-test a SetOverlayRaw overlay by its texture aspect or as a square?
// Creates two 1000x100 overlays, 0.5 m wide, 3 m below the floor, alpha 0 (invisible):
// "plain" (mouse scale left at default) and "scaled" (mouse scale = 1000x100). Then casts
// rays at 0.02 m (inside a 10:1 bar, height 0.05) and 0.15 m (outside it, inside a
// square) above each centre and prints which ones hit.
#include <openvr.h>

#include <chrono>
#include <cstdio>
#include <thread>
#include <vector>

static bool Hit(vr::VROverlayHandle_t h, float x, float y) {
    vr::VROverlayIntersectionParams_t p{};
    p.vSource = {x, y, 1.0f};
    p.vDirection = {0, 0, -1};
    p.eOrigin = vr::TrackingUniverseStanding;
    vr::VROverlayIntersectionResults_t r{};
    return vr::VROverlay()->ComputeOverlayIntersection(h, &p, &r);
}

int main() {
    vr::EVRInitError err = vr::VRInitError_None;
    vr::VR_Init(&err, vr::VRApplication_Overlay);
    if (err != vr::VRInitError_None) {
        std::printf("VR_Init failed: %s\n", vr::VR_GetVRInitErrorAsEnglishDescription(err));
        return 1;
    }
    std::vector<uint8_t> px(1000 * 100 * 4, 255);
    const char *names[] = {"plain", "scaled"};
    for (int k = 0; k < 2; ++k) {
        char key[64];
        std::snprintf(key, sizeof key, "frametop.test.aspect.%s", names[k]);
        vr::VROverlayHandle_t h = vr::k_ulOverlayHandleInvalid;
        if (vr::VROverlay()->CreateOverlay(key, key, &h) != vr::VROverlayError_None) {
            std::printf("%s: CreateOverlay failed\n", names[k]);
            continue;
        }
        vr::VROverlay()->SetOverlayRaw(h, px.data(), 1000, 100, 4);
        vr::VROverlay()->SetOverlayInputMethod(h, vr::VROverlayInputMethod_Mouse);
        if (k == 1) {
            vr::HmdVector2_t s = {{1000.f, 100.f}};
            vr::VROverlay()->SetOverlayMouseScale(h, &s);
        }
        vr::VROverlay()->SetOverlayWidthInMeters(h, 0.5f);
        const float cx = k * 2.0f, cy = -3.0f;
        vr::HmdMatrix34_t t = {{{1, 0, 0, cx}, {0, 1, 0, cy}, {0, 0, 1, 0}}};
        vr::VROverlay()->SetOverlayTransformAbsolute(h, vr::TrackingUniverseStanding, &t);
        // Hidden overlays never intersect; alpha 0 under the floor stays invisible.
        vr::VROverlay()->SetOverlayAlpha(h, 0.f);
        vr::VROverlay()->ShowOverlay(h);
        std::this_thread::sleep_for(std::chrono::milliseconds(500));
        uint32_t tw = 0, th = 0;
        vr::VROverlay()->GetOverlayTextureSize(h, &tw, &th);
        std::printf("%-6s tex=%ux%u  hit@+0.02=%d  hit@+0.15=%d  hit@-0.15=%d\n", names[k], tw, th,
                    Hit(h, cx, cy + 0.02f), Hit(h, cx, cy + 0.15f), Hit(h, cx, cy - 0.15f));
        vr::VROverlay()->DestroyOverlay(h);
    }
    vr::VR_Shutdown();
    return 0;
}
