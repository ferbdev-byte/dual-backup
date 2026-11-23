"""Dòng lệnh dualbackup."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from . import __version__
from .store import Store
from .targets import find_drive_by_label, rclone_sync


def _mb(n: int) -> str:
    return f"{n / 1024 / 1024:.1f} MB"


def _resolve_store(args: argparse.Namespace) -> Store:
    if args.drive_label:
        root = find_drive_by_label(args.drive_label)
        if root is None:
            sys.exit(f"Không thấy ổ có nhãn {args.drive_label!r}. Cắm ổ sao lưu vào rồi chạy lại.")
        return Store(root / "dualbackup")
    if not args.store:
        sys.exit("Cần --store hoặc --drive-label")
    return Store(args.store)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="dualbackup", description="Sao lưu có kiểm chứng ra ổ ngoài và cloud.")
    p.add_argument("--version", action="version", version=f"dualbackup {__version__}")
    p.add_argument("--store", help="thư mục kho sao lưu")
    p.add_argument("--drive-label", help="tự tìm ổ ngoài theo nhãn (vd. SAOLUU) và dùng kho trên đó")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("backup", help="sao lưu một thư mục")
    b.add_argument("source")
    b.add_argument("--remote", help="đẩy kho lên rclone remote sau khi sao lưu, vd. gdrive:SaoLuu")
    b.add_argument("--keep-last", type=int, default=7)
    b.add_argument("--keep-daily", type=int, default=30)

    sub.add_parser("list", help="liệt kê các bản sao lưu")

    v = sub.add_parser("verify", help="kiểm chứng một bản (mặc định bản mới nhất)")
    v.add_argument("name", nargs="?")
    v.add_argument("--quick", action="store_true", help="chỉ kiểm có mặt, không băm lại")

    r = sub.add_parser("restore", help="khôi phục ra thư mục rỗng")
    r.add_argument("target")
    r.add_argument("--name")
    r.add_argument("--only", help="chỉ khôi phục đường dẫn bắt đầu bằng chuỗi này")

    args = p.parse_args(argv)
    store = _resolve_store(args)

    if args.cmd == "backup":
        snap, new = store.backup(args.source)
        print(f"Đã sao lưu {snap.name}: {len(snap.files)} file, {_mb(snap.total_bytes)}, {new} object mới")
        rep = store.verify(snap.name)
        if not rep.ok:
            print(f"LỖI kiểm chứng: thiếu {len(rep.missing)}, hỏng {len(rep.corrupt)}", file=sys.stderr)
            return 2
        removed = store.prune(args.keep_last, args.keep_daily)
        if removed:
            print(f"Đã dọn {len(removed)} bản cũ")
        if args.remote:
            code = rclone_sync(store.root, args.remote)
            print("Đã đẩy lên cloud" if code == 0 else f"rclone lỗi (mã {code})")
            return 0 if code == 0 else 3
        return 0

    if args.cmd == "list":
        for s in store.list():
            when = datetime.fromtimestamp(s.created).strftime("%d/%m/%Y %H:%M")
            print(f"{s.name}  {when}  {len(s.files):>6} file  {_mb(s.total_bytes):>10}")
        return 0

    if args.cmd == "verify":
        rep = store.verify(args.name, deep=not args.quick)
        print(f"Đã kiểm {rep.checked} file — thiếu {len(rep.missing)}, hỏng {len(rep.corrupt)}")
        for x in rep.missing[:20]:
            print("  thiếu:", x)
        for x in rep.corrupt[:20]:
            print("  hỏng: ", x)
        return 0 if rep.ok else 2

    n = store.restore(Path(args.target), args.name, args.only)
    print(f"Đã khôi phục {n} file vào {args.target} (đã kiểm SHA-256 từng file)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
