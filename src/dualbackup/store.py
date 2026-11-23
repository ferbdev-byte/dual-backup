"""Kho sao lưu kiểu content-addressed.

Bố cục trên đĩa:

    <kho>/
      objects/ab/abcdef...      nội dung file, đặt tên theo SHA-256 (file giống nhau chỉ lưu một lần)
      snapshots/20261123-090000.json   danh sách file của một lần sao lưu: đường dẫn, cỡ, sha256, mtime

Vì mỗi object mang tên chính là SHA-256 của nó, việc kiểm chứng chỉ là băm lại và so tên.
Một bản sao lưu chưa từng khôi phục thử thì chưa được coi là bản sao lưu: xem `verify` và `restore`.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SKIP_NAMES = {"Thumbs.db", "desktop.ini", ".DS_Store"}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(1 << 20):
            h.update(block)
    return h.hexdigest()


@dataclass
class Snapshot:
    name: str
    created: float
    source: str
    files: dict[str, dict[str, Any]] = field(default_factory=dict)  # rel_path -> {size, sha256, mtime}

    @property
    def total_bytes(self) -> int:
        return sum(f["size"] for f in self.files.values())


@dataclass
class VerifyReport:
    checked: int = 0
    missing: list[str] = field(default_factory=list)
    corrupt: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing and not self.corrupt


# Bí danh kiểu: trong class Store, tên `list` bị phương thức Store.list che mất
NameList = list[str]


class Store:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.objects = self.root / "objects"
        self.snapshots = self.root / "snapshots"

    # ---------- ghi ----------
    def _object_path(self, digest: str) -> Path:
        return self.objects / digest[:2] / digest

    def _put(self, src: Path, digest: str) -> bool:
        """Chép file vào kho nếu chưa có. Trả về True nếu thực sự ghi mới."""
        dst = self._object_path(digest)
        if dst.exists():
            return False
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_suffix(".tmp")
        shutil.copyfile(src, tmp)
        if _sha256(tmp) != digest:  # file nguồn bị sửa trong lúc đang chép
            tmp.unlink(missing_ok=True)
            raise OSError(f"nội dung thay đổi trong lúc sao lưu: {src}")
        os.replace(tmp, dst)
        return True

    def backup(self, source: str | Path, now: float | None = None) -> tuple[Snapshot, int]:
        """Sao lưu cả thư mục. Trả về (snapshot, số object mới ghi)."""
        source = Path(source)
        if not source.is_dir():
            raise NotADirectoryError(source)
        now = time.time() if now is None else now
        snap = Snapshot(time.strftime("%Y%m%d-%H%M%S", time.localtime(now)), now, str(source))
        written = 0
        for dirpath, dirnames, filenames in os.walk(source):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for name in filenames:
                if name in SKIP_NAMES or name.startswith("~$"):
                    continue
                full = Path(dirpath) / name
                rel = full.relative_to(source).as_posix()
                st = full.stat()
                digest = _sha256(full)
                written += self._put(full, digest)
                snap.files[rel] = {"size": st.st_size, "sha256": digest, "mtime": st.st_mtime}
        self.snapshots.mkdir(parents=True, exist_ok=True)
        path = self.snapshots / f"{snap.name}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(snap.__dict__, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, path)
        return snap, written

    # ---------- đọc ----------
    def list(self) -> list[Snapshot]:
        if not self.snapshots.is_dir():
            return []
        out = []
        for p in sorted(self.snapshots.glob("*.json")):
            out.append(Snapshot(**json.loads(p.read_text(encoding="utf-8"))))
        return out

    def get(self, name: str | None = None) -> Snapshot:
        snaps = self.list()
        if not snaps:
            raise LookupError("kho chưa có bản sao lưu nào")
        if name is None:
            return snaps[-1]
        for s in snaps:
            if s.name == name:
                return s
        raise LookupError(f"không có bản {name}")

    def verify(self, name: str | None = None, deep: bool = True) -> VerifyReport:
        """Kiểm mọi object mà snapshot dùng: có mặt, và (deep) băm lại đúng tên."""
        rep = VerifyReport()
        for rel, meta in self.get(name).files.items():
            rep.checked += 1
            obj = self._object_path(meta["sha256"])
            if not obj.exists():
                rep.missing.append(rel)
            elif deep and _sha256(obj) != meta["sha256"]:
                rep.corrupt.append(rel)
        return rep

    def restore(self, target: str | Path, name: str | None = None, only: str | None = None) -> int:
        """Khôi phục ra thư mục `target` (phải rỗng hoặc chưa có). Không ghi đè file đang tồn tại."""
        target = Path(target)
        if target.exists() and any(target.iterdir()):
            raise FileExistsError(f"thư mục đích không rỗng: {target}")
        count = 0
        for rel, meta in self.get(name).files.items():
            if only and not rel.startswith(only):
                continue
            dst = target / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self._object_path(meta["sha256"]), dst)
            os.utime(dst, (meta["mtime"], meta["mtime"]))
            if _sha256(dst) != meta["sha256"]:
                raise OSError(f"khôi phục sai nội dung: {rel}")
            count += 1
        return count

    def diff(self, old: str, new: str) -> dict[str, NameList]:
        """So hai bản sao lưu: file thêm mới, bị xoá, và bị sửa nội dung."""
        a, b = self.get(old).files, self.get(new).files
        return {
            "added": sorted(b.keys() - a.keys()),
            "removed": sorted(a.keys() - b.keys()),
            "changed": sorted(k for k in a.keys() & b.keys() if a[k]["sha256"] != b[k]["sha256"]),
        }

    # ---------- dọn ----------
    def prune(self, keep_last: int = 7, keep_daily: int = 30, now: float | None = None) -> NameList:
        """Giữ `keep_last` bản mới nhất và một bản mỗi ngày trong `keep_daily` ngày. Trả về tên các bản đã xoá."""
        now = time.time() if now is None else now
        snaps = self.list()
        keep = {s.name for s in snaps[-keep_last:]} if keep_last else set()
        seen_days = set()
        for s in reversed(snaps):
            day = s.name[:8]
            if now - s.created <= keep_daily * 86400 and day not in seen_days:
                keep.add(s.name)
                seen_days.add(day)
        removed = [s.name for s in snaps if s.name not in keep]
        for n in removed:
            (self.snapshots / f"{n}.json").unlink()
        self.gc()
        return removed

    def gc(self) -> int:
        """Xoá object không còn snapshot nào dùng."""
        used = {m["sha256"] for s in self.list() for m in s.files.values()}
        removed = 0
        if self.objects.is_dir():
            for obj in self.objects.glob("*/*"):
                if obj.name not in used:
                    obj.unlink()
                    removed += 1
        return removed
