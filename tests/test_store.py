import time

import pytest

from dualbackup import Store
from dualbackup.cli import main


def write(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def ts(day, hour=9):
    return time.mktime((2026, 11, day, hour, 0, 0, 0, 0, -1))


@pytest.fixture
def src(tmp_path):
    s = tmp_path / "kho"
    write(s / "hop-dong" / "HD-01.docx", "hợp đồng 01")
    write(s / "hop-dong" / "HD-01-ban-sao.docx", "hợp đồng 01")  # trùng nội dung
    write(s / "so-quy.xlsx", "thu chi")
    write(s / "~$so-quy.xlsx", "khoá tạm")
    return s


def test_backup_dedups_identical_content(src, tmp_path):
    store = Store(tmp_path / "bk")
    snap, new = store.backup(src, now=ts(1))
    assert len(snap.files) == 3
    assert new == 2  # hai file trùng nội dung chỉ lưu một object
    assert "~$so-quy.xlsx" not in snap.files


def test_second_backup_writes_only_changes(src, tmp_path):
    store = Store(tmp_path / "bk")
    store.backup(src, now=ts(1))
    write(src / "so-quy.xlsx", "thu chi tháng 11")
    _, new = store.backup(src, now=ts(2))
    assert new == 1
    assert len(store.list()) == 2


def test_restore_roundtrip(src, tmp_path):
    store = Store(tmp_path / "bk")
    store.backup(src, now=ts(1))
    out = tmp_path / "phuc-hoi"
    assert store.restore(out) == 3
    assert (out / "hop-dong" / "HD-01.docx").read_text(encoding="utf-8") == "hợp đồng 01"


def test_restore_old_version(src, tmp_path):
    store = Store(tmp_path / "bk")
    first, _ = store.backup(src, now=ts(1))
    write(src / "so-quy.xlsx", "đã sửa")
    store.backup(src, now=ts(2))
    out = tmp_path / "cu"
    store.restore(out, name=first.name, only="so-quy")
    assert (out / "so-quy.xlsx").read_text(encoding="utf-8") == "thu chi"
    assert not (out / "hop-dong").exists()


def test_restore_refuses_non_empty_target(src, tmp_path):
    store = Store(tmp_path / "bk")
    store.backup(src, now=ts(1))
    write(tmp_path / "dang-co" / "x.txt", "đừng đè")
    with pytest.raises(FileExistsError):
        store.restore(tmp_path / "dang-co")


def test_verify_detects_corruption_and_loss(src, tmp_path):
    store = Store(tmp_path / "bk")
    snap, _ = store.backup(src, now=ts(1))
    assert store.verify().ok
    objs = sorted(store.objects.glob("*/*"))
    objs[0].write_bytes(b"bit rot")
    objs[1].unlink()
    rep = store.verify()
    assert not rep.ok and rep.corrupt and rep.missing
    quick = store.verify(deep=False)
    assert quick.missing and not quick.corrupt


def test_prune_and_gc(src, tmp_path):
    store = Store(tmp_path / "bk")
    for day in range(1, 11):
        write(src / "so-quy.xlsx", f"ngày {day}")
        store.backup(src, now=ts(day))
    removed = store.prune(keep_last=2, keep_daily=3, now=ts(10, 12))
    names = [s.name for s in store.list()]
    assert names == ["20261108-090000", "20261109-090000", "20261110-090000"]
    assert len(removed) == 7
    used = {m["sha256"] for s in store.list() for m in s.files.values()}
    assert {o.name for o in store.objects.glob("*/*")} == used
    assert store.verify().ok


def test_cli_backup_verify_restore(src, tmp_path, capsys):
    bk = str(tmp_path / "bk")
    assert main(["--store", bk, "backup", str(src)]) == 0
    assert main(["--store", bk, "verify"]) == 0
    assert main(["--store", bk, "list"]) == 0
    assert main(["--store", bk, "restore", str(tmp_path / "r")]) == 0
    out = capsys.readouterr().out
    assert "Đã khôi phục 3 file" in out


def test_empty_store_errors(tmp_path):
    with pytest.raises(LookupError):
        Store(tmp_path / "rong").get()
