"""Which languages leave four-digit numbers ungrouped, from Unicode's own data.

    uv run --frozen python tools/cldr_grouping.py

Babel does not apply CLDR's minimumGroupingDigits. This writes the value of each locale that differs from its parent,
from the CLDR version Babel uses; app/core/formatters.py looks a locale up, then its parents, then uses 1. CLDR omits
default regions such as es-ES because they inherit, so this must follow parents too. tests/test_language.py fails if
the two versions part ways: run this again after upgrading Babel.
"""

import io
import json
import sys
import tarfile
from pathlib import Path

from babel.core import get_cldr_version

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vendor

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "app" / "core" / "cldr_grouping.json"
PACKAGE = "cldr-numbers-full"
NUMBERS = "/numbers.json"


def inherited(locale: str, values: dict[str, int]) -> int:
    while "-" in locale:
        locale = locale.rpartition("-")[0]
        if locale in values:
            return values[locale]
    return 1


def main() -> None:
    version = f"{get_cldr_version()}.0.0"
    values = {}
    with tarfile.open(fileobj=io.BytesIO(vendor.tarball(PACKAGE, version))) as archive:
        for member in archive.getmembers():
            if not (member.name.startswith("package/main/") and member.name.endswith(NUMBERS)):
                continue
            extracted = archive.extractfile(member)
            if extracted is None:
                continue
            locale = member.name.removeprefix("package/main/").removesuffix(NUMBERS)
            values[locale] = int(json.load(extracted)["main"][locale]["numbers"]["minimumGroupingDigits"])
    locales = {locale: value for locale, value in sorted(values.items()) if value != inherited(locale, values)}
    content = {"cldr": version, "source": PACKAGE, "licence": "Unicode-3.0", "locales": locales}
    TARGET.write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(locales)} locales from CLDR {version}")


if __name__ == "__main__":
    main()
