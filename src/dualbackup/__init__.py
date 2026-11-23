"""dualbackup — sao lưu chống trùng, có manifest SHA-256, khôi phục và kiểm chứng được."""

from .store import Snapshot, Store, VerifyReport

__all__ = ["Snapshot", "Store", "VerifyReport"]
__version__ = "0.2.0"
