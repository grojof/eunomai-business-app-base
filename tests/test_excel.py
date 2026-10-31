"""Excel files, read back by unzipping their XML: no reader is a dependency of this repository."""

import logging
import re
import xml.etree.ElementTree as ET
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.core.excel import ExcelColumn, exact_enough, excel_response, safe_text, sheet_name, write_workbook

MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
COLUMNS = (
    ExcelColumn("Code"),
    ExcelColumn("Cost", "number"),
    ExcelColumn("Due", "date"),
    ExcelColumn("Seen", "moment"),
)


def cells(path: Path) -> list[list[tuple[str, str]]]:
    """Every row as (type, text): `n` for a number or a date, `inlineStr` for text."""
    with zipfile.ZipFile(path) as archive:
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))  # noqa: S314  # a file this test made
    rows = []
    for row in sheet.iter(f"{MAIN}row"):
        found = []
        for cell in row:
            kind = cell.get("t", "n")
            value = cell.find(f"{MAIN}v")
            text = cell.find(f"{MAIN}is/{MAIN}t")
            found.append((kind, (value if value is not None else text).text or ""))
        rows.append(found)
    return rows


def written(tmp_path: Path, rows, zone: str = "UTC") -> list[list[tuple[str, str]]]:
    path = tmp_path / "list.xlsx"
    write_workbook(str(path), "List", COLUMNS, rows, zone)
    return cells(path)


def test_a_header_and_real_cells(tmp_path):
    rows = written(tmp_path, [("A-1", Decimal("1234.5"), date(2027, 3, 15), datetime(2026, 1, 2, 3, 4, tzinfo=UTC))])
    assert [text for _kind, text in rows[0]] == ["Code", "Cost", "Due", "Seen"]
    code, cost, due, seen = rows[1]
    assert code == ("inlineStr", "A-1")
    assert (cost[0], Decimal(cost[1])) == ("n", Decimal("1234.5"))
    assert due == ("n", "46461")
    assert seen[0] == "n"
    assert seen[1].startswith("46024.127")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("0.125"), "0.13"),
        (Decimal("0.135"), "0.14"),
        (Decimal("2.5"), "2.5"),
        (Decimal("1234567890123.45678901234567890123"), "1234567890123.46"),
    ],
)
def test_a_decimal_is_rounded_half_up_before_excel_sees_it(tmp_path, value, expected):
    kind, text = written(tmp_path, [("A", value, None, None)])[1][1]
    assert (kind, Decimal(text)) == ("n", Decimal(expected))


def test_digits_excel_cannot_keep_go_as_text(tmp_path):
    value = Decimal("123456789012345678.12")
    assert exact_enough(value, 2) is None
    assert written(tmp_path, [("A", value, None, None)])[1][1] == ("inlineStr", "123456789012345678.12")


def test_fifteen_digits_stay_a_number():
    assert exact_enough(Decimal("1234567890123.45"), 2) == Decimal("1234567890123.45")


def test_a_long_code_stays_text_with_its_zeros(tmp_path):
    assert written(tmp_path, [("000123456789012345678", None, None, None)])[1][0] == (
        "inlineStr",
        "000123456789012345678",
    )


@pytest.mark.rule("SEC-15")
@pytest.mark.parametrize(
    "text",
    [
        "=1+1",
        "+1+1",
        "-1+1",
        "@SUM(A1)",
        "\t=1",
        "\r=1",
        '=HYPERLINK("http://a.example")',
        "  =1",
        "\uff1d1",
        "\uff0b1",
    ],
)
def test_text_that_could_run_as_a_formula_is_neutralised(tmp_path, text):
    assert safe_text(text) == f"'{text}"
    kind, value = written(tmp_path, [(text, None, None, None)])[1][0]
    assert kind == "inlineStr"
    assert value.startswith("'")


@pytest.mark.rule("SEC-15")
def test_no_cell_holds_a_formula(tmp_path):
    path = tmp_path / "list.xlsx"
    write_workbook(str(path), "List", COLUMNS, [("=1+1", None, None, None)], "UTC")
    with zipfile.ZipFile(path) as archive:
        assert b"<f>" not in archive.read("xl/worksheets/sheet1.xml")


@pytest.mark.parametrize("text", ["Air compressor", "1-2", "a=b", "EQ-000001"])
def test_ordinary_text_is_left_alone(text):
    assert safe_text(text) == text


