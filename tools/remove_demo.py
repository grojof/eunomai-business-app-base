"""Turns a clone into a clean application: deletes the demo and what only the demo needs. Then run tools/css.py.

uv run python tools/remove_demo.py
"""

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ONLY_ON_DEMO = {"A11Y-09", "COMP-03"}
"""Rules whose only proof is a demo screen. Without the demo nothing proves them automatically, so they stop saying so:
they become `By hand` until the application has a screen, and a test, of its own. A test keeps this set exact."""
DEMO_ICONS = (
    "calendar",
    "clipboard-list",
    "clock",
    "component",
    "layout-dashboard",
    "layout-grid",
    "layout-panel-left",
    "shield",
    "wallet",
)
"""Icons only the demo uses. The rest belong to the application's shell."""


def rewrite(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def main() -> None:
    for folder in (ROOT / "app" / "demo", ROOT / "tests" / "demo"):
        if folder.exists():
            shutil.rmtree(folder)
    for icon in DEMO_ICONS:
        (ROOT / "app" / "ui" / "templates" / "ui" / "icons" / f"{icon}.svg").unlink(missing_ok=True)

    main_file = ROOT / "app" / "main.py"
    lines = main_file.read_text(encoding="utf-8").splitlines(keepends=True)
    rewrite(main_file, "".join(line for line in lines if not line.rstrip().endswith("# demo")))

    example = ROOT / ".env.example"
    rewrite(example, example.read_text(encoding="utf-8").replace("demo-admins", "admins"))

    standards = ROOT / "docs" / "standards.md"
    if standards.exists():
        text = standards.read_text(encoding="utf-8")
        for rule in sorted(ONLY_ON_DEMO):
            text = re.sub(rf"^(\| {rule} \|.*\| )Automatic( \|)$", r"\1By hand\2", text, flags=re.M)
        rewrite(standards, text)


if __name__ == "__main__":
    main()
