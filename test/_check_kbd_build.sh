#!/usr/bin/env bash
set -euo pipefail
bin=~/dev/frametop/screens/build/ft-screens
ls -la "$bin"
echo "=== keyboard strings ==="
strings "$bin" | grep -E 'vrkeyboard|frametop.keyboard' | head || echo NONE
echo "=== relay unit ExecStart ==="
grep ExecStart ~/.config/systemd/user/frametop-input-relay.service
