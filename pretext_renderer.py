from __future__ import annotations

import argparse
import shutil
from pathlib import Path


SOURCE_TEMPLATE = Path("templates") / "single.html"
TARGET_TEMPLATE = Path("layouts") / "_default" / "single.html"


def main() -> None:
    parser = argparse.ArgumentParser(description="Install the Hugo single.html reader template safely.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the existing target template.",
    )
    args = parser.parse_args()

    if not SOURCE_TEMPLATE.exists():
        raise SystemExit(
            f"Source template not found: {SOURCE_TEMPLATE}\n"
            "Put your good single.html into templates/single.html first."
        )

    TARGET_TEMPLATE.parent.mkdir(parents=True, exist_ok=True)

    if TARGET_TEMPLATE.exists() and not args.force:
        print(f"⛔ Refusing to overwrite existing template: {TARGET_TEMPLATE}")
        print("Use --force if you really want to replace it.")
        return

    if TARGET_TEMPLATE.exists():
        backup = TARGET_TEMPLATE.with_suffix(".html.bak")
        shutil.copy2(TARGET_TEMPLATE, backup)
        print(f"🗂 Backup created: {backup}")

    shutil.copy2(SOURCE_TEMPLATE, TARGET_TEMPLATE)
    print(f"✅ Installed template: {TARGET_TEMPLATE}")


if __name__ == "__main__":
    main()