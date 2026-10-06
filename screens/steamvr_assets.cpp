// SteamVR runtime asset resolver (Stage 2). Fail soft; never crash on missing files.
#include "steamvr_assets.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

// Implementation lives in vr.cpp (STB_IMAGE_IMPLEMENTATION once per binary).
#include "stb_image.h"

namespace {

const char *EnvOr(const char *key, const char *fallback) {
    const char *v = std::getenv(key);
    return (v && v[0]) ? v : fallback;
}

bool FileReadable(const char *path) {
    if (!path || !path[0]) return false;
    FILE *f = std::fopen(path, "rb");
    if (!f) return false;
    std::fclose(f);
    return true;
}

std::string &RootBuf() {
    static std::string root;
    return root;
}

}  // namespace

const char *ft_steamvr_root(void) {
    std::string &root = RootBuf();
    if (!root.empty()) return root.c_str();
    const char *candidates[] = {
        EnvOr("STEAMVR_PATH", nullptr),
        EnvOr("VR_OVERRIDE", nullptr),
        "/opt/steamvr",
        "/usr/local/steamvr",
    };
    for (const char *c : candidates) {
        if (!c) continue;
        std::string try_root = c;
        // VR_OVERRIDE sometimes points at a bin dir; accept either.
        std::string probe = try_root + "/resources/webinterface/dashboard";
        if (FileReadable((probe + "/systemui.html").c_str()) ||
            FileReadable((try_root + "/systemui.html").c_str())) {
            root = try_root;
            return root.c_str();
        }
        if (FileReadable((try_root + "/resources/webinterface/dashboard/systemui.html").c_str())) {
            root = try_root;
            return root.c_str();
        }
    }
    root = "/opt/steamvr";  // best-effort default; callers still check FileReadable
    return root.c_str();
}

const char *ft_steamvr_icon_path(const char *basename) {
    if (!basename || !basename[0]) return nullptr;
    if (std::strchr(basename, '/') || std::strstr(basename, "..")) return nullptr;
    static thread_local char path[512];
    std::snprintf(path, sizeof path, "%s/resources/webinterface/dashboard/images/icons/%s", ft_steamvr_root(),
                  basename);
    if (!FileReadable(path)) return nullptr;
    return path;
}

uint8_t *ft_steamvr_load_rgba(const char *path, int *out_w, int *out_h) {
    if (out_w) *out_w = 0;
    if (out_h) *out_h = 0;
    if (!path || !FileReadable(path)) return nullptr;
    // Only decode PNG; SVG needs a rasterizer we do not ship.
    const char *dot = std::strrchr(path, '.');
    if (!dot || (std::strcmp(dot, ".png") != 0 && std::strcmp(dot, ".PNG") != 0)) return nullptr;
    int w = 0, h = 0, n = 0;
    stbi_uc *img = stbi_load(path, &w, &h, &n, 4);
    if (!img || w <= 0 || h <= 0) {
        if (img) stbi_image_free(img);
        return nullptr;
    }
    if (out_w) *out_w = w;
    if (out_h) *out_h = h;
    return img;  // stbi_load uses malloc; free() is correct
}
