"""Tìm ổ cứng ngoài theo nhãn ổ (Windows) và đẩy kho lên cloud bằng rclone."""

from __future__ import annotations

import os
import shutil
import string
import subprocess
from pathlib import Path


def find_drive_by_label(label: str) -> Path | None:
    """Trả về gốc ổ (vd. `E:\\`) có nhãn `label`, hoặc None. Chỉ chạy trên Windows."""
    if os.name != "nt":
        return None
    import ctypes

    k = ctypes.windll.kernel32  # type: ignore[attr-defined,unused-ignore]  # chỉ có trên Windows
    mask = k.GetLogicalDrives()
    for i, letter in enumerate(string.ascii_uppercase):
        if not mask >> i & 1:
            continue
        root = f"{letter}:\\"
        buf = ctypes.create_unicode_buffer(261)
        if k.GetVolumeInformationW(root, buf, 261, None, None, None, None, 0) and buf.value.upper() == label.upper():
            return Path(root)
    return None


def rclone_sync(store_root: Path, remote: str, rclone: str | None = None, dry_run: bool = False) -> int:
    """Đồng bộ thư mục kho lên remote rclone (vd. `gdrive:SaoLuu`). Trả về mã thoát của rclone.

    Kho là content-addressed và object không bao giờ bị sửa, nên `rclone sync` chỉ đẩy phần mới.
    """
    exe = rclone or shutil.which("rclone")
    if not exe:
        raise FileNotFoundError("không tìm thấy rclone trong PATH")
    cmd = [exe, "sync", str(store_root), remote, "--checksum", "--transfers", "4"]
    if dry_run:
        cmd.append("--dry-run")
    return subprocess.run(cmd, check=False).returncode
