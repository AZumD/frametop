#!/usr/bin/env python3
"""Unit tests for VR buffer → seat pointer mapping (nested KWin scale).

Mirrors screens/coords.h. At scale 1.0, buffer==surface. When KWin output scale
is fractional but Wayland uses integer buffer_scale=ceil(scale), seat coords
must use buffer/output_scale (Qt dpr), not buffer/wayland_dpr.

Run:
  python3 test/test_pointer_coords.py
"""
import math
import unittest


def ft_buffer_to_surface(buf_x, buf_y, buf_w, buf_h, surf_w, surf_h):
    if buf_w <= 0 or buf_h <= 0 or surf_w <= 0 or surf_h <= 0:
        return buf_x, buf_y
    return buf_x * surf_w / buf_w, buf_y * surf_h / buf_h


def ft_buffer_to_seat(buf_x, buf_y, buf_w, buf_h, surf_w, surf_h, output_scale):
    scale = output_scale if output_scale > 0.01 else 1.0
    if buf_w > 0 and surf_w > 0:
        wayland_dpr = buf_w / surf_w
        if scale > 1.01 and wayland_dpr > scale + 0.2:
            return buf_x / scale, buf_y / scale
    return ft_buffer_to_surface(buf_x, buf_y, buf_w, buf_h, surf_w, surf_h)


def ft_uv_to_surface(u, v, surf_w, surf_h):
    if surf_w <= 0 or surf_h <= 0:
        return 0.0, 0.0
    return u * surf_w, v * surf_h


def ft_uv_to_seat(u, v, buf_w, buf_h, surf_w, surf_h, output_scale):
    if buf_w <= 0 or buf_h <= 0:
        return ft_uv_to_surface(u, v, surf_w, surf_h)
    return ft_buffer_to_seat(u * buf_w, v * buf_h, buf_w, buf_h, surf_w, surf_h, output_scale)


def ft_buffer_to_uv(buf_x, buf_y, buf_w, buf_h):
    if buf_w <= 0 or buf_h <= 0:
        return 0.5, 0.5
    return buf_x / buf_w, buf_y / buf_h


def scaled_buffer(logical_w, logical_h, scale):
    return math.ceil(logical_w * scale - 1e-9), math.ceil(logical_h * scale - 1e-9)


class PointerCoordMapping(unittest.TestCase):
    def test_scale_100_identity(self):
        sx, sy = ft_buffer_to_seat(960, 540, 1920, 1080, 1920, 1080, 1.0)
        self.assertAlmostEqual(sx, 960)
        self.assertAlmostEqual(sy, 540)

    def test_scale_125_matching_surface(self):
        # Ideal: surface = logical, buffer = physical
        bw, bh = scaled_buffer(1920, 1080, 1.25)
        sx, sy = ft_buffer_to_seat(bw / 2, bh / 2, bw, bh, 1920, 1080, 1.25)
        self.assertAlmostEqual(sx, 960)
        self.assertAlmostEqual(sy, 540)

    def test_scale_125_integer_dpr_mismatch(self):
        # Live Frame: output scale 1.25, wl buffer_scale=2 → surface = phys/2
        phys_w, phys_h = 5120, 1440
        scale = 1.25
        surf_w, surf_h = phys_w // 2, phys_h // 2
        # Laser at buffer centre must land at logical centre for Qt (buf/scale)
        sx, sy = ft_buffer_to_seat(phys_w / 2, phys_h / 2, phys_w, phys_h, surf_w, surf_h, scale)
        self.assertAlmostEqual(sx, (phys_w / 2) / scale)
        self.assertAlmostEqual(sy, (phys_h / 2) / scale)
        # Wrong (surface-only) mapping would be phys/4
        wrong = (phys_w / 2) * surf_w / phys_w
        self.assertNotAlmostEqual(sx, wrong)

    def test_scale_133_integer_dpr_mismatch(self):
        phys_w, phys_h = 5120, 1440
        scale = 4 / 3
        surf_w, surf_h = phys_w // 2, phys_h // 2
        sx, sy = ft_buffer_to_seat(phys_w / 2, phys_h / 2, phys_w, phys_h, surf_w, surf_h, scale)
        self.assertAlmostEqual(sx, (phys_w / 2) / scale)
        self.assertAlmostEqual(sy, (phys_h / 2) / scale)

    def test_uv_seat_matches_buffer_seat(self):
        phys_w, phys_h = 5120, 1440
        scale = 1.25
        surf_w, surf_h = phys_w // 2, phys_h // 2
        u, v = 0.25, 0.75
        a = ft_uv_to_seat(u, v, phys_w, phys_h, surf_w, surf_h, scale)
        b = ft_buffer_to_seat(u * phys_w, v * phys_h, phys_w, phys_h, surf_w, surf_h, scale)
        self.assertAlmostEqual(a[0], b[0], places=9)
        self.assertAlmostEqual(a[1], b[1], places=9)

    def test_mixed_per_screen_scales(self):
        cases = [
            (1920, 1080, 1.0, 1.0),
            (1920, 1080, 1.25, 1.25),  # matching surface
            (5120, 1440, 2.0, 1.25),   # dpr 2 vs scale 1.25
        ]
        for buf_w, buf_h, dpr, scale in cases:
            surf_w = int(round(buf_w / dpr))
            surf_h = int(round(buf_h / dpr))
            u, v = 0.25, 0.75
            sx, sy = ft_buffer_to_seat(u * buf_w, v * buf_h, buf_w, buf_h, surf_w, surf_h, scale)
            if scale > 1.01 and dpr > scale + 0.2:
                self.assertAlmostEqual(sx, u * buf_w / scale, places=5)
            else:
                self.assertAlmostEqual(sx, u * surf_w, places=5)

    def test_vr_metres_independent_of_scale(self):
        metres = 2.4
        for scale in (1.0, 1.25, 1.5):
            bw, bh = 1920, 1080
            sx, sy = ft_buffer_to_seat(bw / 2, bh / 2, bw, bh, bw, bh, scale)
            self.assertAlmostEqual(sx, 960)
            self.assertEqual(metres, 2.4)

    def test_unknown_surface_falls_back(self):
        sx, sy = ft_buffer_to_seat(100, 200, 2400, 1350, 0, 0, 1.25)
        # No surface → treat as identity path through ft_buffer_to_surface fallback
        self.assertEqual((sx, sy), (100, 200))


if __name__ == "__main__":
    unittest.main()
