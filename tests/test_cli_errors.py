import pytest

from dualbackup import Store
from dualbackup.cli import main


def _src(tmp_path):
    s = tmp_path / "kho"
    (s / "hop-dong").mkdir(parents=True)
    (s / "hop-dong" / "HD-01.docx").write_text("hợp đồng", encoding="utf-8")
    (s / "so-quy.xlsx").write_text("thu chi", encoding="utf-8")
    return s


def test_verify_returns_2_on_corruption(tmp_path, capsys):
    bk = tmp_path / "bk"
    assert main(["--store", str(bk), "backup", str(_src(tmp_path))]) == 0
    next(Store(bk).objects.glob("*/*")).write_bytes(b"hong")
    assert main(["--store", str(bk), "verify"]) == 2
    assert "hỏng 1" in capsys.readouterr().out
    assert main(["--store", str(bk), "verify", "--quick"]) == 0  # chỉ kiểm có mặt


def test_restore_only_subfolder(tmp_path, capsys):
    bk = tmp_path / "bk"
    main(["--store", str(bk), "backup", str(_src(tmp_path))])
    assert main(["--store", str(bk), "restore", str(tmp_path / "r"), "--only", "hop-dong"]) == 0
    assert (tmp_path / "r" / "hop-dong" / "HD-01.docx").exists()
    assert not (tmp_path / "r" / "so-quy.xlsx").exists()


def test_needs_store_or_label():
    with pytest.raises(SystemExit) as e:
        main(["list"])
    assert "Cần --store hoặc --drive-label" in str(e.value.code)


def test_missing_drive_label_exits_with_message():
    with pytest.raises(SystemExit) as e:
        main(["--drive-label", "KHONG-CO-O-NAY", "list"])
    assert "KHONG-CO-O-NAY" in str(e.value.code)


def test_remote_without_rclone_reports(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: None)
    with pytest.raises(FileNotFoundError):
        main(["--store", str(tmp_path / "bk"), "backup", str(_src(tmp_path)), "--remote", "gdrive:X"])
