"""单战役的进度隔离文件工作区；本模块不重定向游戏写入。

prepare 必须在保存队列和在途写入静止的边界调用。只处理指定战役及
settings.menu_state/User.keymap，不读取其他战役，不允许 default 或保护备份。
baseline 是进度文件基线，不是完整游戏现场。working 供后续隔离后端使用。
"""

import hashlib
import json
import os
from pathlib import Path
import stat

from .return_journal import _write_synced


_ROOT_FILES = ("settings.menu_state", "User.keymap")
_MAX_FILE = 64 * 1024 * 1024
_MAX_TOTAL = 256 * 1024 * 1024
_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
             *(f"lpt{i}" for i in range(1, 10))}


def _campaign(value: str) -> None:
    if (not isinstance(value, str) or not value or value in (".", "..")
            or value[-1] in " ." or any(c in '<>:"/\\|?*' or ord(c) < 32 for c in value)
            or value.casefold() in {"default", "save-backups"}
            or value.split(".", 1)[0].casefold() in _RESERVED):
        raise ValueError("Invalid or protected campaign")


def _plain(path: Path) -> None:
    # 拒绝已存在的符号链接、junction 与其他重解析点；不穿过路径别名。
    for part in (path, *path.parents):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Reparse paths are not supported for save workspaces")


def _read(path: Path) -> bytes:
    _plain(path)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > _MAX_FILE:
        raise ValueError("Invalid or oversized save file")
    with path.open("rb") as stream:
        data = stream.read(_MAX_FILE + 1)
    after = path.stat()
    if (len(data) != before.st_size or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns):
        raise ValueError("Save file changed during capture")
    return data


def _inventory(root: Path, campaign: str) -> dict:
    _plain(root / campaign)
    if not (root / campaign).is_dir():
        raise ValueError("Campaign must be an existing directory")
    directories = [campaign]
    paths = []
    def failed(error):
        raise error
    for current, children, files in os.walk(root / campaign, onerror=failed, followlinks=False):
        for name in children:
            path = Path(current, name)
            _plain(path)
            directories.append(path.relative_to(root).as_posix())
        paths.extend(Path(current, name) for name in files)
        if len(paths) + len(directories) > 4096:
            raise ValueError("Too many save entries")
    paths.extend(root / name for name in _ROOT_FILES if (root / name).exists() or (root / name).is_symlink())
    files = {}
    total = 0
    for path in sorted(paths):
        data = _read(path)
        total += len(data)
        if total > _MAX_TOTAL:
            raise ValueError("Save workspace exceeds size limit")
        files[path.relative_to(root).as_posix()] = {
            "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    return {"files": files, "directories": sorted(directories)}


class SaveWorkspace:
    def __init__(self, root: Path, source: Path, campaign: str, inventory: dict):
        self.root, self.source = root, source
        self.campaign, self.inventory = campaign, inventory

    @classmethod
    def prepare(cls, source: Path, root: Path, *, campaign: str):
        _campaign(campaign)
        source, root = Path(source).absolute(), Path(root).absolute()
        _plain(source)
        _plain(root.parent)
        if any(p.casefold() in {"default", "save-backups"} for p in source.parts):
            raise ValueError("Protected source cannot be used for experiments")
        source, root = source.resolve(strict=True), root.resolve()
        if source == root or source in root.parents or root in source.parents:
            raise ValueError("Source and workspace must be disjoint")
        if root.exists():
            raise FileExistsError(root)
        inventory = _inventory(source, campaign)
        root.mkdir()
        for kind in ("baseline", "working"):
            for name in inventory["directories"]:
                (root / kind / name).mkdir(parents=True, exist_ok=True)
        for name, expected in inventory["files"].items():
            data = _read(source / name)
            if len(data) != expected["size"] or hashlib.sha256(data).hexdigest() != expected["sha256"]:
                raise ValueError("Save changed while preparing workspace")
            for kind in ("baseline", "working"):
                _write_synced(root / kind / name, data)
        if _inventory(source, campaign) != inventory:
            raise ValueError("Save tree changed while preparing workspace")
        manifest = {"version": 1, "source": str(source), "campaign": campaign,
                    "inventory": inventory}
        _write_synced(root / "manifest.json.tmp", json.dumps(manifest, ensure_ascii=False).encode("utf-8"))
        os.replace(root / "manifest.json.tmp", root / "manifest.json")
        return cls.open(root)

    @classmethod
    def open(cls, root: Path):
        root = Path(root).absolute()
        _plain(root / "manifest.json")
        with (root / "manifest.json").open("rb") as stream:
            data = stream.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise ValueError("Workspace manifest is too large")
        row = json.loads(data)
        if (not isinstance(row, dict) or type(row.get("version")) is not int or row["version"] != 1
                or not isinstance(row.get("source"), str) or not Path(row["source"]).is_absolute()):
            raise ValueError("Invalid workspace manifest")
        _campaign(row.get("campaign"))
        if any(p.casefold() in {"default", "save-backups"} for p in Path(row["source"]).parts):
            raise ValueError("Protected workspace source")
        if _inventory(root / "baseline", row["campaign"]) != row.get("inventory"):
            raise ValueError("Workspace baseline changed")
        return cls(root, Path(row["source"]), row["campaign"], row["inventory"])

    def verify_source_unchanged(self) -> None:
        if _inventory(self.source, self.campaign) != self.inventory:
            raise ValueError("Original progress changed")
