#!/usr/bin/env python3
"""Phase 2: POINTER_IGNORE (overlays the pointer passes through).

  1. A Python mirror of ft-pointer.cpp's ParseIgnore / Ignored (comma-separated shell patterns,
     fnmatch without escapes) is checked against the examples in the docs.
  2. The C++ source is checked for the wiring: <fnmatch.h>, the "overlays" command, ignored
     keys skipped when handles are built, reload re-applying the list, every frametop.*
     overlay kept as a real panel.
  3. If g++ exists, ParseIgnore / Ignored are extracted from the source, compiled into a small
     program, and compared with the mirror on every case below (skipped otherwise).
  4. Frametop Input Settings' overlay_app / IGNORE_KEY (ft_input_settings.py, which needs
     PySide6 to import, so they're read from the source).

  python3 test/test_pointer_ignore.py
"""
from __future__ import annotations

import ast
import fnmatch
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CPP = os.path.join(ROOT, "pointer", "helper", "ft-pointer.cpp")
SETTINGS = os.path.join(ROOT, "input-settings", "ft_input_settings.py")
QML = os.path.join(ROOT, "input-settings", "main.qml")
CONF_EXAMPLE = os.path.join(ROOT, "session", "frametop.conf.example")

failures: list[str] = []


def check(label, ok, detail=""):
    print(("ok    " if ok else "FAIL  ") + label + ("" if ok or not detail else f": {detail}"), flush=True)
    if not ok:
        failures.append(label)


def parse_ignore(text: str) -> list[str]:
    """Mirror of ParseIgnore: split on commas, trim spaces and tabs, drop empty items."""
    return [item.strip(" \t") for item in text.split(",") if item.strip(" \t")]


def ignored(patterns: list[str], key: str) -> bool:
    """Mirror of Ignored: frametop.* is never ignored; else any fnmatch (FNM_NOESCAPE)."""
    if key.startswith("frametop."):
        return False
    return any(fnmatch.fnmatchcase(key, p) for p in patterns)


PARSE_CASES = [
    ("", []),
    (" ", []),
    (",", []),
    ("a", ["a"]),
    ("a,b", ["a", "b"]),
    (" a , b ,, c\t,", ["a", "b", "c"]),
    ("sasaken.frame-perf-overlay*, valve.steam.*", ["sasaken.frame-perf-overlay*", "valve.steam.*"]),
]

# (list, key, ignored)
MATCH_CASES = [
    ("", "sasaken.frame-perf-overlay", False),
    ("sasaken.frame-perf-overlay", "sasaken.frame-perf-overlay", True),
    ("sasaken.frame-perf-overlay", "sasaken.frame-perf-overlay.2", False),
    ("vendor.app*", "vendor.app", True),
    ("vendor.app*", "vendor.app.panel", True),
    ("vendor.app*", "vendor.apple", True),  # a "whole app" pattern is a prefix match, as documented
    ("vendor.app*", "other.vendor.app", False),
    ("vendor.app.*", "vendor.app", False),
    ("a.b, c.d*", "c.dee", True),
    ("a.b, c.d*", "a.bc", False),
    ("*.hud", "x.y.hud", True),
    ("v?ndor.app", "vendor.app", True),
    ("v?ndor.app", "vndor.app", False),
    ("vendor.[ab]pp", "vendor.app", True),
    ("vendor.[ab]pp", "vendor.cpp", False),
    ("vendor.app\\*", "vendor.app\\x", True),  # FNM_NOESCAPE: the backslash is an ordinary character
    ("vendor.app\\*", "vendor.app*", False),
    ("Vendor.App", "vendor.app", False),  # case-sensitive
    (",,,", "anything", False),
    # Hand-edited POINTER_IGNORE must not disable Frametop's own overlays.
    ("frametop.screen.1", "frametop.screen.1", False),
    ("frametop.*", "frametop.screen.1", False),
    ("frametop.*", "frametop.keyboard", False),
    ("*", "frametop.screen.1", False),
    ("*", "frametop.keyboard", False),
    ("*", "frametop.some-future-panel", False),
    ("*", "vendor.app.panel", True),
    ("vendor.app*", "vendor.app.panel", True),
]


