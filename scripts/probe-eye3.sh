#!/bin/bash
grep -r -i eyetrack /opt/steamvr/drivers 2>/dev/null | head -40
echo '---'
ls /opt/steamvr/drivers 2>/dev/null
echo '---'
find /opt/steamvr -iname '*frame*' 2>/dev/null | head -50
echo '---'
find /opt/steamvr -iname '*eye*' 2>/dev/null | head -40
