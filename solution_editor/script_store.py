"""只保存操作序列；完整方案初始态与返回态由后续状态事务管理。"""

import hashlib
import json
import os
from pathlib import Path
import tempfile

from .timeline import SolutionTimeline, Step
from .script_limits import MAX_SCRIPT_BYTES


_FORMAT = "ootss-step-script"
_VERSION = 1
_MAX_BYTES = MAX_SCRIPT_BYTES


class ScriptConflict(Exception):
    """磁盘文件与编辑器读入时不一致，禁止静默覆盖。"""


def _read_bytes(path: Path) -> bytes:
    if path.stat().st_size > _MAX_BYTES:
        raise ValueError("Script file is too large")
    data = path.read_bytes()
    if len(data) > _MAX_BYTES:
        raise ValueError("Script file is too large")
    return data


def _fingerprint(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_script(path: Path) -> tuple[SolutionTimeline, str]:
    data = _read_bytes(Path(path))
    document = json.loads(data.decode("utf-8"))
    if isinstance(document,dict) and document.get('format')==_FORMAT and document.get('version')==2:
        from .recording_timeline import RecordingTimeline
        return RecordingTimeline.from_document(document),_fingerprint(data)
    if not isinstance(document, dict) or document.get("format") != _FORMAT or document.get("version") != _VERSION:
        raise ValueError("Unsupported script format or version")
    rows = document.get("steps")
    if not isinstance(rows, list):
        raise ValueError("Script steps must be an array")
    steps = []
    for row in rows:
        if not isinstance(row, dict) or set(row) not in ({"symbol"}, {"symbol", "wait_ms"}):
            raise ValueError("Invalid script step")
        steps.append(Step(row["symbol"], row.get("wait_ms")))
    return SolutionTimeline(steps), _fingerprint(data)


def write_script(path: Path, timeline: SolutionTimeline, *, expected_fingerprint: str | None) -> str:
    path = Path(path)
    if path.exists():
        if expected_fingerprint is None or _fingerprint(_read_bytes(path)) != expected_fingerprint:
            raise ScriptConflict("Script changed on disk; reload or choose another name")
    elif expected_fingerprint is not None:
        raise ScriptConflict("Script disappeared from disk")
    steps = []
    for step in timeline.steps:
        row = {"symbol": step.symbol}
        if step.wait_ms is not None:
            row["wait_ms"] = step.wait_ms
        steps.append(row)
    from .recording_timeline import RecordingTimeline
    document=(timeline.to_document() if isinstance(timeline,RecordingTimeline)
              else {"format": _FORMAT, "version": _VERSION, "steps": steps})
    data = (json.dumps(document,
                       ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(data) > _MAX_BYTES:
        raise ValueError("Script file is too large")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, prefix=".script-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        # Check once more after writing the temporary file to narrow the edit race.
        if path.exists():
            if expected_fingerprint is None or _fingerprint(_read_bytes(path)) != expected_fingerprint:
                raise ScriptConflict("Script changed while saving")
        elif expected_fingerprint is not None:
            raise ScriptConflict("Script disappeared while saving")
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    timeline.dirty = False
    return _fingerprint(data)
