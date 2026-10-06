# TEST_FT_LAYOUT_LF

Script: `test/test_ft_layout_lf.py`

## Purpose

Assert that `layout/ft-layout` is LF-only. A CRLF shebang makes SteamOS report
`No such file or directory` when `frametop-session.sh` runs `ft-layout`.

## Usage

```
python3 test/test_ft_layout_lf.py
```
