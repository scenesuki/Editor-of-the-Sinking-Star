"""按已核对构建选择原生接口的存档工程后端；供工程窗口和开发协议复用。

主线程执行已核对的正常保存／载入接口，等待文件写入和队列完成后复制或清理。
保留早期菜单参数桥供调查查阅；正式自动路径使用 create_auto/enter_auto/exit_auto。
"""
import argparse
import json
from pathlib import Path
import struct
import time
from contextlib import nullcontext
from functools import wraps

from .campaign_project import CampaignProject, _name, _publish
from .save_workspace import _plain
from .game_builds import LEGACY,select_build


def read_campaign_binding(read, base, *, build=LEGACY):
    samples=[]
    values=[]
    for rva,maximum in ((build.rvas['save_root'],4096),(build.rvas['campaign'],128)):
        header=bytes(read(base+rva,16))
        count,data=struct.unpack('<QQ',header)
        if not 0<count<=maximum or not 0<data<2**64-count:raise ValueError('Invalid campaign path header')
        payload=bytes(read(data,count))
        if len(payload)!=count:raise OSError('Incomplete campaign path')
        values.append(payload.decode('utf-8'))
        samples.extend(((base+rva,header),(data,payload)))
    for address,expected in samples:
        if bytes(read(address,len(expected)))!=expected:raise ValueError('Campaign changed during binding')
    if not Path(values[0]).is_absolute():raise ValueError('Save root is not absolute')
    _name(values[1])
    return dict(save_root=values[0],campaign=values[1])


def validate_saved_items(events,finished):
    def canonical(path):return path.replace('\\','/').casefold()
    for item in finished:
        if item['flag']!='0':continue
        final=canonical(item['path'])
        parent,leaf=final.rsplit('/',1)
        temporary=parent+'/_temp_'+leaf
        rows=[e for e in events if e.get('thread')==item['thread']
              and item['started_sequence']<e['sequence']<item['sequence']]
        writes=[e for e in rows if e['tag']=='file_write' and canonical(e['path'])==temporary]
        commits=[e for e in rows if e['tag'] in ('file_replace','file_move')
                 and canonical(e.get('destination',e.get('path','')))==final and e.get('success') is True]
        if not writes or not commits or any(e.get('success') is not True or e.get('overlapped') is not False
                                           or e.get('written')!=e.get('requested') for e in writes):
            raise RuntimeError('Native save write or final replacement did not succeed: '+item['path'])


def _running_game(method):
    @wraps(method)
    def wrapped(self,*args,**kwargs):
        if method.__name__=='command' and (args[0] if args else kwargs['row'])['action']=='complete_tile':
            from .release_profile import check_steps
            check_steps([{'symbol':'P'}])
        if method.__name__=='command' and (args[0] if args else kwargs['row'])['action'] not in (
            'create_auto','enter_auto','exit_auto','recover_auto','checkpoint_capture','checkpoint_restore',
            'complete_tile','save','save_menu'):
            return method(self,*args,**kwargs)
        speed=getattr(self,'speed',None)
        with speed.running() if speed is not None else nullcontext():
            return method(self,*args,**kwargs)
    return wrapped


