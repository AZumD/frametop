#!/usr/bin/env python3
"""Read/write SteamVR settings via IVRSettings_003 (libopenvr_api.so).

Usage:
  openvr_settings.py get-string steamvr background
  openvr_settings.py get-int steamvr environmentMode
  openvr_settings.py get-float steamvr backgroundCameraHeight
  openvr_settings.py get-bool steamvr backgroundUseDomeProjection
  openvr_settings.py set-string steamvr background /path/to.png
  openvr_settings.py set-int steamvr environmentMode 0
  openvr_settings.py set-float steamvr backgroundDomeRadius 20
  openvr_settings.py set-bool steamvr backgroundUseDomeProjection false
"""
from __future__ import annotations

import ctypes
import sys

LIB = "/opt/steamvr/bin/linuxarm64/libopenvr_api.so"
IVRSETTINGS = b"IVRSettings_003"
VRApplication_Utility = 4
VRApplication_Background = 3

EVRInitError = ctypes.c_int32
EVRSettingsError = ctypes.c_int32


class OpenVR:
    def __init__(self) -> None:
        self.so = ctypes.CDLL(LIB)
        self.so.VR_InitInternal2.argtypes = [
            ctypes.POINTER(EVRInitError),
            ctypes.c_int32,
            ctypes.c_char_p,
        ]
        self.so.VR_InitInternal2.restype = ctypes.c_uint32
        self.so.VR_GetGenericInterface.argtypes = [
            ctypes.c_char_p,
            ctypes.POINTER(EVRInitError),
        ]
        self.so.VR_GetGenericInterface.restype = ctypes.c_void_p
        self.so.VR_ShutdownInternal.argtypes = []

        err = EVRInitError(0)
        token = self.so.VR_InitInternal2(ctypes.byref(err), VRApplication_Utility, None)
        if err.value != 0:
            err = EVRInitError(0)
            token = self.so.VR_InitInternal2(
                ctypes.byref(err), VRApplication_Background, None
            )
        if err.value != 0:
            raise RuntimeError(f"VR_Init failed: {err.value}")

        err = EVRInitError(0)
        self.iface = self.so.VR_GetGenericInterface(IVRSETTINGS, ctypes.byref(err))
        if not self.iface or err.value != 0:
            self.so.VR_ShutdownInternal()
            raise RuntimeError(f"IVRSettings failed: {err.value}")

        # C++ vtable: first pointer of object
        self.vtable = ctypes.cast(
            ctypes.c_void_p(self.iface), ctypes.POINTER(ctypes.c_void_p)
        ).contents
        # Actually iface IS the object pointer; vtable is at *[iface]
        obj = ctypes.cast(self.iface, ctypes.POINTER(ctypes.c_void_p))
        vt_ptr = obj[0]
        self.vt = ctypes.cast(vt_ptr, ctypes.POINTER(ctypes.c_void_p))

    def close(self) -> None:
        self.so.VR_ShutdownInternal()

    def _fn(self, index: int, restype, argtypes):
        f = ctypes.CFUNCTYPE(restype, *argtypes)(self.vt[index])
        return f

    def error_name(self, code: int) -> str:
        f = self._fn(
            0,
            ctypes.c_char_p,
            [ctypes.c_void_p, ctypes.c_int32],
        )
        name = f(self.iface, code)
        return name.decode() if name else str(code)

    def set_string(self, section: str, key: str, value: str) -> None:
        err = EVRSettingsError(0)
        f = self._fn(
            4,
            None,
            [
                ctypes.c_void_p,
                ctypes.c_char_p,
                ctypes.c_char_p,
                ctypes.c_char_p,
                ctypes.POINTER(EVRSettingsError),
            ],
        )
        f(
            self.iface,
            section.encode(),
            key.encode(),
            value.encode(),
            ctypes.byref(err),
        )
        if err.value:
            raise RuntimeError(f"SetString: {self.error_name(err.value)} ({err.value})")

    def get_string(self, section: str, key: str) -> str:
        err = EVRSettingsError(0)
        buf = ctypes.create_string_buffer(4096)
        f = self._fn(
            8,
            None,
            [
                ctypes.c_void_p,
                ctypes.c_char_p,
                ctypes.c_char_p,
                ctypes.c_char_p,
                ctypes.c_uint32,
                ctypes.POINTER(EVRSettingsError),
            ],
        )
        f(
            self.iface,
            section.encode(),
            key.encode(),
            buf,
            ctypes.sizeof(buf),
            ctypes.byref(err),
        )
        if err.value:
            raise RuntimeError(f"GetString: {self.error_name(err.value)} ({err.value})")
        return buf.value.decode()

    def set_int(self, section: str, key: str, value: int) -> None:
        err = EVRSettingsError(0)
        f = self._fn(
            2,
            None,
            [
                ctypes.c_void_p,
                ctypes.c_char_p,
                ctypes.c_char_p,
                ctypes.c_int32,
                ctypes.POINTER(EVRSettingsError),
            ],
        )
        f(self.iface, section.encode(), key.encode(), int(value), ctypes.byref(err))
        if err.value:
            raise RuntimeError(f"SetInt32: {self.error_name(err.value)} ({err.value})")

    def get_int(self, section: str, key: str) -> int:
        err = EVRSettingsError(0)
        f = self._fn(
            6,
            ctypes.c_int32,
            [
                ctypes.c_void_p,
                ctypes.c_char_p,
                ctypes.c_char_p,
                ctypes.POINTER(EVRSettingsError),
            ],
        )
        v = f(self.iface, section.encode(), key.encode(), ctypes.byref(err))
        if err.value:
            raise RuntimeError(f"GetInt32: {self.error_name(err.value)} ({err.value})")
        return int(v)

    def set_float(self, section: str, key: str, value: float) -> None:
        err = EVRSettingsError(0)
        f = self._fn(
            3,
            None,
            [
                ctypes.c_void_p,
                ctypes.c_char_p,
                ctypes.c_char_p,
                ctypes.c_float,
                ctypes.POINTER(EVRSettingsError),
            ],
        )
        f(self.iface, section.encode(), key.encode(), float(value), ctypes.byref(err))
        if err.value:
            raise RuntimeError(f"SetFloat: {self.error_name(err.value)} ({err.value})")

    def get_float(self, section: str, key: str) -> float:
        err = EVRSettingsError(0)
        f = self._fn(
            7,
            ctypes.c_float,
            [
                ctypes.c_void_p,
                ctypes.c_char_p,
                ctypes.c_char_p,
                ctypes.POINTER(EVRSettingsError),
            ],
        )
        v = f(self.iface, section.encode(), key.encode(), ctypes.byref(err))
        if err.value:
            raise RuntimeError(f"GetFloat: {self.error_name(err.value)} ({err.value})")
        return float(v)

    def set_bool(self, section: str, key: str, value: bool) -> None:
        err = EVRSettingsError(0)
        f = self._fn(
            1,
            None,
            [
                ctypes.c_void_p,
                ctypes.c_char_p,
                ctypes.c_char_p,
                ctypes.c_bool,
                ctypes.POINTER(EVRSettingsError),
            ],
        )
        f(self.iface, section.encode(), key.encode(), bool(value), ctypes.byref(err))
        if err.value:
            raise RuntimeError(f"SetBool: {self.error_name(err.value)} ({err.value})")

    def get_bool(self, section: str, key: str) -> bool:
        err = EVRSettingsError(0)
        f = self._fn(
            5,
            ctypes.c_bool,
            [
                ctypes.c_void_p,
                ctypes.c_char_p,
                ctypes.c_char_p,
                ctypes.POINTER(EVRSettingsError),
            ],
        )
        v = f(self.iface, section.encode(), key.encode(), ctypes.byref(err))
        if err.value:
            raise RuntimeError(f"GetBool: {self.error_name(err.value)} ({err.value})")
        return bool(v)


