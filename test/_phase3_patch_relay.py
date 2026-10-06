#!/usr/bin/env python3
"""Wire Meta+Shift+F float_toggle into input-relay without importing gaze."""
from pathlib import Path

path = Path("/mnt/c/Users/Antho/Projects/frametop-customized-main/input/input-relay.py")
t = path.read_text(encoding="utf-8")
orig = t

# Docstring mention near float_toggle description
if "Meta+Shift+F" not in t:
    old = ("float_toggle = float the\n"
           "desktop window under the pointer (else the active one) in VR or dock it if it floats, dock_all =\n")
    # Check actual wording
    if "float_toggle = float the" not in t:
        raise SystemExit("doc float_toggle line missing")

# Insert DEFAULT_KEY_BINDINGS after FLOAT_ACTIONS
if "DEFAULT_KEY_BINDINGS" not in t:
    needle = (
        'FLOAT = "\\0frametop_float"  # ft-floatd; floating windows in the Frametop desktop\n'
        "# Actions for ft-floatd: work even when pointer mode is off.\n"
        'FLOAT_ACTIONS = {"float_toggle": b"float pointer", "dock_all": b"dock all"}\n'
    )
    insert = (
        'FLOAT = "\\0frametop_float"  # ft-floatd; floating windows in the Frametop desktop\n'
        "# Actions for ft-floatd: work even when pointer mode is off.\n"
        'FLOAT_ACTIONS = {"float_toggle": b"float pointer", "dock_all": b"dock all"}\n'
        "# Key combinations a rules file without \"key_bindings\" gets. Meta+Shift+F floats/docks\n"
        "# a window (free on the Frametop desktop; apps rarely use Meta+Shift+F).\n"
        'DEFAULT_KEY_BINDINGS = {"42+125+33": "float_toggle"}  # Shift+Meta+F\n'
        "KEY_F24 = 194  # sent to the desktop with a Meta combination (see key_binding)\n"
        "# Key combinations (\"key_bindings\"): modifiers, each side's code folded into the left one's.\n"
        "MODIFIERS = {29: 29, 97: 29, 42: 42, 54: 42, 56: 56, 100: 56, 125: 125, 126: 125}\n"
        "\n"
        "\n"
        "def known_action(a):\n"
        "    return a in ACTIONS\n"
        "\n"
        "\n"
        "def needs_pointer(a):\n"
        "    return a not in FLOAT_ACTIONS\n"
    )
    if needle not in t:
        raise SystemExit("FLOAT_ACTIONS block not found")
    t = t.replace(needle, insert, 1)

# read_rules: setdefault key_bindings
old_rules = '''def read_rules(path=RULES_PATH):
    """{"devices": {id: {"role", "name"}}, "buttons": {id: {"<code>": action}},
    "controller_buttons": {"<hand>/<button>": action}, "controller_in_games": bool,
    "vr_keyboard": one of VR_KEYBOARD_MODES, "vr_keyboard_persist": bool}."""
    try:
        with open(path) as f:
            rules = json.load(f)
    except (OSError, ValueError):
        rules = {}
    rules.setdefault("devices", {})
    rules.setdefault("buttons", {})
    rules.setdefault("controller_buttons", {})
    return rules
'''
new_rules = '''def read_rules(path=RULES_PATH):
    """{"devices": {id: {"role", "name"}}, "buttons": {id: {"<code>": action}},
    "controller_buttons": {"<hand>/<button>": action}, "controller_in_games": bool,
    "key_bindings": {"<code>+<code>...": action},
    "vr_keyboard": one of VR_KEYBOARD_MODES, "vr_keyboard_persist": bool}.

    A rules file without "key_bindings" gets DEFAULT_KEY_BINDINGS (Meta+Shift+F:
    float_toggle); one with its own list, even an empty one, does not.
    """
    try:
        with open(path) as f:
            rules = json.load(f)
    except (OSError, ValueError):
        rules = {}
    rules.setdefault("devices", {})
    rules.setdefault("buttons", {})
    rules.setdefault("controller_buttons", {})
    if not isinstance(rules.get("key_bindings"), dict):
        rules["key_bindings"] = dict(DEFAULT_KEY_BINDINGS)
    return rules
'''
if 'rules["key_bindings"] = dict(DEFAULT_KEY_BINDINGS)' not in t:
    if old_rules not in t:
        raise SystemExit("read_rules not found exact")
    t = t.replace(old_rules, new_rules, 1)

