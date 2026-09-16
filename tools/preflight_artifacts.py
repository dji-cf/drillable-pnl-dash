"""Pre-flight: assert every path in snowflake.yml::artifacts exists on disk.

`snow streamlit deploy` does NOT validate this. A missing path uploads as a
zero-byte stage entry, the deploy exits 0, and the app dies on first import --
the single most common cause of "the deploy succeeded but the app is broken".

    .venv\\Scripts\\python.exe tools\\preflight_artifacts.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "snowflake.yml"


def main() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    entities = manifest.get("entities") or {}

    problems: list[str] = []
    checked = 0

    for name, ent in entities.items():
        if (ent or {}).get("type") != "streamlit":
            continue
        artifacts = ent.get("artifacts") or []
        main_file = ent.get("main_file")

        if main_file and main_file not in artifacts:
            problems.append(
                f"{name}: main_file {main_file!r} is not listed in artifacts"
            )

        for art in artifacts:
            checked += 1
            if not (ROOT / art).exists():
                problems.append(f"{name}: MISSING {art}")

        # Anything the app imports must ship. Catch a new module that was added
        # to the project but never added to the manifest.
        for module in sorted(ROOT.glob("*.py")):
            if module.name not in artifacts:
                problems.append(
                    f"{name}: {module.name} exists in the project but is not in "
                    f"artifacts (add it, or move it under tools/)"
                )

    print(f"checked {checked} artifact path(s) in {MANIFEST.name}")
    if problems:
        print("\nPROBLEMS:", *problems, sep="\n  ")
        raise SystemExit(1)
    print("OK -- every artifact exists and every top-level module ships")


if __name__ == "__main__":
    main()
