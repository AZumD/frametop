# TEST_LAUNCHER_WRAPPERS_LF

Script: `test/test_launcher_wrappers_lf.py`

## Purpose

Assert that launcher/session wrappers (`ft-layout`, `ft-display-settings`, …) are
LF-only so Windows CRLF checkouts do not break shebang exec on the Frame.

## Usage

```
python3 test/test_launcher_wrappers_lf.py
```
