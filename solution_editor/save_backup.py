"""完整存档备份／恢复：源与副本复核、恢复前备份、持久事务记录。"""
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import uuid
import ctypes
from ctypes import wintypes as w

from .campaign_project import _publish,_json
from .save_workspace import _plain
from .identity import environment_id
from .paths import paths
from .app_lease import EditorLease

GAME_FOLDER='Order of the Sinking Star'


def canonical(value):
    p=Path(value).absolute()
    for parent in [p,*p.parents]:
        if parent.exists() or parent.is_symlink():_plain(parent)
    return p.resolve()


def disjoint(a,b):
    if a==b or a in b.parents or b in a.parents:raise ValueError('Save, backup and recovery directories must be disjoint.')


def quiet_game():
    from .campaign_connection import process_rows
    if any(name.casefold() in ('sinking_star.exe','ssekeyworker.exe') for _,name in process_rows()):
        raise ValueError('Close the game and editor before backing up or restoring saves.')


def default_save_root():
    shell=ctypes.WinDLL('shell32');ole=ctypes.WinDLL('ole32')
    shell.SHGetKnownFolderPath.argtypes=[ctypes.c_void_p,w.DWORD,w.HANDLE,ctypes.POINTER(w.LPWSTR)]
    ole.CoTaskMemFree.argtypes=[ctypes.c_void_p]
    guid=ctypes.create_string_buffer(uuid.UUID('4c5c32ff-bb9d-43b0-b5b4-2d72e54eaaa4').bytes_le)
    result=w.LPWSTR()
    if shell.SHGetKnownFolderPath(guid,0,None,ctypes.byref(result))!=0:
        raise OSError('Cannot locate Windows Saved Games. Choose the game save directory manually.')
    try:return Path(result.value)/GAME_FOLDER
    finally:ole.CoTaskMemFree(ctypes.cast(result,ctypes.c_void_p))


def inventory(root):
    root=canonical(root)
    if not root.is_dir():raise ValueError('Save directory does not exist.')
    files={};directories=[];total=0
    for current,children,names in os.walk(root,followlinks=False,onerror=lambda e:(_ for _ in ()).throw(e)):
        current=Path(current);_plain(current);directories.append(current.relative_to(root).as_posix())
        for name in children:_plain(current/name)
        for name in names:
            p=current/name;_plain(p);before=p.stat();digest=hashlib.sha256()
            if not p.is_file():raise ValueError('Unsupported save entry.')
            with p.open('rb') as stream:
                for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
            after=p.stat()
            if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('Save changed while reading.')
            total+=after.st_size
            if total>8*1024**3 or len(files)+len(directories)>50000:raise ValueError('Save directory exceeds preview limits.')
            files[p.relative_to(root).as_posix()]=dict(bytes=after.st_size,sha256=digest.hexdigest())
    return dict(directories=sorted(directories),files=files)


def copy_verified(source,target,tree):
    target.mkdir()
    for name in tree['directories']:(target/name).mkdir(parents=True,exist_ok=True)
    for name in tree['files']:shutil.copyfile(source/name,target/name)
    if inventory(source)!=tree or inventory(target)!=tree:raise ValueError('Backup copy was not stable; files are preserved.')


def register_project(root):
    path=paths().config/'known-projects.json';path.parent.mkdir(parents=True,exist_ok=True)
    rows=json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    value=str(canonical(root))
    if value not in rows:rows.append(value);_publish(path,rows)


def known_projects():
    roots={p.parent for p in paths().projects.glob('*/project.json')}
    path=paths().config/'known-projects.json'
    if path.exists():
        if path.stat().st_size>1024*1024:raise ValueError('Project registry too large.')
        row=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(row,list) or not all(isinstance(p,str) and Path(p).is_absolute() for p in row):raise ValueError('Invalid project registry.')
        roots.update(Path(p) for p in row)
    return sorted(roots)