def test_mirror():
    for text, want in PARSE_CASES:
        check(f"parse {text!r}", parse_ignore(text) == want, repr(parse_ignore(text)))
    for text, key, want in MATCH_CASES:
        check(f"match {text!r} vs {key!r}", ignored(parse_ignore(text), key) == want)


def test_source_wiring():
    with open(CPP, encoding="utf-8") as f:
        src = f.read()
    check("includes <fnmatch.h>", "#include <fnmatch.h>" in src)
    check("ParseIgnore defined", "std::vector<std::string> ParseIgnore(const std::string &list)" in src)
    check("Ignored uses fnmatch with FNM_NOESCAPE", "fnmatch(p.c_str(), key.c_str(), FNM_NOESCAPE) == 0" in src)
    ignored_fn = extract(src, "bool Ignored(")
    check("Ignored refuses frametop.* before fnmatch",
          'key.rfind("frametop.", 0) == 0' in ignored_fn
          and ignored_fn.index('key.rfind("frametop.", 0) == 0') < ignored_fn.index("fnmatch("))
    check("POINTER_IGNORE read in loadConfig",
          re.search(r'conf\.find\("POINTER_IGNORE"\)[\s\S]{0,120}ignore = ParseIgnore', src) is not None)
    check("overlays command answered through Request",
          re.search(r'strncmp\(buf, "overlays", 8\) == 0\)\s*\{\s*overlays\.Request\(sender, senderLen\)', src)
          is not None)
    check("ignored keys are skipped before FindOverlay",
          re.search(r'for \(const auto &key : overlays\.Keys\(\)\) \{\s*if \(Ignored\(ignore, key\)\) continue;\s*'
                    r'vr::VROverlayHandle_t h;', src) is not None)
    check("reload re-lists handles now (lastSlow reset)",
          re.search(r'loadConfig\(\);\s*lastSlow = Clock::now\(\) - std::chrono::seconds\(10\)', src) is not None)
    check("reload log counts ignored entries", "%zu ignored" in src and "ignore.size()" in src)
    check("overlay JSON reply built with JsonQuote", "JsonQuote(entries_[i].key)" in src and '"{\\"t\\":\\"overlays\\"' in src)
    check("OverlayList refreshes while paused on request", "if (!paused_ || requested_) Refresh();" in src)
    check("every frametop.* overlay is a real panel (not the scene-graph radius)",
          'key.rfind("frametop.", 0) != 0;' in src and 'key.rfind("frametop.screen.", 0) != 0' not in src)
    check("header documents POINTER_IGNORE and overlays", "POINTER_IGNORE (empty)" in src and "overlays (replies" in src)
    with open(CONF_EXAMPLE, encoding="utf-8") as f:
        check("frametop.conf.example lists POINTER_IGNORE", "POINTER_IGNORE=" in f.read())


def extract(src: str, start: str) -> str:
    """The brace-balanced definition that begins at `start`."""
    at = src.index(start)
    depth, i = 0, src.index("{", at)
    while True:
        depth += src[i] == "{"
        depth -= src[i] == "}"
        i += 1
        if depth == 0:
            return src[at:i]


