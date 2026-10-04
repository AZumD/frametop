#!/usr/bin/env python3
"""Probe @frametop_mpris reachability (host vs container)."""
import socket
import sys


def probe(label: str) -> int:
    cli = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    cli.settimeout(1.0)
    try:
        try:
            cli.bind("\0")
        except OSError as e:
            print(f"{label}: autobind failed: {e}", flush=True)
            return 2
        dest = "\0frametop_mpris"
        cli.sendto(b"state", dest)
        data, _ = cli.recvfrom(512)
        print(f"{label}: ok {data!r}", flush=True)
        return 0
    except Exception as e:
        print(f"{label}: fail {type(e).__name__}: {e}", flush=True)
        return 1
    finally:
        cli.close()


if __name__ == "__main__":
    raise SystemExit(probe(sys.argv[1] if len(sys.argv) > 1 else "probe"))