def test_a_moment_is_shown_in_the_applications_time_zone(tmp_path):
    moment = datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
    in_utc = float(written(tmp_path, [("A", None, None, moment)], "UTC")[1][1][1])
    in_madrid = float(written(tmp_path, [("A", None, None, moment)], "Europe/Madrid")[1][1][1])
    assert in_madrid - in_utc == pytest.approx(2 / 24)


def test_an_empty_value_leaves_an_empty_cell(tmp_path):
    assert len(written(tmp_path, [("A", None, None, None)])[1]) == 1


def test_the_file_has_filters_and_a_fixed_header(tmp_path):
    path = tmp_path / "list.xlsx"
    assert write_workbook(str(path), "List", COLUMNS, [("A", None, None, None), ("B", None, None, None)], "UTC") == 2
    with zipfile.ZipFile(path) as archive:
        sheet = archive.read("xl/worksheets/sheet1.xml").decode()
    assert '<autoFilter ref="A1:D3"/>' in sheet
    assert 'state="frozen"' in sheet


@pytest.mark.parametrize(
    ("title", "expected"),
    [("Equipment", "Equipment"), ("a/b:c", "a b c"), ("x" * 40, "x" * 31), ("[]", "Sheet1")],
)
def test_a_title_becomes_a_name_excel_accepts(title, expected):
    assert sheet_name(title) == expected


def test_more_rows_than_excel_has_fails_instead_of_cutting_the_file(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.excel.LAST_ROW", 2)
    rows = [("A", None, None, None)] * 3
    with pytest.raises(ValueError, match="more"):
        write_workbook(str(tmp_path / "list.xlsx"), "List", COLUMNS, rows, "UTC")


def test_a_failure_leaves_no_file_behind(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))

    def broken():
        yield ("A", None, None, None)
        raise RuntimeError("the query failed")

    with pytest.raises(RuntimeError):
        excel_response("List", COLUMNS, broken(), "UTC")
    assert list(tmp_path.iterdir()) == []


def test_the_download_is_named_and_typed():
    response = excel_response("Equipos", COLUMNS, [("A", None, None, None)], "UTC")
    assert response.media_type.endswith("spreadsheetml.sheet")
    assert re.search(r'attachment; filename="Equipos-\d{4}-\d{2}-\d{2}\.xlsx"', response.headers["content-disposition"])
    Path(response.path).unlink()


@pytest.mark.parametrize(
    "text", ["x" * 32_768, "=" + "y" * 32_767, "z" * 40_000], ids=["over", "with its apostrophe", "long"]
)
def test_text_too_long_for_a_cell_is_cut_on_purpose_and_logged(tmp_path, caplog, text):
    with caplog.at_level(logging.WARNING, logger="app.core.excel"):
        value = written(tmp_path, [(text, None, None, None)])[1][0][1]
    assert len(value) == 32_767
    assert value.endswith("\u2026")
    assert "row 1" in caplog.text
    assert text[1:50] not in caplog.text, "what a cell holds does not belong in a log"


def test_the_longest_text_a_cell_holds_is_left_alone(tmp_path, caplog):
    with caplog.at_level(logging.WARNING, logger="app.core.excel"):
        assert written(tmp_path, [("z" * 32_767, None, None, None)])[1][0][1] == "z" * 32_767
    assert caplog.text == ""


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (date(1899, 12, 31), "1899-12-31"),
        (date(1800, 1, 1), "1800-01-01"),
        (date(1, 1, 1), "0001-01-01"),
    ],
)
def test_a_date_before_excels_calendar_is_written_as_text(tmp_path, value, text):
    assert written(tmp_path, [("A", None, value, None)])[1][1] == ("inlineStr", text)


def test_a_moment_before_excels_calendar_is_written_as_text(tmp_path):
    moment = datetime(1850, 6, 1, 12, 0, tzinfo=UTC)
    assert written(tmp_path, [("A", None, None, moment)])[1][1] == ("inlineStr", "1850-06-01 12:00:00")


def test_the_first_day_of_excels_calendar_is_a_date(tmp_path):
    assert written(tmp_path, [("A", None, date(1900, 1, 1), None)])[1][1][0] == "n"


@pytest.mark.parametrize(("zone", "day"), [("Pacific/Kiritimati", "2027-01-01"), ("Pacific/Pago_Pago", "2026-12-31")])
def test_the_file_is_named_for_the_applications_day(monkeypatch, zone, day):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 12, 31, 23, 30, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr("app.core.excel.datetime", Clock)
    response = excel_response("List", COLUMNS, [("A", None, None, None)], zone)
    assert f"List-{day}.xlsx" in response.headers["content-disposition"]
    Path(response.path).unlink()
