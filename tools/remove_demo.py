"""Turns a clone into a clean application: deletes the demo and what only the demo needs. Then run tools/css.py.

uv run --frozen python tools/remove_demo.py
"""

import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ONLY_ON_DEMO = {"A11Y-09", "COMP-03", "DATA-07"}
"""Rules whose only proof is a demo screen. Without the demo nothing proves them automatically, so they stop saying so:
they become `By hand` until the application has a screen, and a test, of its own. A test keeps this set exact."""
DEMO_ICONS = (
    "calendar",
    "clipboard-list",
    "clock",
    "component",
    "database",
    "eye",
    "file-spreadsheet",
    "gauge",
    "history",
    "printer",
    "shield",
    "wallet",
    "wrench",
)
"""Icons only the demo uses. The rest belong to the application's shell."""
DEMO_MIGRATIONS = "*_demo_*.py"


def rewrite(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def main() -> None:
    for folder in (ROOT / "app" / "demo", ROOT / "tests" / "demo", ROOT / "app" / "ui" / "static" / "placeholders"):
        if folder.exists():
            shutil.rmtree(folder)
    for icon in DEMO_ICONS:
        (ROOT / "app" / "ui" / "templates" / "ui" / "icons" / f"{icon}.svg").unlink(missing_ok=True)

    # These migrations hold only the demo's tables. The tooling stays, and the application's own starts from zero.
    for migration in (ROOT / "migrations" / "versions").glob(DEMO_MIGRATIONS):
        migration.unlink()

    for source in (ROOT / "app" / "main.py", ROOT / "migrations" / "env.py"):
        lines = source.read_text(encoding="utf-8").splitlines(keepends=True)
        rewrite(source, "".join(line for line in lines if not line.rstrip().endswith("# demo")))

    stylesheet = ROOT / "app" / "ui" / "styles" / "app.css"
    lines = stylesheet.read_text(encoding="utf-8").splitlines(keepends=True)
    rewrite(stylesheet, "".join(line for line in lines if not line.rstrip().endswith("/* demo */")))

    # The gallery's source. tools/gallery.py stays, with nothing to do, so the update workflow needs no second form.
    (ROOT / "tools" / "tailwind" / "daisyui-docs.json").unlink(missing_ok=True)
    vendored = ROOT / "vendor.json"
    entries = json.loads(vendored.read_text(encoding="utf-8"))
    entries.pop("daisyui-docs", None)
    rewrite(vendored, json.dumps(entries, indent=2) + "\n")

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