def test_compiled_matches_mirror():
    cxx = shutil.which("g++") or shutil.which("clang++")
    if not cxx:
        print("skip  compiling the C++ functions (no g++/clang++ here)")
        return
    with open(CPP, encoding="utf-8") as f:
        src = f.read()
    funcs = (extract(src, "std::vector<std::string> ParseIgnore(")
             + "\n" + extract(src, "bool Ignored("))
    harness = f"""
#include <algorithm>
#include <fnmatch.h>
#include <iostream>
#include <string>
#include <vector>
{funcs}
int main() {{
    std::string list, key;
    while (std::getline(std::cin, list) && std::getline(std::cin, key)) {{
        const auto p = ParseIgnore(list);
        std::cout << p.size() << ' ' << (Ignored(p, key) ? 1 : 0) << '\\n';
    }}
}}
"""
    with tempfile.TemporaryDirectory() as td:
        cc, exe = os.path.join(td, "t.cpp"), os.path.join(td, "t")
        with open(cc, "w") as f:
            f.write(harness)
        build = subprocess.run([cxx, "-std=c++17", "-O1", cc, "-o", exe], capture_output=True, text=True)
        check("C++ ParseIgnore/Ignored compile", build.returncode == 0, build.stderr[-400:])
        if build.returncode:
            return
        cases = [(t, k, w) for t, k, w in MATCH_CASES] + [(t, "x", False) for t, _ in PARSE_CASES]
        stdin = "".join(f"{t}\n{k}\n" for t, k, _ in cases)
        out = subprocess.run([exe], input=stdin, capture_output=True, text=True).stdout.split("\n")
        for (t, k, want), line in zip(cases, out):
            n, hit = line.split()
            mine = parse_ignore(t)
            check(f"C++ == mirror for {t!r} vs {k!r}", int(n) == len(mine) and (hit == "1") == ignored(mine, k),
                  f"C++ {line!r}, mirror {len(mine)} {ignored(mine, k)}")


def test_settings_app():
    with open(SETTINGS, encoding="utf-8") as f:
        text = f.read()
    tree = ast.parse(text)
    ns: dict = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "overlay_app":
            exec(compile(ast.Module([node], []), SETTINGS, "exec"), ns)  # noqa: S102
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "IGNORE_KEY" for t in node.targets):
            exec(compile(ast.Module([node], []), SETTINGS, "exec"), ns)  # noqa: S102
    check("IGNORE_KEY is POINTER_IGNORE", ns.get("IGNORE_KEY") == "POINTER_IGNORE")
    app = ns["overlay_app"]
    check("overlay_app groups by the first two parts", app("sasaken.frame-perf-overlay.hud") == "sasaken.frame-perf-overlay")
    check("overlay_app of an app key is itself", app("vendor.app") == "vendor.app")
    check("overlay_app of a bare name", app("system") == "system")
    check("the app pattern covers its panels (what setAppIgnored writes)",
          ignored(parse_ignore(app("vendor.app.panel") + "*"), "vendor.app.panel2"))
    for needle in ("def setAppIgnored", "def setPanelIgnored", "def removeIgnore", "def refreshPanels",
                   "def panelGroups", "def ignoreOrphans", 'startswith("frametop.")',
                   'self._send("overlays", HELPER)', 'self._send("reload", HELPER)'):
        check(f"settings backend has {needle}", needle in text)
    check("settings backend lists uinput for devices", '"uinput": n.get("uinput", False)' in text)
    check("keyboard_toggle labelled", '"keyboard_toggle": "Open/close keyboard"' in text)
    with open(QML, encoding="utf-8") as f:
        qml = f.read()
    check("QML: Ignored panels page and drawer entry", "id: ignorePage" in qml and 'text: "Ignored panels"' in qml)
    check("QML: Keyboard page and drawer entry", "id: keyboardPage" in qml and 'text: "Keyboard"' in qml)
    check("QML: keyboard page skips uinput keyboards", "!d.uinput" in qml)
    check("QML: FT_INPUT_PAGE knows ignore and keyboard",
          "keyboard: keyboardPage" in qml and "ignore: ignorePage" in qml)


def main():
    test_mirror()
    test_source_wiring()
    test_compiled_matches_mirror()
    test_settings_app()
    if failures:
        print(f"{len(failures)} failure(s): {failures}", file=sys.stderr)
        return 1
    print("all pointer-ignore checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
