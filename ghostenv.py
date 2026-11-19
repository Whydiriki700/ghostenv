#!/usr/bin/env python3
"""ghostenv: hunt the environment variables your code uses in secret.

Scans Python, JavaScript, TypeScript, and shell sources for environment
variable reads, then compares them with your .env.example. Variables the
code uses but nobody documented are ghosts: they surface at deploy time,
at midnight, as a crash. Variables documented but never used are stale.
Zero dependencies. Python 3.8+. Values are never read, only names.
"""

import argparse
import json
import os
import re
import sys

NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,}$")
PY_PATTERNS = [
    re.compile(r"""os\.environ\[["']([A-Za-z_][A-Za-z0-9_]*)["']\]"""),
    re.compile(r"""os\.environ\.get\(["']([A-Za-z_][A-Za-z0-9_]*)["']"""),
    re.compile(r"""os\.environ\.setdefault\(["']([A-Za-z_][A-Za-z0-9_]*)["']"""),
    re.compile(r"""os\.getenv\(["']([A-Za-z_][A-Za-z0-9_]*)["']"""),
    re.compile(r"""(?<![\w.])environ\[["']([A-Za-z_][A-Za-z0-9_]*)["']\]"""),
    re.compile(r"""(?<![\w.])getenv\(["']([A-Za-z_][A-Za-z0-9_]*)["']"""),
]
JS_PATTERNS = [
    re.compile(r"process\.env\.([A-Za-z_$][A-Za-z0-9_$]*)"),
    re.compile(r"""process\.env\[["']([A-Za-z_][A-Za-z0-9_]*)["']\]"""),
]
SH_PATTERN = re.compile(r"\$\{?([A-Z][A-Z0-9_]{2,})\}?")
SH_BUILTINS = {
    "PATH", "HOME", "USER", "PWD", "SHELL", "TERM", "LANG", "HOSTNAME",
    "UID", "EUID", "PPID", "RANDOM", "IFS", "OSTYPE", "BASH", "ZSH",
    "LINENO", "SECONDS", "REPLY", "OPTIND", "SHLVL", "LOGNAME", "DISPLAY",
}
PATTERNS_BY_EXT = {
    ".py": PY_PATTERNS,
    ".js": JS_PATTERNS, ".ts": JS_PATTERNS, ".jsx": JS_PATTERNS,
    ".tsx": JS_PATTERNS, ".mjs": JS_PATTERNS, ".cjs": JS_PATTERNS,
}
EXAMPLE_NAMES = [".env.example", ".env.sample", ".env.template", ".env.dist"]
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}


def valid(name):
    return bool(NAME_RE.match(name))


def scan_file(path):
    ext = os.path.splitext(path)[1].lower()
    found = set()
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return found
    if ext in (".sh", ".bash"):
        for name in SH_PATTERN.findall(text):
            if valid(name) and name not in SH_BUILTINS:
                found.add(name)
        return found
    for pattern in PATTERNS_BY_EXT.get(ext, []):
        for name in pattern.findall(text):
            if valid(name):
                found.add(name)
    return found


def parse_env_names(path):
    names = set()
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[len("export "):]
                name = line.split("=", 1)[0].strip()
                if valid(name):
                    names.add(name)
    except OSError:
        pass
    return names


def analyze(root):
    root = os.path.abspath(root)
    used = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            for var in scan_file(path):
                used.setdefault(var, []).append(os.path.relpath(path, root))
    documented = set()
    for candidate in EXAMPLE_NAMES:
        documented |= parse_env_names(os.path.join(root, candidate))
    env_path = os.path.join(root, ".env")
    actual = parse_env_names(env_path) if os.path.exists(env_path) else None
    used_names = set(used)
    report = {
        "used": {k: sorted(v) for k, v in sorted(used.items())},
        "documented": sorted(documented),
        "ghosts": sorted(used_names - documented),
        "stale": sorted(documented - used_names),
        "unset": None,
        "ok": sorted(used_names & documented),
    }
    if actual is not None:
        report["unset"] = sorted((used_names & documented) - actual)
    return report


def render(report):
    lines = []
    lines.append(f"Used in code: {len(report['used'])}   Documented: {len(report['documented'])}   Clean: {len(report['ok'])}")
    lines.append("")
    lines.append("GHOSTS (used in code, missing from .env.example)")
    if report["ghosts"]:
        for name in report["ghosts"]:
            where = ", ".join(report["used"][name][:3])
            lines.append(f"  {name}   in {where}")
    else:
        lines.append("  none. Every used variable is documented.")
    lines.append("")
    lines.append("STALE (documented, never used in code)")
    if report["stale"]:
        for name in report["stale"]:
            lines.append(f"  {name}")
    else:
        lines.append("  none.")
    if report["unset"] is not None:
        lines.append("")
        lines.append("UNSET (used and documented, missing from your .env)")
        if report["unset"]:
            for name in report["unset"]:
                lines.append(f"  {name}")
        else:
            lines.append("  none.")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="ghostenv",
        description="Hunt the environment variables your code uses in secret.",
    )
    parser.add_argument("--root", default=".", help="project root (default: current directory)")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)

    report = analyze(args.root)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render(report))
    return 1 if report["ghosts"] else 0


if __name__ == "__main__":
    sys.exit(main())
