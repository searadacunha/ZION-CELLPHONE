"""Minimal, locally validated ADB/Shizuku UI primitives for ZION OPERATOR.

No network, root, arbitrary shell fragments or credential storage. This is not
an AccessibilityService; UI inspection uses the on-device uiautomator binary.
"""
import re
import shlex

PACKAGE = re.compile(r"[A-Za-z]\w*(?:\.[A-Za-z]\w*)+")
FOCUS = re.compile(r"\b([A-Za-z]\w*(?:\.[A-Za-z]\w*)+)/[\w.$]+")
UI_ACTIONS = frozenset(("ui_tree", "ui_tap", "ui_swipe", "ui_text"))


def parse_foreground(output):
    """Extract a package from a current-activity dump; no match means fail closed."""
    for line in output.splitlines():
        if any(k in line for k in ("topResumedActivity", "mResumedActivity", "mCurrentFocus", "mFocusedApp")):
            match = FOCUS.search(line)
            if match:
                return match.group(1)
    return None


def validate_target(package, allowlist, foreground):
    """Only operate on an explicitly allowlisted app which is visibly foreground."""
    if not PACKAGE.fullmatch(package or ""):
        raise ValueError("ui action requires a valid package")
    if package not in allowlist:
        raise PermissionError("app is not in ui_allowed_packages")
    if foreground != package:
        raise PermissionError("foreground app does not match the requested package")


def _numbers(value, count):
    parts = value.split(",") if isinstance(value, str) else []
    if len(parts) != count or any(not p.isdecimal() for p in parts):
        raise ValueError(f"expected {count} comma-separated nonnegative integers")
    nums = tuple(int(p) for p in parts)
    if any(n > 8192 for n in nums[:4]):
        raise ValueError("coordinates exceed 8192 pixels")
    return nums


def build_command(action, args):
    """Return a fixed command with validated arguments. Never interpolate shell code."""
    if action == "ui_focus":
        return "dumpsys activity activities | grep -m1 -E 'topResumedActivity|mResumedActivity'"
    if action == "ui_home":
        return "input keyevent KEYCODE_HOME"
    if action == "ui_back":
        return "input keyevent KEYCODE_BACK"
    if action == "app_open":
        package = args.get("package", "")
        if not PACKAGE.fullmatch(package):
            raise ValueError("app_open requires an Android package")
        return f"monkey -p {shlex.quote(package)} -c android.intent.category.LAUNCHER 1"
    if action == "ui_tree":
        return ("umask 077; f=$(mktemp /data/local/tmp/zion-ui.XXXXXX) || exit 1; "
                "trap 'rm -f \"$f\"' EXIT; "
                "uiautomator dump \"$f\" >/dev/null && cat \"$f\"")
    if action == "ui_tap":
        x, y = _numbers(args.get("value", ""), 2)
        return f"input tap {x} {y}"
    if action == "ui_swipe":
        x1, y1, x2, y2, millis = _numbers(args.get("value", ""), 5)
        if not 50 <= millis <= 3000:
            raise ValueError("swipe duration must be 50..3000 ms")
        return f"input swipe {x1} {y1} {x2} {y2} {millis}"
    if action == "ui_text":
        raw = args.get("text", "")
        if not isinstance(raw, str) or not (1 <= len(raw) <= 200) or not all(32 <= ord(c) <= 126 for c in raw):
            raise ValueError("ui_text accepts only 1..200 printable ASCII characters; use a reviewed accessibility bridge for Unicode")
        return f"input text {shlex.quote(raw.replace(' ', '%s'))}"
    raise ValueError(f"unknown UI action: {action}")
