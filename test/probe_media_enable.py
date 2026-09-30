#!/usr/bin/env python3
"""Ask live ft-screens to enable/recenter the Media instrument."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "layout"))
import ft_layout  # noqa: E402


def main():
    sock = ft_layout.screens_socket()
    print("list:", sock.ask("instrument list"))
    print("enable:", sock.ask("instrument enable media"))
    print("recenter:", sock.ask("instrument recenter media"))
    print("list2:", sock.ask("instrument list"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
