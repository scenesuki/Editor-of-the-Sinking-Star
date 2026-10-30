"""进入方案前的返回态材料容器；不负责捕获、隔离或恢复游戏。"""

import hashlib
import json
import os
from pathlib import Path


_MAX_CAPTURE = 1024 * 1024 * 1024
_FORMAT_VERSION = 1


def _valid_build(value: str) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _valid_capture_format(value: str) -> bool:
    return isinstance(value, str) and 0 < len(value) <= 128 and value.isascii() and all(c.isalnum() or c in "-_." for c in value)


def _write_synced(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


class ReturnJournal:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def prepare(self, capture: bytes, *, game_sha256: str, capture_format: str) -> None:
        if not isinstance(capture, bytes) or not 0 < len(capture) <= _MAX_CAPTURE:
            raise ValueError("Invalid return capture")
        if not _valid_build(game_sha256) or not _valid_capture_format(capture_format):
            raise ValueError("Invalid game build or capture format")
        self.root.mkdir(exist_ok=False)
        payload = self.root / "return.bin"
        _write_synced(self.root / "return.bin.tmp", capture)
        os.replace(self.root / "return.bin.tmp", payload)
        manifest = {
            "format_version": _FORMAT_VERSION,
            "game_sha256": game_sha256,
            "capture_format": capture_format,
            "payload_size": len(capture),
            "payload_sha256": hashlib.sha256(capture).hexdigest(),
        }
        encoded = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        _write_synced(self.root / "pending.json.tmp", encoded)
        os.replace(self.root / "pending.json.tmp", self.root / "pending.json")
        self.read_pending(game_sha256=game_sha256, capture_format=capture_format)

    def read_pending(self, *, game_sha256: str, capture_format: str) -> bytes:
        if not _valid_build(game_sha256) or not _valid_capture_format(capture_format):
            raise ValueError("Invalid game build or capture format")
        manifest = json.loads((self.root / "pending.json").read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or manifest.get("format_version") != _FORMAT_VERSION:
            raise ValueError("Unsupported return journal")
        if manifest.get("game_sha256") != game_sha256 or manifest.get("capture_format") != capture_format:
            raise ValueError("Return journal belongs to another game build or capture format")
        size = manifest.get("payload_size")
        digest = manifest.get("payload_sha256")
        if type(size) is not int or not 0 < size <= _MAX_CAPTURE or not _valid_build(digest):
            raise ValueError("Invalid return journal manifest")
        payload = self.root / "return.bin"
        if payload.stat().st_size != size:
            raise ValueError("Return capture length changed")
        data = payload.read_bytes()
        if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("Return capture checksum changed")
        return data

    def mark_completed(self, *, game_sha256: str, capture_format: str) -> None:
        """调用者已恢复现场并完成隔离收尾后，归档标识并保留返回材料。"""
        self.read_pending(game_sha256=game_sha256, capture_format=capture_format)
        completed = self.root / "completed.json"
        if completed.exists():
            raise FileExistsError("Return journal already completed")
        os.rename(self.root / "pending.json", completed)
