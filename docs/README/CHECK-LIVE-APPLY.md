# CHECK-LIVE-APPLY

Script: `scripts/check-live-apply.py`

## Purpose

Live Frame helper: push visibility / wrist / gesture / controllers / scales from `~/.config/frametop-layout.json` to `@ft_screens` and print instrument/head replies. Defaults match `layout/ft_layout.py` (`controllers` → `outside_games`).

## Usage

On the Frame (or inside the nested session where `@ft_screens` is reachable):

```
python3 scripts/check-live-apply.py
```

## Related

[FT_LAYOUT.md](FT_LAYOUT.md).
