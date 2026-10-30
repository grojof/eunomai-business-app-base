"""The stylesheet: generated from the templates by Tailwind's standalone executable, with no Node.

    uv run python tools/css.py         write app/ui/static/app.css
    uv run python tools/css.py check   fail if it is out of date

The executable is downloaded once for this computer, checked against the hash in vendor.json, and kept in .cache/.
Servers need none of this: they receive the generated file.
"""

import hashlib
import json
import platform
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "app" / "ui" / "styles" / "app.css"
TARGET = ROOT / "app" / "ui" / "static" / "app.css"
RELEASES = "https://github.com/tailwindlabs/tailwindcss/releases/download"


def executable_name() -> str:
    system = {"Linux": "linux", "Darwin": "macos", "Windows": "windows"}[platform.system()]
    machine = {"x86_64": "x64", "amd64": "x64", "arm64": "arm64", "aarch64": "arm64"}[platform.machine().lower()]
    return f"tailwindcss-{system}-{machine}" + (".exe" if system == "windows" else "")


def executable() -> Path:
    entry = json.loads((ROOT / "vendor.json").read_text(encoding="utf-8"))["tailwindcss"]
    name = executable_name()
    expected = entry["executables"][name]
    path: Path = ROOT / ".cache" / "tailwindcss" / entry["version"] / name
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(f"{RELEASES}/v{entry['version']}/{name}", timeout=300) as response:
            content = response.read()
        if hashlib.sha256(content).hexdigest() != expected:
            raise RuntimeError(f"{name}: the download does not match vendor.json")
        path.write_bytes(content)
        path.chmod(0o755)
    return path


def build(target: Path) -> None:
    subprocess.run(
        [str(executable()), "-i", str(SOURCE), "-o", str(target), "--minify"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )


def main() -> int:
    if sys.argv[1:] == []:
        build(TARGET)
        print(f"{TARGET.relative_to(ROOT).as_posix()}: {TARGET.stat().st_size} bytes")
        return 0
    if sys.argv[1:] == ["check"]:
        with tempfile.TemporaryDirectory() as folder:
            fresh = Path(folder) / "app.css"
            build(fresh)
            same = fresh.read_bytes() == TARGET.read_bytes()
        print("stylesheet up to date" if same else "app/ui/static/app.css is out of date: run tools/css.py")
        return 0 if same else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
