"""原生战役文件工程。调用方须先完成游戏保存，并提供新鲜的当前战役确认。"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid

from .return_journal import _valid_build, _write_synced
from .save_workspace import _campaign, _plain, _read
from .game_builds import compatible_saved_build


def _name(value):
    if isinstance(value, str) and value.casefold() == 'default':
        return  # 产品允许原存档；开发接入端另行拒绝以受保护存档实验。
    _campaign(value)


def _tree(root):
    root = Path(root)
    _plain(root)
    if not root.is_dir(): raise ValueError('Expected campaign directory')
    rows, directories, total = {}, [], 0
    for current, children, files in os.walk(root, followlinks=False, onerror=lambda e: (_ for _ in ()).throw(e)):
        current = Path(current)
        _plain(current)
        directories.append(current.relative_to(root).as_posix())
        for name in children: _plain(current / name)
        for name in files:
            p = current / name
            data = _read(p)
            total += len(data)
            if total > 256 * 1024 * 1024: raise ValueError('Campaign too large')
            rows[p.relative_to(root).as_posix()] = {'bytes':len(data), 'sha256':hashlib.sha256(data).hexdigest()}
        if len(rows) + len(directories) > 4096: raise ValueError('Too many campaign entries')
    return {'directories':sorted(directories), 'files':rows}


def _copy(source, target, inventory, *, owner=None, exclude_owner=False):
    target.mkdir()
    if owner is not None: _publish(target / '.ootss-editor-owner.json', owner)
    for name in inventory['directories']:
        (target / name).mkdir(exist_ok=True, parents=True)
    for name, row in inventory['files'].items():
        data = _read(source / name)
        if len(data) != row['bytes'] or hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('Campaign changed during copy')
        _write_synced(target / name, data)
    actual = _tree(target)
    if owner is not None: actual['files'].pop('.ootss-editor-owner.json', None)
    source_inventory = _tree(source)
    if exclude_owner: source_inventory['files'].pop('.ootss-editor-owner.json', None)
    if source_inventory != inventory or actual != inventory:
        raise ValueError('Campaign copy was not stable')


def _json(path):
    _plain(path)
    with path.open('rb') as stream: data = stream.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024: raise ValueError('Manifest too large')
    row = json.loads(data)
    if not isinstance(row, dict): raise ValueError('Invalid manifest')
    return row


def _publish(path, row):
    fd, name = tempfile.mkstemp(prefix=path.name + '-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write((json.dumps(row, ensure_ascii=False, sort_keys=True)+'\n').encode('utf-8'))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


@contextmanager
def _lock(root):
    import msvcrt
    with root.with_name(root.name + '.lock').open('a+b') as stream:
        if stream.seek(0, os.SEEK_END) == 0: stream.write(b'0'); stream.flush()
        stream.seek(0)
        try: msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error: raise RuntimeError('Project already controlled') from error
        try: yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


class CampaignProject:
    def __init__(self, root, row, *, game_sha256=None):
        self.root, self.row = root, row
        self.game_sha256 = game_sha256 if game_sha256 is not None else row['game_sha256']

    @classmethod
    def create(cls, root, name, save_root, campaign, *, game_sha256):
        _name(campaign)
        if not _valid_build(game_sha256) or not isinstance(name,str) or not 0 < len(name.strip()) <= 128:
            raise ValueError('Invalid project identity')
        root, save_root = Path(root).absolute(), Path(save_root).absolute()
        _plain(root.parent); _plain(save_root)
        if any(p.casefold() == 'save-backups' for p in save_root.parts): raise ValueError('Protected backup')
        root, save_root = root.resolve(), save_root.resolve()
        if root == save_root or root in save_root.parents or save_root in root.parents:
            raise ValueError('Project and saves must be disjoint')
        with _lock(root):
            inventory = _tree(save_root / campaign)
            root.mkdir()
            (root / 'initial').mkdir()
            _copy(save_root / campaign, root / 'initial' / campaign, inventory)
            row = {'format':'ootss-campaign-project','version':1,'id':uuid.uuid4().hex,
                   'name':name,'game_sha256':game_sha256,'campaign':campaign,'inventory':inventory}
            _publish(root / 'project.json', row)
        return cls.open(root, game_sha256=game_sha256)

    @classmethod
    def open(cls, root, *, game_sha256, verify_initial=True):
        root = Path(root).resolve(strict=True)
        row = _json(root / 'project.json')
        if (row.get('format') != 'ootss-campaign-project' or type(row.get('version')) is not int
            or row['version'] != 1 or not _valid_build(game_sha256) or not compatible_saved_build(row.get('game_sha256'),game_sha256)
            or not isinstance(row.get('id'),str) or not re.fullmatch('[0-9a-f]{32}',row['id'])):
            raise ValueError('Unsupported project identity or game build')
        _name(row.get('campaign'))
        if verify_initial and _tree(root / 'initial' / row['campaign']) != row.get('inventory'):
            raise ValueError('Initial campaign changed')
        return cls(root, row, game_sha256=game_sha256)

    def pending(self):
        path = self.root / 'session.json'
        if not path.exists(): return None
        row = _json(path)
        if (row.get('project_id') != self.row['id'] or row.get('phase') not in ('preparing','prepared','active','closed')
            or not isinstance(row.get('session_id'),str) or not re.fullmatch('[0-9a-f]{32}', row['session_id'])
            or row.get('temporary_campaign') != 'ootss_editor_' + row['session_id']
            or not isinstance(row.get('save_root'),str) or not Path(row['save_root']).is_absolute()):
            raise ValueError('Invalid session record')
        _name(row.get('return_campaign'))
        if row['return_campaign'].casefold().startswith('ootss_editor_'):
            raise ValueError('Return campaign cannot be a tool temporary')
        if row['phase']=='closed':return None
        from .identity import environment_id
        if row.get('environment')!=environment_id():
            raise ValueError('会话设备／用户环境无法核验；请在原环境安全退出，保留全部材料。')
        from .restore_events import check_session
        check_session(row)
        return row

    def prepare_session(self, save_root, *, return_campaign, checkpoint=None):
        _name(return_campaign)
        if return_campaign.casefold().startswith('ootss_editor_'):
            raise ValueError('Return campaign cannot be a tool temporary')
        save_root = Path(save_root).absolute()
        _plain(save_root / return_campaign)
        save_root = save_root.resolve(strict=True)
        if any(p.casefold() == 'save-backups' for p in save_root.parts): raise ValueError('Protected backup')
        with _lock(self.root):
            if self.pending() is not None: raise FileExistsError('Unresolved temporary campaign')
            fresh = self.open(self.root, game_sha256=self.game_sha256)
            source, inventory = fresh.root / 'initial' / self.row['campaign'], fresh.row['inventory']
            if checkpoint is not None:
                from .delay_checkpoints import Checkpoints
                source, inventory = Checkpoints(fresh).resolve(checkpoint)
            sid = uuid.uuid4().hex
            from .identity import environment_id
            row = {'project_id':self.row['id'],'session_id':sid,'save_root':str(save_root),'environment':environment_id(),
                   'return_campaign':return_campaign,'temporary_campaign':'ootss_editor_' + sid,'phase':'preparing'}
            _publish(self.root / 'session.json', row)
            target = save_root / row['temporary_campaign']
            _copy(source, target, inventory,
                  owner={'project_id':row['project_id'],'session_id':sid})
            row['phase'] = 'prepared'
            _publish(self.root / 'session.json', row)
            return row

    def confirm_loaded(self, current_campaign):
        with _lock(self.root):
            row = self.pending()
            if row is None or row['phase'] != 'prepared' or current_campaign != row['temporary_campaign']:
                raise ValueError('Temporary campaign load was not confirmed')
            row['phase'] = 'active'
            _publish(self.root / 'session.json', row)

    def finish_session(self, *, current_campaign):
        with _lock(self.root):
            row = self.pending()
            if row is None: return
            if current_campaign != row['return_campaign']:
                raise ValueError('Original campaign must be loaded before cleanup')
            save_root = Path(row['save_root']).resolve(strict=True)
            target = save_root / row['temporary_campaign']
            if target.exists():
                _plain(target)
                if target.resolve().parent != save_root or not target.name.startswith('ootss_editor_'):
                    raise ValueError('Unsafe cleanup target')
                expected = {'project_id':row['project_id'],'session_id':row['session_id']}
                if _json(target / '.ootss-editor-owner.json') != expected:
                    raise ValueError('Temporary campaign ownership changed')
                for p in target.rglob('*'): _plain(p)
                shutil.rmtree(target)  # 已核对绝对路径、直接父目录、唯一名称和归属。
            row['phase'] = 'closed'
            _publish(self.root / 'session.json', row)