class CampaignRuntime:
    def __init__(self,pid,project_root):
        from research.process import ProcessReader
        from research.pe import PeImage
        from .windows_observer import process_creation_id
        self.reader=ProcessReader(pid)
        self.bridge=None
        self.frames=None
        self.lease=None
        self.speed=None
        try:
            path=Path(self.reader.path)
            data=path.read_bytes()
            if path.name.casefold()!='sinking_star.exe':
                raise ValueError('Unsupported game executable')
            self.build=select_build(data)
            self.creation=process_creation_id(self.reader.handle)
            from .campaign_connection import GameLease
            self.lease=GameLease(pid,self.creation)
            self.pid=pid
            self.project_root=Path(project_root).absolute()
            self.image=PeImage(data)
            offset=self.image.rva_to_offset(self.build.rvas['load'])
            self.expected_code=data[offset:offset+32].hex()
            self.binding()
            from .game_speed import GameSpeed
            self.speed=GameSpeed(pid,self.creation,self.build,self.image,self.reader.image_base)
        except BaseException:
            if self.lease is not None:self.lease.close()
            self.reader.close();raise

    def binding(self):
        from .windows_observer import process_creation_id
        if process_creation_id(self.reader.handle)!=self.creation:raise ValueError('Game process changed')
        row=read_campaign_binding(self.reader.read,self.reader.image_base,build=self.build)
        return row

    def project(self,*,verify_initial=True):
        return CampaignProject.open(self.project_root,game_sha256=self.build.sha256,verify_initial=verify_initial)

    @staticmethod
    def _require_original(binding):
        if binding['campaign'].casefold().startswith('ootss_editor_'):
            raise ValueError('当前仍在工具临时副本中，请打开其所属工程并恢复原存档。')

    def _frame_commands(self):
        if self.frames is None:
            from research.campaign_frame_commands import CampaignFrameCommands
            config=self.build.code_config(self.image,self.reader.image_base,('frame','load','save','menu'))
            self.frames=CampaignFrameCommands(self.pid,config)
        return self.frames

    def _execute(self,action,campaign=None):
        self.binding()
        frames=self._frame_commands()
        frames.request(action,campaign)
        deadline=time.monotonic()+6
        while time.monotonic()<deadline:
            status=frames.status()
            if status['state']=='complete':
                if action=='load' and not status['result']['success']:
                    raise RuntimeError('Native campaign load failed')
                return status['result']
            if status['state'] in ('error','expired'):raise RuntimeError(str(status))
            time.sleep(.02)
        raise TimeoutError('Native frame command did not complete')

    @_running_game
    def save_current(self,*,metadata_only=False):
        from research.save_trace import SaveTrace
        binding=self.binding()
        points=self.build.save_trace_points(self.image,self.reader.image_base)
        with SaveTrace(self.pid,points,Path(binding['save_root']).resolve().as_posix()+'/',
                       file_io=True,lifetime_ms=15000) as trace:
            command=self._execute('menu' if metadata_only else 'save')
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                snapshot=trace.snapshot()
                queue=struct.unpack('<Q',self.reader.read(self.reader.image_base+self.build.rvas['save_queue'],8))[0]
                campaign_parent=(Path(binding['save_root'])/binding['campaign']).resolve()
                finished=[e for e in snapshot['events'] if e['tag']=='item_finished'
                          and (Path(e['path']).resolve()==(Path(binding['save_root'])/'settings.menu_state').resolve()
                               if metadata_only else Path(e['path']).parent.resolve()==campaign_parent)]
                if snapshot['closed'] or snapshot['tracking_errors'] or snapshot['dropped']:
                    raise RuntimeError('Native save completion tracking failed')
                if finished and queue==0 and not snapshot['in_flight'] and not snapshot['open_handles']:
                    validate_saved_items(snapshot['events'],finished)
                    if self.binding()!=binding:raise ValueError('Campaign changed during save')
                    return dict(binding=binding,command=command,queue=queue,
                                finished=finished,events=snapshot['events'])
                time.sleep(.02)
        error=TimeoutError('Native save queue did not finish')
        error.snapshot=dict(binding=binding,command=command,queue=queue,tracking=snapshot)
        raise error

    @_running_game
    def load_campaign(self,target):
        _name(target)
        target_path=Path(self.binding()['save_root'])/target
        _plain(target_path)
        if not target_path.is_dir():raise ValueError('Campaign directory is missing')
        command=self._execute('load',target)
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            binding=self.binding()
            if binding['campaign']==target:return dict(binding=binding,command=command)
            time.sleep(.02)
        raise RuntimeError('Native campaign identity did not switch')

    @_running_game
    def command(self,row):
        action=row['action']
        binding=self.binding()
        if action=='save':return self.save_current()
        if action=='complete_tile':
            from .overworld_completion import complete_current_tile
            return complete_current_tile(self,cancel=row.get('_cancel'))
        if action=='save_menu':return self.save_current(metadata_only=True)
        if action in ('checkpoint_capture','checkpoint_restore'):
            from .delay_checkpoints import Checkpoints
            p=self.project();pending=p.pending();store=Checkpoints(p);key=row['key']
            store.path(key)
            if (pending is None or pending['phase']!='active'
                or binding['campaign']!=pending['temporary_campaign']
                or Path(binding['save_root']).resolve()!=Path(pending['save_root']).resolve()):
                raise ValueError('Checkpoint requires the active project temporary')
            if action=='checkpoint_capture':
                saved=self.save_current()
                path=store.capture(key,current_campaign=self.binding()['campaign'])
                return dict(checkpoint=str(path),save=saved)
            store.resolve(key)  # 校验快照在切换和清理之前完成。
            original=pending['return_campaign']
            self.command(dict(action='exit_auto'))
            returned=self.binding()
            if returned['campaign']!=original:raise ValueError('Checkpoint return campaign changed')
            prepared=p.prepare_session(Path(returned['save_root']),return_campaign=original,checkpoint=key)
            loaded=self.load_campaign(prepared['temporary_campaign'])
            p.confirm_loaded(loaded['binding']['campaign'])
            return dict(session=prepared,loaded=loaded,checkpoint=key)
        if action=='create_auto':
            self._require_original(binding)
            if self.project_root.exists():raise FileExistsError('Project directory already exists')
            saved=self.save_current()
            self.project_root.parent.mkdir(parents=True,exist_ok=True)
            p=CampaignProject.create(self.project_root,row.get('name','存档工程'),Path(binding['save_root']),
                                     binding['campaign'],game_sha256=self.build.sha256)
            return dict(project=str(p.root),project_id=p.row['id'],save=saved)
        if action=='enter_auto':
            self._require_original(binding)
            p=self.project()
            if p.pending() is not None:raise FileExistsError('Unresolved temporary campaign; recover first')
            saved=self.save_current()
            session=p.prepare_session(Path(binding['save_root']),return_campaign=binding['campaign'])
            loaded=self.load_campaign(session['temporary_campaign'])
            p.confirm_loaded(loaded['binding']['campaign'])
            return dict(session=session,loaded=loaded,save=saved)
        if action in ('exit_auto','recover_auto'):
            p=self.project(verify_initial=False);session=p.pending()
            if session is None:return dict(phase='closed',binding=binding)
            if binding['campaign'] not in (session['temporary_campaign'],session['return_campaign']):
                if action!='recover_auto':
                    raise ValueError('Another campaign is active; use explicit recovery and keep recovery materials')
                self._require_original(binding)
            if Path(binding['save_root']).resolve()!=Path(session['save_root']).resolve():
                raise ValueError('Save root changed')
            saved=None
            if binding['campaign']!=session['return_campaign']:
                saved=self.save_current()
                self.load_campaign(session['return_campaign'])
            menu=self.save_current(metadata_only=True)
            p.finish_session(current_campaign=self.binding()['campaign'])
            return dict(phase='closed',binding=self.binding(),save=saved,menu=menu)
        if action=='status':
            return dict(binding=binding,bridge=self.bridge.status() if self.bridge else None,
                        pending=self.project(verify_initial=False).pending() if (self.project_root/'project.json').exists() else None)
        if action=='create':
            self._require_original(binding)
            if row.get('saved_via_native_menu') is not True:
                raise ValueError('Complete normal native save before project creation')
            self.project_root.parent.mkdir(parents=True,exist_ok=True)
            p=CampaignProject.create(self.project_root,row.get('name','存档工程'),Path(binding['save_root']),
                                     binding['campaign'],game_sha256=self.build.sha256)
            return dict(project=str(p.root),project_id=p.row['id'])
        if action=='prepare':
            self._require_original(binding)
            return self.project().prepare_session(Path(binding['save_root']),return_campaign=binding['campaign'])
        if action in ('arm_temporary','arm_return'):
            pending=self.project().pending()
            if pending is None:raise ValueError('No pending session')
            if Path(binding['save_root']).resolve()!=Path(pending['save_root']).resolve():
                raise ValueError('Save root changed')
            if binding['campaign'] not in (pending['return_campaign'],pending['temporary_campaign']):
                raise ValueError('Current campaign no longer belongs to this session')
            if self.bridge is None:
                from research.campaign_load_bridge import CampaignLoadBridge
                self.bridge=CampaignLoadBridge(self.pid,hex(self.reader.image_base+self.build.rvas['load']),self.expected_code)
            target=pending['temporary_campaign'] if action=='arm_temporary' else pending['return_campaign']
            # 原生菜单选择当前战役会直接续玩，因此等待明确目标条目的正常加载。
            self.bridge.arm(target,target)
            return self.bridge.status()
        if action=='confirm':
            if self.bridge is None or self.bridge.status()['state']!='intercepted':
                raise ValueError('No completed native menu interception')
            self.project().confirm_loaded(binding['campaign'])
            return dict(binding=binding,phase='active')
        if action=='finish':
            self.project().finish_session(current_campaign=binding['campaign'])
            return dict(binding=binding,phase='closed')
        if action=='close':
            pending=self.project(verify_initial=False).pending() if (self.project_root/'project.json').exists() else None
            if pending is not None:raise ValueError('Return and clean up session before closing controller')
            self.close();return dict(closed=True)
        raise ValueError('Unsupported campaign command')

    def close(self):
        if getattr(self,'speed',None) is not None:
            self.speed.close();self.speed=None
        if self.frames is not None:
            if (not self.frames.session.is_detached
                and self.frames.script.exports_sync.borrowed(hex(self.reader.image_base+self.build.rvas['campaign']))):
                raise RuntimeError('Native campaign path still borrows frame command memory')
            self.frames.close();self.frames=None
        if self.bridge is not None:
            if (not self.bridge.session.is_detached
                and self.bridge.script.exports_sync.borrowed(hex(self.reader.image_base+self.build.rvas['campaign']))):
                raise RuntimeError('Native campaign path still borrows bridge memory; return before detaching')
            self.bridge.close();self.bridge=None
        self.reader.close()
        if self.lease is not None:self.lease.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid',type=int,required=True)
    parser.add_argument('--project',type=Path,required=True)
    parser.add_argument('--control',type=Path,required=True)
    args=parser.parse_args()
    args.control.mkdir(exist_ok=False)
    runtime=CampaignRuntime(args.pid,args.project)
    _publish(args.control/'ready.json',runtime.binding())
    seen=set()
    try:
        while True:
            for request in sorted(args.control.glob('request-*.json')):
                if request.name in seen:continue
                seen.add(request.name)
                try:
                    row=json.loads(request.read_text(encoding='utf-8-sig'))
                    result=dict(ok=True,result=runtime.command(row))
                except Exception as error:result=dict(ok=False,error=str(error))
                _publish(request.with_name(request.name.replace('request-','response-',1)),result)
                if result['ok'] and row['action']=='close':return
            time.sleep(.1)
    finally:
        runtime.close()


if __name__=='__main__':main()
