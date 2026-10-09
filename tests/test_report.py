from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from firebreak import report

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable

    import pytest

LISTING = """\
lrwxrwxrwx root root 2026-10-09 12:00 boot_a -> /dev/block/mmcblk0p17
lrwxrwxrwx root root 2026-10-09 12:00 lk_a -> /tmp/lk_a
lrwxrwxrwx root root 2026-10-09 12:00 lk_a_real -> /dev/block/mmcblk0p3
lrwxrwxrwx root root 2026-10-09 12:00 system -> system_a
lrwxrwxrwx root root 2026-10-09 12:00 system_a -> /dev/block/mmcblk0p13
total 0"""
PARTITIONS = """\
major minor  #blocks  name

 179        0    7634944 mmcblk0
 179       13     786432 mmcblk0p13
 179       17       2048 mmcblk0p17"""
TABLE = """\
Disk /dev/block/mmcblk0: 15269888 sectors, 7.3 GiB
Number  Start (sector)    End (sector)  Size       Code  Name
   3            8192            9215   512.0 KiB   0700  lk_a
  13          262144         1835007   768.0 MiB   0700  system_a
  17         1835008         1839103   2.0 MiB     0700  boot_a
table-ok"""


def marked(*, boot: str = "", log: str) -> Callable[..., str]:
    def asked(*, command: str) -> str:
        if command.startswith(report.BOOT_LINE):
            return f"{boot}\n{report.BOOT_OK}"
        return f"{log}\n{report.LOG_OK}"

    return asked


def test_dot_details_labels_each_answer() -> None:
    def asked(*, command: str) -> str:
        return "uptime" if "uptime" in command else "x"

    said = report.dot_details(asked=asked)
    assert len(said) == len(report.PROPERTIES) + len(report.EMMC_FIELDS) + 1
    assert said[0] == report.labelled(label="ro.product.device", value="x")
    assert said[len(report.PROPERTIES)].startswith("eMMC name")
    assert said[-1] == report.labelled(label="uptime", value="uptime s, dmesg from x s")


def test_labelled_pads_the_label() -> None:
    assert report.labelled(label="adb", value=1) == "adb" + " " * 22 + "1"


