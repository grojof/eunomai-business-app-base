"""The equipment list's export holds exactly what the screen filters and sorts."""

import io
import re
import time
import xml.etree.ElementTree as ET
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.demo.generate import equipment_row
from app.main import create_app
from tests.conftest import build_settings

MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def rows_of(content: bytes) -> list[list[str]]:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))  # noqa: S314  # a file this test made
    found = []
    for row in sheet.iter(f"{MAIN}row"):
        values = []
        for cell in row:
            value = cell.find(f"{MAIN}v")
            text = cell.find(f"{MAIN}is/{MAIN}t")
            values.append((value if value is not None else text).text)
        found.append(values)
    return found


def codes_on_screen(client: TestClient, query: str) -> list[str]:
    html = client.get(f"/equipment?size=100&{query}").text
    return re.findall(r'href="/equipment/\d+">(EQ-\d+)</a>', html)


@pytest.mark.parametrize(
    "query",
    [
        "",
        "status=stopped",
        "location=Roof&sort=cost&dir=desc",
        "q=compressor&sort=name",
        "sort=location",
        "sort=status",
    ],
)
def test_the_file_has_the_rows_of_the_screen_in_its_order(filled, query):
    shown = codes_on_screen(filled, query)
    rows = rows_of(filled.get(f"/equipment/export?{query}").content)
    assert [row[0] for row in rows[1 : len(shown) + 1]] == shown


def test_every_filtered_row_goes_not_just_a_page(filled):
    rows = rows_of(filled.get("/equipment/export").content)
    assert len(rows) == 1_001


def test_a_page_in_the_address_changes_nothing(filled):
    assert len(rows_of(filled.get("/equipment/export?page=3&size=10").content)) == 1_001


def test_the_cost_is_rounded_and_a_number(filled):
    first = rows_of(filled.get("/equipment/export").content)[1]
    assert first[5] == f"{equipment_row(0)['cost']:.2f}"


def test_the_headers_and_labels_are_in_the_persons_language(filled):
    filled.cookies.set("language", "es")
    response = filled.get("/equipment/export?status=stopped&location=Roof")
    rows = rows_of(response.content)
    assert rows[0][:4] == ["Código", "Nombre", "Ubicación", "Estado"]
    assert rows[1][2:4] == ["Cubierta", "Parado"]
    assert "Equipos" in response.headers["content-disposition"]


def test_the_list_offers_the_export_of_what_it_shows(filled):
    html = filled.get("/equipment?status=stopped&sort=cost&page=2").text
    assert 'href="/equipment/export?status=stopped&amp;sort=cost"' in html


def test_nothing_to_export_offers_no_export(filled):
    assert "/equipment/export" not in filled.get("/equipment?q=nothing+like+this").text


def test_without_the_rows_the_export_goes_back_to_the_list(client, person):
    response = client.get("/equipment/export", headers=person, follow_redirects=False)
    assert (response.status_code, response.headers["location"]) == (303, "/equipment")


@pytest.mark.rule("SEC-05")
def test_the_export_validates_the_address_like_the_list(filled):
    rows = rows_of(filled.get("/equipment/export?sort=name;DROP TABLE equipment&status=x'").content)
    assert len(rows) == 1_001


def test_fifty_thousand_rows_arrive_whole(large_url, person):
    client = TestClient(create_app(build_settings(database_url=large_url)))
    started = time.perf_counter()
    content = client.get("/equipment/export", headers=person).content
    seconds = time.perf_counter() - started
    assert len(rows_of(content)) == 50_001
    assert seconds < 30
