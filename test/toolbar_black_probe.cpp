// Read-only autopsy for Frametop's desktop toolbar overlays.
//
// Finds the live toolbar overlays owned by ft-screens and reports compositor-visible state
// plus the actual RGBA image SteamVR says is attached to each overlay. This is intentionally
// a separate OpenVR client so it can inspect a broken toolbar without restarting Frametop.

#include <openvr.h>

#include <algorithm>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

namespace {

void Report(vr::IVROverlay *ov, const std::string &key) {
    vr::VROverlayHandle_t h = vr::k_ulOverlayHandleInvalid;
    auto err = ov->FindOverlay(key.c_str(), &h);
    if (err != vr::VROverlayError_None) return;

    bool vis = ov->IsOverlayVisible(h);
    float alpha = -1.f, red = -1.f, green = -1.f, blue = -1.f, width = -1.f;
    uint32_t sort = 0;
    vr::HmdVector2_t mouse{};
    vr::VRTextureBounds_t bounds{};
    vr::VROverlayInputMethod input = vr::VROverlayInputMethod_None;
    vr::VROverlayTransformType transformType = vr::VROverlayTransform_Invalid;
    ov->GetOverlayAlpha(h, &alpha);
    ov->GetOverlayColor(h, &red, &green, &blue);
    ov->GetOverlayWidthInMeters(h, &width);
    ov->GetOverlaySortOrder(h, &sort);
    ov->GetOverlayMouseScale(h, &mouse);
    ov->GetOverlayTextureBounds(h, &bounds);
    ov->GetOverlayInputMethod(h, &input);
    ov->GetOverlayTransformType(h, &transformType);

    double x = 0, y = 0, z = 0;
    if (transformType == vr::VROverlayTransform_Absolute) {
        vr::TrackingUniverseOrigin origin{};
        vr::HmdMatrix34_t m{};
        if (ov->GetOverlayTransformAbsolute(h, &origin, &m) == vr::VROverlayError_None)
            x = m.m[0][3], y = m.m[1][3], z = m.m[2][3];
    }

    uint32_t iw = 0, ih = 0;
    auto imageErr = ov->GetOverlayImageData(h, nullptr, 0, &iw, &ih);
    std::string image;
    if (imageErr == vr::VROverlayError_ArrayTooSmall && iw && ih &&
        uint64_t(iw) * ih <= 16ULL * 1024 * 1024) {
        std::vector<unsigned char> px(size_t(iw) * ih * 4);
        imageErr = ov->GetOverlayImageData(h, px.data(), uint32_t(px.size()), &iw, &ih);
        if (imageErr == vr::VROverlayError_None) {
            uint64_t nonzeroA = 0, opaque = 0, rgbEnergy = 0, alphaSum = 0;
            unsigned minA = 255, maxA = 0;
            for (size_t i = 0; i + 3 < px.size(); i += 4) {
                const unsigned a = px[i + 3];
                alphaSum += a;
                minA = std::min(minA, a);
                maxA = std::max(maxA, a);
                if (a) ++nonzeroA;
                if (a >= 250) ++opaque;
                rgbEnergy += px[i] + px[i + 1] + px[i + 2];
            }
            const uint64_t pixels = uint64_t(iw) * ih;
            char buf[256];
            std::snprintf(buf, sizeof buf,
                          "%ux%u nzA=%llu/%llu opaque=%llu a=%u..%u meanA=%.1f rgb=%llu",
                          iw, ih,
                          static_cast<unsigned long long>(nonzeroA),
                          static_cast<unsigned long long>(pixels),
                          static_cast<unsigned long long>(opaque),
                          minA, maxA,
                          pixels ? double(alphaSum) / pixels : 0.0,
                          static_cast<unsigned long long>(rgbEnergy));
            image = buf;
        }
    }
    if (image.empty()) {
        image = std::string("imageErr=") + ov->GetOverlayErrorNameFromEnum(imageErr) +
                " dims=" + std::to_string(iw) + "x" + std::to_string(ih);
    }

    std::printf(
        "%-30s h=%llu vis=%d alpha=%.3f color=%.2f,%.2f,%.2f sort=%u "
        "width=%.4f mouse=%.0fx%.0f uv=%.2f,%.2f..%.2f,%.2f input=%d "
        "type=%d pos=%.3f,%.3f,%.3f  %s\n",
        key.c_str(), static_cast<unsigned long long>(h), vis ? 1 : 0, alpha,
        red, green, blue, sort, width, mouse.v[0], mouse.v[1],
        bounds.uMin, bounds.vMin, bounds.uMax, bounds.vMax, int(input), int(transformType),
        x, y, z, image.c_str());
}

}  // namespace

int main() {
    vr::EVRInitError init = vr::VRInitError_None;
    vr::VR_Init(&init, vr::VRApplication_Background);
    if (init != vr::VRInitError_None) {
        std::fprintf(stderr, "background init failed: %s\n",
                     vr::VR_GetVRInitErrorAsEnglishDescription(init));
        return 2;
    }
    vr::VR_Shutdown();

    init = vr::VRInitError_None;
    vr::VR_Init(&init, vr::VRApplication_Overlay);
    if (init != vr::VRInitError_None) {
        std::fprintf(stderr, "overlay init failed: %s\n",
                     vr::VR_GetVRInitErrorAsEnglishDescription(init));
        return 3;
    }

    auto *ov = vr::VROverlay();
    if (!ov) {
        vr::VR_Shutdown();
        return 4;
    }

    Report(ov, "frametop.toolbar.backing");
    Report(ov, "frametop.toolbar.grab");
    Report(ov, "frametop.toolbar.popup");
    Report(ov, "frametop.toolbar.popup.hl");

    char key[96];
    for (int m = 0; m < 16; ++m)
        for (int c = 0; c < 32; ++c) {
            std::snprintf(key, sizeof key, "frametop.toolbar.m%d.c%d", m, c);
            Report(ov, key);
        }

    vr::VR_Shutdown();
    return 0;
}