# key_binding handler + state, inserted before screens_down
if "def key_binding(" not in t:
    marker = "    screens_down = set()  # keys the desktop was told went down and not yet up (see reconcile_desktop_keys)"
    kb = '''    held_modifiers = set()  # on any keyboard, folded (MODIFIERS)
    held_meta = set()  # the Meta keys held, as they are (KEY_LEFTMETA, KEY_RIGHTMETA)
    meta_hidden = set()  # held Meta keys the desktop was told came up (a combination; key_binding)
    combos_down = {}  # key code -> the action its combination started (released with it)

    def key_binding(code, value, now):
        """A key from a keyboard: does it complete a key combination ("key_bindings")?

        True if it was taken for one (then it isn't typed).
        """
        nonlocal meta_down
        if code in MODIFIERS:
            (held_modifiers.add if value else held_modifiers.discard)(MODIFIERS[code])
            if code in (KEY_LEFTMETA, KEY_RIGHTMETA):
                (held_meta.add if value else held_meta.discard)(code)
                if value == 0 and code in meta_hidden:
                    meta_hidden.discard(code)
                    return True  # the desktop already had it come up (below)
            return False
        if value == 1 and code not in combos_down and meta_hidden:
            # Another key while Meta is still held after a combination: the desktop gets Meta
            # back first, so Meta+that key still works there.
            for c in sorted(meta_hidden):
                to_screens(c, 1)
            meta_hidden.clear()
        if value == 0 and code in combos_down:
            action = combos_down.pop(code)
            if state["pointer"] or not needs_pointer(action):
                do_action(action, 0, now)
            return True
        if value != 1 or not state["rules"]["key_bindings"]:
            return value == 2 and code in combos_down
        combo = "+".join(str(c) for c in sorted(held_modifiers) + [code])
        action = state["rules"]["key_bindings"].get(combo)
        if not known_action(action) or action in ("key", "none"):
            return False
        combos_down[code] = action
        if held_meta - meta_hidden:
            # The desktop saw Meta go down. Swallow it there now so Plasma's launcher and
            # Meta+mouse window move/resize don't fire; the real Meta release is dropped above.
            meta_down = False
            to_screens(KEY_F24, 1)
            to_screens(KEY_F24, 0)
            for c in sorted(held_meta - meta_hidden):
                to_screens(c, 0)
            meta_hidden.update(held_meta)
        if state["pointer"] or not needs_pointer(action):
            do_action(action, 1, now)
        log(f"key combination {combo}: {action}")
        return True

'''
    # Note: key_binding references to_screens before it is defined. Upstream has the same
    # order — key_binding is a nested function and to_screens is defined immediately after,
    # so by call time to_screens exists. But wait — in upstream, to_screens is AFTER
    # key_binding definition. Nested functions look up names at call time, so OK.
    if marker not in t:
        raise SystemExit("screens_down marker missing")
    t = t.replace(marker, kb + marker, 1)

# Call site in passthrough path
old_pt = '''                if node.role != "pointer":
                    # Observed only, unless typing goes to the desktop. With META_DASHBOARD=1,
                    # a Meta tap on any keyboard toggles the dashboard.
                    if node.role == "passthrough" and etype == EV_KEY:
                        to_screens(code, value)
'''
new_pt = '''                if node.role != "pointer":
                    # Observed only, unless typing goes to the desktop. With META_DASHBOARD=1,
                    # a Meta tap on any keyboard toggles the dashboard.
                    if node.role == "passthrough" and etype == EV_KEY and code < BTN_MISC and key_binding(code, value, now):
                        continue
                    if node.role == "passthrough" and etype == EV_KEY:
                        to_screens(code, value)
'''
if "key_binding(code, value, now)" not in t:
    if old_pt not in t:
        raise SystemExit("passthrough EV_KEY block not found")
    t = t.replace(old_pt, new_pt, 1)

# Also handle key_binding for pointer-role keyboard keys that would otherwise type.
# Upstream does NOT — stick to upstream call site only.

# Module docstring: mention key_bindings briefly near float lines
old_doc = (
    "slots via ft-layout, keyboard_toggle = open or close Frametop's keyboard, float_toggle = float the\n"
    "desktop window under the pointer (else the active one) in VR or dock it if it floats, dock_all =\n"
)
# Find actual text
idx = t.find("float_toggle = float the")
print("float_toggle doc @", idx)
print(repr(t[idx - 80 : idx + 200]))

if t == orig:
    raise SystemExit("no changes")
path.write_text(t, encoding="utf-8")
print("patched relay")
print("DEFAULT_KEY_BINDINGS", "DEFAULT_KEY_BINDINGS" in t)
print("key_binding def", t.count("def key_binding"))
print("Meta+Shift float", "42+125+33" in t)
