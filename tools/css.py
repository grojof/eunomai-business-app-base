"""The stylesheet: generated from the templates by Tailwind's standalone executable, with no Node.

    uv run --frozen python tools/css.py         write app/ui/static/app.css
    uv run --frozen python tools/css.py check   fail if it is out of date

The executable is downloaded once for this computer and kept in .cache/. It runs only if it matches the hash in
vendor.json, checked every time: one that does not is downloaded again. Servers need none of this: they receive the
generated file.
"""

import hashlib
import json
import os
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
SYSTEMS = {"Linux": "linux", "Darwin": "macos", "Windows": "windows"}
MACHINES = {"x86_64": "x64", "amd64": "x64", "arm64": "arm64", "aarch64": "arm64"}
SUPPORTED = (
    "tailwindcss-linux-arm64",
    "tailwindcss-linux-arm64-musl",
    "tailwindcss-linux-x64",
    "tailwindcss-linux-x64-musl",
    "tailwindcss-macos-arm64",
    "tailwindcss-macos-x64",
    "tailwindcss-windows-x64.exe",
)


def uses_musl() -> bool:
    return platform.system() == "Linux" and any(Path("/lib").glob("ld-musl-*"))


def executable_name() -> str:
    system = SYSTEMS.get(platform.system())
    machine = MACHINES.get(platform.machine().lower())
    name = (
        f"tailwindcss-{system}-{machine}" + ("-musl" if uses_musl() else "") + (".exe" if system == "windows" else "")
    )
    if name not in SUPPORTED:
        raise SystemExit(
            f"Tailwind publishes no executable for {platform.system()} on {platform.machine()}. "
            f"It has: {', '.join(SUPPORTED)}"
        )
    return name


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def executable() -> Path:
    entry = json.loads((ROOT / "vendor.json").read_text(encoding="utf-8"))["tailwindcss"]
    name = executable_name()
    expected = entry["executables"][name]
    path: Path = ROOT / ".cache" / "tailwindcss" / entry["version"] / name
    if path.exists() and sha256(path.read_bytes()) == expected:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(f"{RELEASES}/v{entry['version']}/{name}", timeout=300) as response:
        content = response.read()
    if sha256(content) != expected:
        raise RuntimeError(f"{name}: the download does not match vendor.json")
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f"{name}.")
    with os.fdopen(descriptor, "wb") as file:
        file.write(content)
    Path(temporary).chmod(0o755)
    os.replace(temporary, path)
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
