#!/usr/bin/env bash
set -uo pipefail
cd /mnt/c/Users/Antho/Projects/frametop-customized-main || exit 1

echo "=== OnlyShowIn helpers in working ft_desktop.py ==="
grep -nE "def current_desktops|def shown_in|only_show_in|NotShowIn|KDE is always" layout/ft_desktop.py | head -30

echo
echo "=== list_applications decided/Hidden logic ==="
grep -nE "decided|Hidden|NoDisplay|shown_in|current_desktops" layout/ft_desktop.py | head -40

echo
echo "=== stage2 ft_desktop vs working (OnlyShowIn region) ==="
git show stage2-desktop-toolbar:layout/ft_desktop.py > /tmp/s2_desk.py
# Extract functions
python3 - <<'PY'
from pathlib import Path
def extract(path, names):
    text = Path(path).read_text(encoding='utf-8', errors='replace').splitlines()
    out = {}
    i = 0
    while i < len(text):
        line = text[i]
        for n in names:
            if line.startswith(f'def {n}('):
                start = i
                i += 1
                while i < len(text) and not (text[i].startswith('def ') and not text[i].startswith('def ' + n)):
                    if text[i].startswith('def ') and not text[i].startswith(f'def {n}('):
                        break
                    i += 1
                out[n] = '\n'.join(text[start:i])
                break
        else:
            i += 1
    return out
names = ['current_desktops','shown_in','parse_desktop_file','list_applications','desktop_actions']
s2 = extract('/tmp/s2_desk.py', names)
wt = extract('layout/ft_desktop.py', names)
for n in names:
    a, b = s2.get(n,''), wt.get(n,'')
    if a == b:
        print(f'{n}: IDENTICAL')
    elif not b:
        print(f'{n}: MISSING in working tree')
    elif not a:
        print(f'{n}: only in working tree')
    else:
        print(f'{n}: DIFFERS (s2={len(a)} wt={len(b)} chars)')
PY

echo
echo "=== ChromeStyle namespace in working vr.cpp? ==="
grep -n "namespace ChromeStyle" screens/vr.cpp || echo 'NO ChromeStyle namespace'
grep -n "kResizePad\|kResizeStroke\|kResizeCornerR\|kBarVisualHFrac\|kIdleR" screens/vr.cpp | head

echo
echo "=== LightHandle / lit corner in working? ==="
grep -n "LightHandle\|CornerTexture(" screens/vr.cpp | head -20

echo
echo "=== sync.sh post-rsync CR strip on stage2 ==="
git show stage2-desktop-toolbar:scripts/sync.sh | tail -40

echo
echo "=== working sync.sh tail ==="
tail -40 scripts/sync.sh

echo
echo "=== .gitattributes LF? ==="
cat .gitattributes 2>/dev/null || echo none
ls test/test_ft_layout_lf.py test/test_launcher_wrappers_lf.py 2>/dev/null || echo 'LF tests missing'
