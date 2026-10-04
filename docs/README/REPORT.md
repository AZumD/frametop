# REPORT

Script: `scripts/report.sh`

## Purpose

Collect a Frametop bug-report bundle on the Frame: OS/SteamVR versions, service states, settings, and recent logs. Bluetooth addresses and the headset serial are masked.

## Usage

From a Frametop checkout on the Frame, or from a PC over SSH (uses `scripts/_env.sh`):

```
scripts/report.sh
```

Writes `frametop-report-<date>.txt` in the repo root. Attach it to an issue at https://github.com/AZumD/frametop/issues.

## Related

[OVERVIEW.md](OVERVIEW.md), README “Reporting problems”.
