"""Turns a clone into a clean application: deletes the demo and the lines that install it.

uv run python tools/remove_demo.py
"""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    for folder in (ROOT / "app" / "demo", ROOT / "tests" / "demo"):
        if folder.exists():
            shutil.rmtree(folder)
    main_file = ROOT / "app" / "main.py"
    lines = main_file.read_text(encoding="utf-8").splitlines(keepends=True)
    main_file.write_text("".join(line for line in lines if not line.rstrip().endswith("# demo")), encoding="utf-8")


if __name__ == "__main__":
    main()
