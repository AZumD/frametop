# _start_desktop_after_spares_rebuild.sh

Smoke-test `ft-screens --spares` then start the Frametop desktop. Use when the
Frame binary already includes `--spares` (after a rebuild) but the desktop is
not running.

## Usage

```
bash test/_start_desktop_after_spares_rebuild.sh
```

If the binary lacks `--spares`, use `_fix_desktop_spares_mismatch.sh` instead.
