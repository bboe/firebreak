from __future__ import annotations

import csv
import pathlib
import re

import pytest

from firebreak.survey import BOOT0, BOOT0_LK, CSV_HEADER, CSV_ORDER, SPARE

COPIES = (BOOT0, BOOT0_LK)
DEVICES = pathlib.Path(__file__).resolve().parent.parent / "firebreak" / "devices"
DIGEST = re.compile(r"[0-9a-f]{64}")
DOCS = pathlib.Path(__file__).resolve().parent.parent / "docs" / "devices.md"
ENTRY = re.compile(r"^\| \[(\w+)\]\(#\1\) \| (.+?) \| `(.+?)` \|$", re.MULTILINE)
HEADER = CSV_HEADER.split(",")
PREFIXES = (*COPIES, SPARE)
SHEETS = sorted(DEVICES.glob("*-partitions.csv"))
VEGA = "Vega "


def builds(*, path: pathlib.Path) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for row in rows(path=path):
        found.setdefault(row["build"], []).append(row["partition"])
    return found


def index() -> dict[str, str]:
    return {
        found.group(1): found.group(3)
        for found in ENTRY.finditer(DOCS.read_text(encoding="utf-8"))
    }


def rows(*, path: pathlib.Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        found = list(csv.DictReader(stream))
    for row in found:
        assert None not in row, (path.name, row)
        assert None not in row.values(), (path.name, row)
    return found


def test_a_build_keeps_its_rows_together() -> None:
    for path in SHEETS:
        blocks = [row["build"] for row in rows(path=path)]
        started = [
            build
            for index, build in enumerate(blocks)
            if index == 0 or blocks[index - 1] != build
        ]
        assert len(started) == len(set(started)), path.name


def test_every_csv_carries_the_header_survey_prints() -> None:
    for path in SHEETS:
        with path.open(encoding="utf-8", newline="") as stream:
            assert next(csv.reader(stream), None) == HEADER, path.name


def test_every_csv_names_one_model_and_the_index_agrees() -> None:
    models = index()
    for path in SHEETS:
        found = {row["model"] for row in rows(path=path)}
        codename = path.name.removesuffix("-partitions.csv")
        assert found == {models.get(codename)}, path.name


def test_every_digest_is_a_sha256() -> None:
    for path in SHEETS:
        for row in rows(path=path):
            assert DIGEST.fullmatch(row["sha256"]), (path.name, row["partition"])


def test_every_row_names_the_device_its_file_does() -> None:
    for path in SHEETS:
        codename = path.name.removesuffix("-partitions.csv")
        assert {row["device"] for row in rows(path=path)} == {codename}, path.name


def test_every_size_is_a_positive_whole_number() -> None:
    for path in SHEETS:
        for row in rows(path=path):
            assert row["bytes"].isdigit(), (path.name, row["partition"])
            assert int(row["bytes"]) > 0, (path.name, row["partition"])


def test_no_build_names_a_partition_twice() -> None:
    for path in SHEETS:
        for build, parts in builds(path=path).items():
            assert len(parts) == len(set(parts)), (path.name, build)


def test_one_image_is_never_given_two_sizes() -> None:
    sizes: dict[str, tuple[str, str, str]] = {}
    for path in SHEETS:
        for row in rows(path=path):
            held = sizes.setdefault(
                row["sha256"], (row["bytes"], path.name, row["partition"])
            )
            assert held[0] == row["bytes"], (held, path.name, row["partition"])


def test_the_index_links_a_section_that_exists() -> None:
    text = DOCS.read_text(encoding="utf-8")
    for codename in index():
        assert f"\n## {codename}\n" in text, codename


def test_the_index_lists_every_device_a_csv_covers() -> None:
    covered = {path.name.removesuffix("-partitions.csv") for path in SHEETS}
    assert set(index()) == covered


@pytest.mark.parametrize("path", SHEETS, ids=lambda path: path.name)
def test_the_rows_of_a_build_follow_the_survey_order(path: pathlib.Path) -> None:
    for build, parts in builds(path=path).items():
        if build.startswith(VEGA):
            continue
        known = [part for part in parts if part in CSV_ORDER]
        assert known == [part for part in CSV_ORDER if part in known], (
            path.name,
            build,
        )
        extra = [part for part in parts if part not in CSV_ORDER]
        copies = sorted(part for part in extra if part.startswith(COPIES))
        spare = sorted(part for part in extra if part.startswith(SPARE))
        assert extra == copies + spare, (path.name, build)
        assert all(part.startswith(PREFIXES) for part in extra), (path.name, build)
        assert parts == known + extra, (path.name, build)
        # survey drops preloader where boot0 carries it, which is where a
        # preloader copy sorts first, before any lk copy.
        if copies and copies[0].startswith(BOOT0):
            assert "preloader" not in parts, (path.name, build)
