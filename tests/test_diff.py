import time

from dualbackup import Store
from dualbackup.cli import main


def test_diff_between_snapshots(tmp_path, capsys):
    src = tmp_path / "kho"
    src.mkdir()
    (src / "giu.txt").write_text("giữ", encoding="utf-8")
    (src / "sua.txt").write_text("v1", encoding="utf-8")
    (src / "xoa.txt").write_text("x", encoding="utf-8")
    store = Store(tmp_path / "bk")
    a, _ = store.backup(src, now=time.mktime((2026, 11, 1, 9, 0, 0, 0, 0, -1)))
    (src / "sua.txt").write_text("v2", encoding="utf-8")
    (src / "xoa.txt").unlink()
    (src / "moi.txt").write_text("mới", encoding="utf-8")
    b, _ = store.backup(src, now=time.mktime((2026, 11, 2, 9, 0, 0, 0, 0, -1)))
    assert store.diff(a.name, b.name) == {"added": ["moi.txt"], "removed": ["xoa.txt"], "changed": ["sua.txt"]}
    assert main(["--store", str(tmp_path / "bk"), "diff", a.name, b.name]) == 0
    assert "1 thêm, 1 xoá, 1 sửa" in capsys.readouterr().out
