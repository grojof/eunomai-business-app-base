"""Excel files, written on the server: real numbers and dates, in the same order as the screen.

XlsxWriter's `constant_memory` writes each row to disk as it arrives, so a long list never sits in memory. The cost is
that rows go in order, one way, which is all an export needs.

Three things go wrong with a list that reaches a spreadsheet, and each is handled once, here:

- Excel keeps 15 significant digits. A value is rounded by the application's rule first, and one still too long goes as
  text, right-aligned: visibly not a number, and every digit there.
- Excel reads `=` as a formula, and a value typed by someone may arrive there. Text that could be read as one starts
  with an apostrophe, as OWASP asks. That also holds if the sheet is later saved as CSV, where cells lose their type.
- Excel guesses. Each column declares its kind, and text is always written as text, so a long code keeps its zeros.
"""

import os
import tempfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from xlsxwriter import Workbook  # type: ignore[import-untyped]

from app.core.formatters import rounded

SIGNIFICANT_DIGITS = 15
LAST_ROW = 1_048_575
"""Excel's own limit, counting from zero. XlsxWriter would skip further rows without an error."""
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r", "\n", "\uff1d", "\uff0b", "\uff0d", "\uff20")
"""What a spreadsheet may read as the start of a formula, full-width forms included."""
NOT_IN_A_SHEET_NAME = str.maketrans(dict.fromkeys("[]:*?/\\'", " "))
SHEET_NAME_LENGTH = 31
SHORT_DATE = 14
"""Excel's built-in format: the date as the computer that opens the file writes it."""
SHORT_MOMENT = 22
MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@dataclass(frozen=True)
class ExcelColumn:
    header: str  # already in the person's language
    kind: Literal["text", "number", "date", "moment"] = "text"
    width: int = 16
    places: int = 2


def safe_text(value: str) -> str:
    """Text that cannot run as a formula, here or after being saved as CSV."""
    return f"'{value}" if value.lstrip(" ").startswith(FORMULA_STARTS) else value


def exact_enough(value: Decimal | int, places: int) -> Decimal | None:
    """The value by the application's rule, or None if Excel could not keep all of it."""
    number = rounded(value, places)
    return number if len(number.as_tuple().digits) <= SIGNIFICANT_DIGITS else None


def sheet_name(title: str) -> str:
    return title.translate(NOT_IN_A_SHEET_NAME).strip()[:SHEET_NAME_LENGTH] or "Sheet1"


def _write_row(
    sheet: Any, number: int, columns: Sequence[ExcelColumn], row: Sequence[Any], formats: dict[Any, Any], zone: ZoneInfo
) -> None:
    for position, (column, value) in enumerate(zip(columns, row, strict=True)):
        if value is None:
            continue
        if column.kind == "number":
            kept = exact_enough(value, column.places)
            if kept is None:
                sheet.write_string(number, position, format(rounded(value, column.places), "f"), formats["long"])
            else:
                sheet.write_number(number, position, kept, formats[column.places])
        elif column.kind == "date":
            sheet.write_datetime(number, position, value, formats["date"])
        elif column.kind == "moment":
            local: datetime = value.astimezone(zone).replace(tzinfo=None)
            sheet.write_datetime(number, position, local, formats["moment"])
        else:
            sheet.write_string(number, position, safe_text(str(value)))


def write_workbook(
    target: str, title: str, columns: Sequence[ExcelColumn], rows: Iterable[Sequence[Any]], zone: str
) -> int:
    """Writes the file and returns how many rows it holds. More rows than Excel has is an error, never a shorter file.

    The `with` also clears XlsxWriter's own temporary files when a row fails on the way.
    """
    with Workbook(target, {"constant_memory": True}) as workbook:
        workbook.set_properties({"title": title})
        sheet = workbook.add_worksheet(sheet_name(title))
        header = workbook.add_format({"bold": True, "bottom": 1})
        formats: dict[Any, Any] = {
            "date": workbook.add_format({"num_format": SHORT_DATE}),
            "moment": workbook.add_format({"num_format": SHORT_MOMENT}),
            "long": workbook.add_format({"align": "right"}),
        }
        for places in {column.places for column in columns if column.kind == "number"}:
            decimals = "." + "0" * places if places else ""
            formats[places] = workbook.add_format({"num_format": "#,##0" + decimals})
        for position, column in enumerate(columns):  # widths come first: `constant_memory` cannot go back
            sheet.set_column(position, position, column.width)
        sheet.freeze_panes(1, 0)
        for position, column in enumerate(columns):
            sheet.write_string(0, position, column.header, header)
        time_zone = ZoneInfo(zone)
        last = 0
        for last, row in enumerate(rows, start=1):
            if last > LAST_ROW:
                raise ValueError(f"Excel holds {LAST_ROW} rows: this list has more")
            _write_row(sheet, last, columns, row, formats, time_zone)
        sheet.autofilter(0, 0, last, len(columns) - 1)
    return last


def excel_response(
    title: str, columns: Sequence[ExcelColumn], rows: Iterable[Sequence[Any]], zone: str
) -> FileResponse:
    """A download, from a file that goes away once it is sent. A failure leaves nothing behind."""
    descriptor, path = tempfile.mkstemp(suffix=".xlsx")
    os.close(descriptor)
    try:
        write_workbook(path, title, columns, rows, zone)
    except Exception:
        Path(path).unlink()
        raise
    return FileResponse(
        path,
        media_type=MEDIA_TYPE,
        filename=f"{title}-{date.today().isoformat()}.xlsx",
        background=BackgroundTask(Path(path).unlink),
    )