def test_masked_hides_guids_and_the_serial(*, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(name="ANDROID_SERIAL", value="G090LF0964230U8T")
    text = "G090LF0964230U8T 0FC63DAF-8483-4772-8E79-3D69D8477DE4"
    assert report.masked(text=text) == "<serial> <guid>"
    monkeypatch.delenv(name="ANDROID_SERIAL")
    assert report.masked(text="G090LF0964230U8T") == "G090LF0964230U8T"


def test_mmc_said_claims_nothing_from_a_cut_log() -> None:
    def asked(*, command: str) -> str:
        return "mmc0: CMD13" if command.startswith(report.MMC_LOG) else "x\nboot-ok"

    said = report.mmc_said(asked=asked)
    assert said == [
        "mmc0: CMD13",
        "\nThat log did not arrive whole, so it says nothing either way.",
    ]


def test_mmc_said_finds_the_boot_line_past_the_tail() -> None:
    first = "mmc0: new HS200 MMC card at address 0001"
    said = report.mmc_said(asked=marked(boot=first, log="mmc0: later"))
    assert said == [first, "...", "mmc0: later"]


def test_mmc_said_keeps_a_log_that_reaches_the_boot() -> None:
    logged = "mmc0: new HS200 MMC card at address 0001"
    assert report.mmc_said(asked=marked(boot=logged, log=logged)) == [logged]


def test_mmc_said_says_when_it_is_not_the_kernel_log() -> None:
    said = report.mmc_said(asked=marked(log="sh: dmesg: not found"))
    assert "not the kernel's log" in said[1]


def test_mmc_said_says_when_the_boot_is_gone() -> None:
    said = report.mmc_said(asked=marked(log="msdc0: CMD13 timeout"))
    assert said[0] == "msdc0: CMD13 timeout"
    assert "no longer reaches the boot" in said[1]


def test_node_names_follow_a_name_to_its_node() -> None:
    assert report.node_names(listing=LISTING) == {
        "boot_a": "/dev/block/mmcblk0p17",
        "lk_a": "/tmp/lk_a",
        "lk_a_real": "/dev/block/mmcblk0p3",
        "system": "/dev/block/mmcblk0p13",
        "system_a": "/dev/block/mmcblk0p13",
    }


def test_node_order() -> None:
    assert report.node_order(node="/dev/block/mmcblk0p13") == 13
    assert report.node_order(node="/tmp/lk_a") == 0
    assert report.node_order(node="/dev/block/mmcblk0boot0") == 0


def test_node_sizes_read_proc_partitions() -> None:
    assert report.node_sizes(partitions=PARTITIONS) == {
        "mmcblk0": 7634944 * 1024,
        "mmcblk0p13": 786432 * 1024,
        "mmcblk0p17": 2048 * 1024,
    }


def test_partition_rows_drop_the_marker_and_trailing_space() -> None:
    printed = TABLE.replace("boot_a\n", "boot_a   \n")
    rows = report.partition_rows(names={}, printed=printed)
    assert report.TABLE_OK not in rows
    assert all(row == row.rstrip() for row in rows)
    assert rows[1].index("  node") == rows[2].index("  mmcblk0p3")


def test_partition_rows_leave_a_cut_table_as_it_came() -> None:
    cut = "\n".join(TABLE.split(sep="\n")[:-2])
    rows = report.partition_rows(names={}, printed=cut)
    assert rows[:-2] == cut.split(sep="\n")
    assert "not a whole table" in rows[-1]


def test_partition_rows_mark_a_partition_no_name_points_at() -> None:
    rows = report.partition_rows(names={}, printed=TABLE)
    assert rows[2].endswith("mmcblk0p3   <no name>")
    assert report.unreal_rows(held={}) == []


def test_partition_rows_match_no_name_without_a_whole_listing() -> None:
    rows = report.partition_rows(names=None, printed=TABLE)
    assert rows[:-2] == TABLE.split(sep="\n")[:-1]
    assert "did not arrive whole" in rows[-1]


def test_partition_rows_name_each_node_and_alias() -> None:
    rows = report.partition_rows(
        names=report.node_names(listing=LISTING), printed=TABLE
    )
    assert rows[0] == TABLE.split(maxsplit=1, sep="\n")[0]
    assert rows[1].split()[-2:] == ["node", "alias"]
    assert rows[2].split()[-2:] == ["mmcblk0p3", "lk_a_real"]
    assert rows[3].split()[-2:] == ["mmcblk0p13", "system"]
    assert rows[4].endswith("mmcblk0p17")
    assert rows[-3:] == [
        "",
        "names that point outside the partition table",
        "lk_a  /tmp/lk_a",
    ]


def test_system_a_rows() -> None:
    names = report.node_names(listing=LISTING)
    assert report.system_a_rows(
        names=names, needs=805257216, partitions=PARTITIONS
    ) == [
        ("system_a", f"/dev/block/mmcblk0p13, {786432 * 1024} bytes"),
        ("system_a spare", f"{786432 * 1024 - 805257216} bytes"),
    ]
    assert report.system_a_rows(names=names, needs=0, partitions=PARTITIONS) == [
        ("system_a", f"/dev/block/mmcblk0p13, {786432 * 1024} bytes")
    ]
    ((label, value),) = report.system_a_rows(names=None, needs=1, partitions=PARTITIONS)
    assert (label, "did not arrive whole" in value) == ("system_a", True)


def test_system_record() -> None:
    assert report.system_record(text="want 196596 6\n") == ("want", 196596 * 4096)
    assert report.system_record(text="") == ("", 0)
    assert report.system_record(text="want two") == ("", 0)


def test_the_dmesg_window_reads_any_uptime(*, tmp_path: pathlib.Path) -> None:
    sent: list[str] = []
    report.dot_details(asked=lambda *, command: sent.append(command) or "")
    (window,) = [command for command in sent if command.startswith("dmesg")]
    for stamp, want in (
        ("[    0.000000]", "0.000000"),
        ("[12345.678901]", "12345.678901"),
    ):
        fake = tmp_path / "dmesg"
        fake.write_text(f"#!/bin/sh\necho '{stamp} Booting Linux'\n")
        fake.chmod(0o755)
        said = subprocess.run(
            args=["sh", "-c", window],
            capture_output=True,
            check=True,
            env={"PATH": f"{tmp_path}:/usr/bin:/bin"},
            text=True,
        ).stdout.strip()
        assert said == want


def test_whole() -> None:
    assert report.whole(marker="done", said="a\ndone\nb") is None
    assert report.whole(marker="done", said="a\nb\ndone\n") == "a\nb"
    assert report.whole(marker="done", said="a\nb") is None
    assert report.whole(marker="done", said="") is None