class SaveBackupStore:
    def __init__(self,root,*,events=None,guard=quiet_game,lease_factory=EditorLease,project_roots=None):
        self.root=canonical(root);self.events=canonical(events or paths().config/'restore-events')
        self.guard=guard;self.lease_factory=lease_factory;self.project_roots=project_roots

    def _target(self,root):
        target=canonical(root)
        parts=[p.casefold() for p in target.parts]
        installed=any(parts[i:i+2]==['steamapps','common'] for i in range(len(parts)-1)) or (target/'sinking_star.exe').exists()
        if target.name.casefold()!=GAME_FOLDER.casefold() or installed:raise ValueError('Choose the Order of the Sinking Star save folder, not its parent or Steam installation.')
        disjoint(target,self.root);disjoint(target,self.events)
        return target

    def _backup(self,target):
        self.guard();tree=inventory(target);self.root.mkdir(parents=True,exist_ok=True)
        sid=uuid.uuid4().hex;name='backup-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+sid[:8]
        stage=self.root/('.preparing-'+sid);stage.mkdir()
        copy_verified(target,stage/'snapshot',tree);self.guard()
        _publish(stage/'backup.json',dict(format='ootss-save-backup',version=1,id=sid,created=datetime.now(timezone.utc).isoformat(),source=str(target),environment=environment_id(),inventory=tree))
        destination=self.root/name
        if destination.exists():raise FileExistsError(destination)
        stage.rename(destination);return destination

    def backup(self,source):
        target=self._target(source);self.guard()
        with self.lease_factory():return self._backup(target)

    def verify(self,backup):
        backup=canonical(backup);manifest=backup/'backup.json';_plain(manifest)
        if manifest.stat().st_size>32*1024*1024:raise ValueError('Backup manifest too large.')
        row=json.loads(manifest.read_text(encoding='utf-8'))
        if (not isinstance(row,dict) or row.get('format')!='ootss-save-backup' or row.get('version')!=1
            or not isinstance(row.get('id'),str) or not re.fullmatch('[0-9a-f]{32}',row['id'])):raise ValueError('Invalid backup format.')
        if row.get('inventory')!=inventory(backup/'snapshot'):raise ValueError('Backup integrity check failed.')
        return row

    def list(self):
        rows=[]
        for path in sorted(self.root.glob('backup-*'),reverse=True):
            try:
                manifest=canonical(path)/'backup.json';_plain(manifest)
                if manifest.stat().st_size>32*1024*1024:continue
                row=json.loads(manifest.read_text(encoding='utf-8'))
                if row.get('format')!='ootss-save-backup' or row.get('version')!=1:continue
                rows.append(dict(path=str(path),created=row.get('created',''),source=row.get('source','')))
            except (OSError,ValueError,AttributeError):continue
        return rows

    def _sessions(self,target):
        rows=[]
        for root in (known_projects() if self.project_roots is None else self.project_roots):
            root=canonical(root)
            if not (root/'session.json').exists() or not (root/'project.json').exists():continue
            row=_json(root/'session.json');project=_json(root/'project.json')
            if (row.get('phase') in ('preparing','prepared','active') and row.get('environment')==environment_id()
                and row.get('project_id')==project.get('id') and isinstance(row.get('session_id'),str)
                and re.fullmatch('[0-9a-f]{32}',row['session_id']) and isinstance(row.get('save_root'),str)
                and row.get('temporary_campaign')=='ootss_editor_'+row['session_id']
                and canonical(row['save_root'])==target):
                rows.append(dict(root=str(root),session_id=row['session_id'],project_id=row['project_id']))
        return rows

    def _finish(self,event):
        for item in event['projects']:
            root=canonical(item['root']);path=root/'session.json';row=_json(path)
            project=_json(root/'project.json')
            if (row.get('session_id')!=item['session_id'] or row.get('project_id')!=item['project_id']
                or project.get('id')!=item['project_id'] or canonical(row.get('save_root',''))!=canonical(event['save_root'])
                or row.get('temporary_campaign')!='ootss_editor_'+item['session_id']):continue
            if row.get('phase')=='closed':continue
            if row.get('environment')!=environment_id():raise ValueError('Session environment changed; files preserved.')
            history=root/'.session-history';history.mkdir(exist_ok=True);_plain(history)
            old=history/(item['session_id']+'-'+event['id']+'.json')
            if not old.exists():_publish(old,row)
            row.update(phase='closed',superseded_by_restore=event['id']);_publish(path,row)
        event['state']='complete';_publish(self.events/(event['id']+'.json'),event)
        rollback=canonical(event['rollback']);target=canonical(event['save_root'])
        warning=''
        if rollback.exists() and rollback.parent==target.parent and rollback.name=='.ootss-rollback-'+event['id']:
            try:
                if inventory(rollback)==self.verify(Path(event['before']))['inventory']:
                    shutil.rmtree(rollback)  # 已验证同级唯一名称、无重解析点、完整预备份和内容一致。
                else:warning='Restore complete; old staging files were preserved.'
            except (OSError,ValueError):warning='Restore complete; old staging files were preserved.'
        return dict(before=event['before'],restored=event['backup'],event=event['id'],warning=warning)

    def restore(self,backup,destination,*,confirmed=False):
        if confirmed is not True:raise ValueError('Explicit restore confirmation is required.')
        target=self._target(destination);backup=canonical(backup);disjoint(target,backup)
        row=self.verify(backup);self.guard()
        with self.lease_factory():
            before=self._backup(target);self.guard()
            sid=uuid.uuid4().hex;stage=target.parent/('.ootss-restore-'+sid);rollback=target.parent/('.ootss-rollback-'+sid)
            copy_verified(backup/'snapshot',stage,row['inventory'])
            projects=self._sessions(target)
            event=dict(format='ootss-save-restore',version=1,id=sid,state='preparing',environment=environment_id(),
                       save_root=str(target),backup=str(backup),before=str(before),stage=str(stage),rollback=str(rollback),
                       projects=projects,sessions=[p['session_id'] for p in projects])
            self.events.mkdir(parents=True,exist_ok=True);record=self.events/(sid+'.json');_publish(record,event)
            self.guard()
            if inventory(target)!=self.verify(before)['inventory']:raise ValueError('Current save changed after pre-backup; restore stopped.')
            target.rename(rollback)
            try:stage.rename(target)
            except BaseException:
                rollback.rename(target);event['state']='rolled_back';_publish(record,event);raise
            event['state']='applied';_publish(record,event)
            if inventory(target)!=row['inventory']:raise ValueError('Restored data differs; recovery files retained.')
            return self._finish(event)

    def finish_pending(self):
        self.guard();results=[]
        with self.lease_factory():
            for path in self.events.glob('*.json'):
                event=_json(path)
                if event.get('state') not in ('preparing','applied'):continue
                if event.get('environment')!=environment_id():raise ValueError('Unverifiable recovery event retained.')
                sid=event.get('id')
                if not isinstance(sid,str) or not re.fullmatch('[0-9a-f]{32}',sid) or path.stem!=sid:raise ValueError('Invalid restore identity.')
                target=self._target(event['save_root']);stage=canonical(event['stage']);rollback=canonical(event['rollback'])
                if stage!=target.parent/('.ootss-restore-'+sid) or rollback!=target.parent/('.ootss-rollback-'+sid):raise ValueError('Unsafe recovery paths.')
                if event['state']=='preparing':
                    if target.exists() and inventory(target)==self.verify(Path(event['backup']))['inventory'] and not stage.exists():
                        event['state']='applied';_publish(path,event)
                    elif not target.exists() and rollback.exists() and inventory(rollback)==self.verify(Path(event['before']))['inventory']:
                        rollback.rename(target);event['state']='rolled_back';_publish(path,event);continue
                    elif target.exists() and not rollback.exists() and inventory(target)==self.verify(Path(event['before']))['inventory']:
                        event['state']='rolled_back';_publish(path,event);continue
                    else:raise ValueError('Recovery state is uncertain. All files were preserved; do not start the game.')
                results.append(self._finish(event))
        return results