def usage() -> None:
    print(__doc__.strip(), file=sys.stderr)
    sys.exit(2)


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        usage()
    op, section, key = argv[1], argv[2], argv[3]
    vr = OpenVR()
    try:
        if op == "get-string":
            print(vr.get_string(section, key))
        elif op == "get-int":
            print(vr.get_int(section, key))
        elif op == "get-float":
            print(vr.get_float(section, key))
        elif op == "get-bool":
            print("true" if vr.get_bool(section, key) else "false")
        elif op == "set-string":
            if len(argv) < 5:
                usage()
            vr.set_string(section, key, argv[4])
            print("ok", vr.get_string(section, key))
        elif op == "set-int":
            if len(argv) < 5:
                usage()
            vr.set_int(section, key, int(argv[4]))
            print("ok", vr.get_int(section, key))
        elif op == "set-float":
            if len(argv) < 5:
                usage()
            vr.set_float(section, key, float(argv[4]))
            print("ok", vr.get_float(section, key))
        elif op == "set-bool":
            if len(argv) < 5:
                usage()
            val = argv[4].lower() in ("1", "true", "yes", "on")
            vr.set_bool(section, key, val)
            print("ok", "true" if vr.get_bool(section, key) else "false")
        else:
            usage()
    finally:
        vr.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
