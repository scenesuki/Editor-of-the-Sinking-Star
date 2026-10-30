"""工程内独立脚本草稿；不覆盖正式脚本或固定存档起点。"""
import json
import re

from .campaign_project import _lock, _publish
from .recording_timeline import RecordingTimeline
from .save_workspace import _plain
from .script_store import ScriptConflict
from .script_limits import MAX_SCRIPT_BYTES


def _path(project):
    return project.root / 'recovery-script.json'


def _read(project):
    path = _path(project)
    if not path.exists():
        return None
    _plain(path)
    with path.open('rb') as stream:
        data = stream.read(MAX_SCRIPT_BYTES + 1)
    if len(data) > MAX_SCRIPT_BYTES:
        raise ValueError('恢复草稿过大，文件已保留。')
    row = json.loads(data)
    if (not isinstance(row, dict)
        or set(row) != {'format', 'version', 'project_id', 'base_fingerprint', 'document'}
        or row['format'] != 'ootss-script-recovery' or row['version'] != 1
        or row['project_id'] != project.row['id']
        or (row['base_fingerprint'] is not None
            and (not isinstance(row['base_fingerprint'], str)
                 or not re.fullmatch('[0-9a-f]{64}', row['base_fingerprint'])))):
        raise ValueError('恢复草稿身份不匹配，文件已保留。')
    RecordingTimeline.from_document(row['document'])
    return row


def preserve(project, timeline, fingerprint):
    document = RecordingTimeline.from_timeline(timeline).to_document()
    row = dict(format='ootss-script-recovery', version=1, project_id=project.row['id'],
               base_fingerprint=fingerprint, document=document)
    with _lock(project.root):
        previous = _read(project)
        if previous != row:
            _publish(_path(project), row)
    return _path(project)


def restore(project, saved, fingerprint):
    row = _read(project)
    if row is None:
        return None
    # 保存成功、草稿删除中断时，正式稿相同即可使用正式稿。
    if row['document'] == RecordingTimeline.from_timeline(saved).to_document():
        return None
    if row['base_fingerprint'] != fingerprint:
        raise ScriptConflict(f'恢复草稿与磁盘脚本冲突，两份均已保留：{_path(project)}')
    timeline = RecordingTimeline.from_document(row['document'])
    timeline.dirty = True
    return timeline


def clear(project):
    with _lock(project.root):
        if _read(project) is not None:
            _path(project).unlink()
