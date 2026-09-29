// Buffer (DMA-BUF / OpenVR mouse) ↔ seat coordinate mapping for nested KWin.
//
// OpenVR SetOverlayMouseScale is the imported texture size (buffer pixels).
// The Wayland seat wants surface-local coordinates — but when KWin's *output*
// scale (e.g. 1.25) differs from the Wayland integer buffer_scale (often
// ceil(output_scale), e.g. 2), Qt uses output_scale as devicePixelRatio while
// wlr_surface.current is buffer/buffer_scale. Mapping only through surface size
// then misses the cursor. In that case send logical = buffer / output_scale.
//
// Prefer fractional-scale so surface tracks the output scale; the fallback below
// still corrects the common ceil(dpr) mismatch. VR metres are unrelated.
#pragma once

#ifdef __cplusplus
extern "C" {
#endif

static inline void ft_buffer_to_surface(double buf_x, double buf_y, int buf_w, int buf_h, int surf_w,
                                       int surf_h, double *surf_x, double *surf_y) {
    if (!surf_x || !surf_y) return;
    if (buf_w <= 0 || buf_h <= 0 || surf_w <= 0 || surf_h <= 0) {
        *surf_x = buf_x;
        *surf_y = buf_y;
        return;
    }
    *surf_x = buf_x * (double)surf_w / (double)buf_w;
    *surf_y = buf_y * (double)surf_h / (double)buf_h;
}

// Buffer pixels → seat coords for nested KWin (see file comment).
static inline void ft_buffer_to_seat(double buf_x, double buf_y, int buf_w, int buf_h, int surf_w,
                                    int surf_h, double output_scale, double *seat_x, double *seat_y) {
    if (!seat_x || !seat_y) return;
    const double scale = output_scale > 0.01 ? output_scale : 1.0;
    if (buf_w > 0 && surf_w > 0) {
        const double wayland_dpr = (double)buf_w / (double)surf_w;
        // Integer wl buffer_scale ahead of KWin output scale (e.g. 2 vs 1.25).
        if (scale > 1.01 && wayland_dpr > scale + 0.2) {
            *seat_x = buf_x / scale;
            *seat_y = buf_y / scale;
            return;
        }
    }
    ft_buffer_to_surface(buf_x, buf_y, buf_w, buf_h, surf_w, surf_h, seat_x, seat_y);
}

static inline void ft_uv_to_surface(double u, double v, int surf_w, int surf_h, double *surf_x,
                                   double *surf_y) {
    if (!surf_x || !surf_y) return;
    if (surf_w <= 0 || surf_h <= 0) {
        *surf_x = 0;
        *surf_y = 0;
        return;
    }
    *surf_x = u * (double)surf_w;
    *surf_y = v * (double)surf_h;
}

// UV → seat coords (same policy as ft_buffer_to_seat).
static inline void ft_uv_to_seat(double u, double v, int buf_w, int buf_h, int surf_w, int surf_h,
                                double output_scale, double *seat_x, double *seat_y) {
    if (!seat_x || !seat_y) return;
    if (buf_w <= 0 || buf_h <= 0) {
        ft_uv_to_surface(u, v, surf_w, surf_h, seat_x, seat_y);
        return;
    }
    ft_buffer_to_seat(u * (double)buf_w, v * (double)buf_h, buf_w, buf_h, surf_w, surf_h, output_scale,
                      seat_x, seat_y);
}

static inline void ft_buffer_to_uv(double buf_x, double buf_y, int buf_w, int buf_h, double *u,
                                  double *v) {
    if (!u || !v) return;
    if (buf_w <= 0 || buf_h <= 0) {
        *u = 0.5;
        *v = 0.5;
        return;
    }
    *u = buf_x / (double)buf_w;
    *v = buf_y / (double)buf_h;
}

#ifdef __cplusplus
}
#endif
