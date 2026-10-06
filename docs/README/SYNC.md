# SYNC

Script: `scripts/sync.sh`

## Purpose

One-way sync of this repo from a PC to `~/dev/frametop` on the Steam Frame (`rsync --delete`). On the Frame itself it is a no-op.

## Notes

After rsync, shell scripts and extensionless wrappers (`*.sh`, `frametop-session.sh`, `run.sh`, `ft-layout`, `ft-handsctl`, `ft-display-settings`, `ft-input-settings`) on the Frame are stripped of CR (`\r`) so a Windows checkout with CRLF does not break bash (`set -o pipefail\r`) or shebang exec (`/bin/bash^M` → bad interpreter). Prefer LF (see `.gitattributes`). Broken `ft-layout` boots one ultrawide screen with no instruments; broken `ft-display-settings` makes Display Settings fail to launch from the menu.

## Usage

```
scripts/sync.sh
scripts/sync.sh --dry-run
```
