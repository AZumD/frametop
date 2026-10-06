// Locate optional SteamVR runtime assets on the Frame. Never vendored into the repo.
// PNG icons can be loaded; SVG paths are reported for future use but not decoded here.
#pragma once

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// Root of the SteamVR install (default /opt/steamvr), or empty if unknown.
const char *ft_steamvr_root(void);

// Resolve a dashboard icon basename (e.g. "svr_settings.svg") under
// resources/webinterface/dashboard/images/icons/. Returns a static path or NULL.
const char *ft_steamvr_icon_path(const char *basename);

// Load a PNG from the SteamVR tree into tightly packed RGBA (caller frees with free()).
// Returns NULL on missing file / decode failure (SVG is not decoded — returns NULL).
uint8_t *ft_steamvr_load_rgba(const char *path, int *out_w, int *out_h);

#ifdef __cplusplus
}
#endif
