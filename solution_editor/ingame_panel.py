"""naive 游戏内工程窗口；渲染在目标交换链，复用原生存档工程后端。"""
import argparse
import json
from pathlib import Path
import threading
import time


class PanelState:
    def __init__(self):
        self.delay_open=False;self.delay_state=dict(ready=False,error='')
        self.checkpoint_open=False;self.checkpoint_state={}
        self.action_open=False;self.action_symbol='U';self.settings_status='';self.inserting=False
        self.action_keys={'X':'X','V':'V'};self.active_solve_key='P';self.active_extra_wait=1000;self.active_interval=250
        self.timeline_folded=False;self.settings_open=False;self.playhead=0;self._last_mode='idle'
        self.can_undo=False;self.can_redo=False
        from .release_profile import preview
        from .localization import language
        self.preview=preview();self.language=language();self.toggle_key='Backquote';self.toggle_hint='`'
        self.speed_state=dict(value=None,available=False,error='')
        self.folded=False;self.name='My project' if self.language=='en' else '我的工程';self.closing=False
        self.open_path='';self.revisions={'name':0,'open_path':0}
        self.busy=False;self.project_state='closed';self.project_label='未打开工程'
        self.status='选择旧工程，或为当前存档新建工程。'
        self.projects=[];self.project_offset=0
        self.record_state=dict(mode='idle',pending=False,count=0);self.policy_errors=[]
        self.steps=[];self.selected=None;self.timeline_offset=0;self.timeline_revision=0;self.follow_current=True
        self.limits=dict(name=64,open_path=512,interval=10,extra=10,solve_key=1,correct_key=1,wait_key=1,wait_value=10,toggle_key=16)
        self.revisions['toggle_key']=0
        for key,value in dict(interval='250',extra='1000',solve_key='P',correct_key='E',wait_key='T',wait_value='1000').items():
            setattr(self,key,value);self.revisions[key]=0

    def set_field(self,name,value):
        setattr(self,name,str(value));self.revisions[name]+=1

    def event(self,event):
        action=event.get('action','')
        if action=='toggle':self.folded=not self.folded
        elif action=='toggle_timeline':self.timeline_folded=not self.timeline_folded
        elif action=='close_delay':self.delay_open=False
        elif action=='close_action':self.action_open=False;self.inserting=False
        elif action=='close_checkpoints':self.checkpoint_open=False
        elif action=='open_checkpoints':
            self.checkpoint_open=True;self.delay_open=False;self.action_open=False;self.inserting=False
        elif action=='new_step':
            self.checkpoint_open=False
            self.action_open=True;self.delay_open=False;self.inserting=True;self.action_symbol='U'
        elif action=='follow_current':self.follow_current=True
        elif action=='scroll_list':
            value=event.get('offset')
            if type(value) is int:
                if event.get('list')=='timeline':
                    self.timeline_offset=max(0,min(value,len(self.steps)-12));self.follow_current=False
                elif event.get('list')=='projects':self.project_offset=max(0,min(value,len(self.projects)-3))
        elif action=='close_settings':self.settings_open=False
        elif action.startswith('choose_action:'):
            symbol=action.split(':',1)[1]
            if symbol in 'UDLRXV123456789P_' and len(symbol)==1 and (symbol!='_' or self.inserting):self.action_symbol=symbol
        elif action=='toggle_settings':self.settings_open=not self.settings_open
        elif action in self.revisions:
            revision=event.get('revision',self.revisions[action]+1)
            if revision>=self.revisions[action]:
                setattr(self,action,str(event.get('value',''))[:self.limits[action]])
                self.revisions[action]=revision
        elif action.startswith('select:'):
            index=int(action.split(':')[1])
            if 0<=index<len(self.projects):
                self.open_path=self.projects[index]['root'];self.revisions['open_path']+=1
        elif action.startswith('step:'):
            self.checkpoint_open=False
            id=action.split(':',1)[1]
            if any(row['id']==id for row in self.steps):
                self.selected=id
                self.inserting=False
                row=next(row for row in self.steps if row['id']==id)
                if row['symbol']=='_':
                    self.set_field('wait_value',row['wait_ms']);self.delay_open=True;self.action_open=False
                else:self.delay_open=False;self.action_open=True;self.action_symbol=row['symbol']
        elif action in ('record','play','prepare_delay','trial_wait'):self.follow_current=True

    def model(self,width,height):
        from .panel_style import decorate
        from .localization import localize_model
        return localize_model(decorate(self._layout_model(width,height)),self.language)

    def _layout_model(self,width,height):
        from .panel_layout import split_model, startup_model
        return (startup_model if self.project_state=='closed' else split_model)(self,width,height)


class IngamePanel:
    def __init__(self):
        import frida
        from research.process import ProcessReader
        from .campaign_connection import discover_game,GameLease
        from .game_builds import select_build
        from .macro_input import find_game_window
        from .windows_observer import process_creation_id
        self.pid=discover_game()
        self.reader=ProcessReader(self.pid);self.session=None;self.lease=None
        self.state=PanelState();self.events=[];self.lock=threading.Lock()
        self.projects=None;self.last_model=None;self.recording=None;self.app_lease=None
        self._form_version=-1;self._timeline_marker=None
        try:
            from .app_lease import EditorLease
            from .paths import paths
            layout=paths();layout.prepare();self.app_lease=EditorLease()
            path=Path(self.reader.path)
            if path.name.casefold()!='sinking_star.exe':
                raise ValueError('Unsupported game executable')
            self.build=select_build(path.read_bytes())
            self.creation=process_creation_id(self.reader.handle)
            self.window=find_game_window(self.pid)
            self.lease=GameLease(self.pid,str(self.creation)+'-ui')
            from .ingame_projects import PanelProjects
            from .campaign_editor_session import CampaignEditorSession
            from .campaign_runtime import CampaignRuntime
            def connect(root):
                runtime=CampaignRuntime(self.pid,root)
                if runtime.creation!=self.creation:
                    runtime.close();raise ValueError('Game process changed')
                return runtime
            controller=CampaignEditorSession(connect,game_sha256=self.build.sha256)
            from .macro_input import MacroConnection
            controller.connect_input=lambda runtime:MacroConnection(runtime,live_bindings=True)
            self.projects=PanelProjects(layout.projects,session=controller)
            self.state.projects=self.projects.projects
            self.session=frida.attach(self.pid)
            research=layout.assets
            source='\n'.join((research/name).read_text(encoding='utf-8') for name in ('panel_text.js','panel_recorder.js','panel_access.js','panel_cursor.js','panel_lists.js','ingame_overlay.js'))
            self.script=self.session.create_script(source)
            self.script.on('message',self._message)
            self.script.load();self.script.exports_sync.install(str(self.window))
            from .native_bindings import read_bindings
            from .recording_controller import RecordingController
            from .tool_preferences import ToolPreferences
            preferences=ToolPreferences(layout.config/'tool-keys.json')
            from .key_settings import toggle_label,actual_toggle_label
            self.state.set_field('toggle_key',toggle_label(preferences.toggle_vk))
            self.state.toggle_hint=actual_toggle_label(preferences.toggle_vk)
            self.script.exports_sync.set_toggle(preferences.toggle_vk)
            self.recording=RecordingController(self.projects,self.script.exports_sync,
                lambda:read_bindings(self.reader.read,[self.reader.image_base+rva for rva in self.build.keymap_pools]),preferences=preferences)
            for field,key in [('solve_key','solve'),('correct_key','correct'),('wait_key','wait')]:
                self.state.set_field(field,preferences.keys[key])
            self.state.settings_status=preferences.error
        except BaseException:
            self.close();raise

    def _message(self,row,data):
        with self.lock:self.events.append(row)

    def tick(self):
        with self.lock:events,self.events=self.events,[]
        self.projects.poll()
        self.recording.tick()
        for row in events:
            if row['type']=='error':raise RuntimeError(row.get('stack',str(row)))
            event=row.get('payload',{})
            if event.get('kind')=='ui':
                action=event.get('action')
                try:
                    if action in ('close_delay','new_step') or (action.startswith('step:') and action.split(':',1)[1]!=self.state.selected):
                        self.recording.close_delay()
                    if action in ('record','play','new','open','leave','recover','close'):
                        self.recording.close_delay();self.state.delay_open=False;self.state.action_open=False;self.state.inserting=False;self.state.checkpoint_open=False
                except Exception as failure:
                    self.recording.notice='任务尚未安全停止：'+str(failure);continue
                self.state.event(event)
                if action=='refresh' and not self.projects.busy:self.projects.refresh()
                elif action in ('new','open','save','leave','recover','close'):
                    try:
                        if not self.projects.busy:self.recording.before_project(action)
                        self.projects.request(action,name=self.state.name,path=self.state.open_path)
                    except Exception as error:
                        self.projects.error=str(error);self.projects.status='操作未开始：'+str(error)
                else:
                    try:
                        if action=='record':self.recording.start_recording()
                        elif action.startswith('speed:'):self.recording.set_speed(float(action.split(':',1)[1]))
                        elif action=='stop_delay':self.recording.stop('调试已停止，保留当前现场。')
                        elif action in ('end_record','stop'):self.recording.stop()
                        elif action=='play':self.recording.begin_replay('play')
                        elif action=='edit_undo':self.recording.undo_edit()
                        elif action=='edit_redo':self.recording.redo_edit()
                        elif action in ('open_checkpoints','refresh_checkpoints'):self.recording.checkpoint_storage()
                        elif action=='prune_checkpoints':self.recording.checkpoint_storage(prune=True)
                        elif action=='prepare_delay':self.recording.prepare_delay(self.state.selected)
                        elif action=='return_delay':self.recording.trial(self.state.selected,restore_only=True)
                        elif action=='trial_wait':self.recording.trial(self.state.selected,self.state.wait_value)
                        elif action=='apply_options':self.recording.apply_delays(self.state.interval,self.state.extra)
                        elif action=='apply_keys':
                            self.recording.apply_keys(dict(solve=self.state.solve_key,correct=self.state.correct_key,wait=self.state.wait_key),toggle=self.state.toggle_key)
                            self.state.settings_status='快捷键已保存'
                            from .key_settings import actual_toggle_label
                            self.state.toggle_hint=actual_toggle_label(self.recording.preferences.toggle_vk)
                            for field,key in [('solve_key','solve'),('correct_key','correct'),('wait_key','wait')]:
                                self.state.set_field(field,self.recording.preferences.keys[key])
                        elif action=='language':
                            from .localization import set_language
                            self.state.language='en' if self.state.language=='zh-CN' else 'zh-CN'
                            set_language(self.state.language)
                        elif action=='open_data':
                            import os
                            from .paths import paths
                            os.startfile(paths().data)
                        elif action=='insert_step':
                            if not self.state.inserting:raise ValueError('请先打开添加窗口。')
                            symbol=self.state.action_symbol
                            inserted_id=self.recording.insert(self.state.selected,symbol)
                            self.state.selected=inserted_id;self.state.inserting=False
                            self.state.delay_open=symbol=='_';self.state.action_open=symbol!='_'
                            if symbol=='_':self.state.set_field('wait_value',self.projects.session.timeline.extra_wait_ms)
                            index=self.projects.session.timeline.ids.index(inserted_id)
                            self.state.timeline_offset=max(0,index-11);self.state.follow_current=False
                        elif action=='move_step':
                            if event.get('version')!=self.state.timeline_revision:raise ValueError('列表已变化，请重新拖动。')
                            self.recording.reorder(event.get('id'),event.get('index'))
                            if self.state.selected!=event.get('id'):
                                self.state.action_open=False;self.state.delay_open=False;self.state.inserting=False
                            self.state.selected=event.get('id')
                        elif action in ('delete_step','set_wait','confirm_wait','replace_step'):
                            self.recording.edit(self.state.selected,delete=action=='delete_step',
                                wait_ms=self.state.wait_value if action in ('set_wait','confirm_wait') else None,confirm=action=='confirm_wait',
                                symbol=self.state.action_symbol if action=='replace_step' else None)
                    except Exception as error:
                        self.recording.notice=str(error)
                        if action=='apply_keys':self.state.settings_status='设置失败：'+str(error)
        self.state.busy=self.projects.busy
        self.state.can_undo=self.recording.history.can_undo
        self.state.can_redo=self.recording.history.can_redo
        self.state.checkpoint_state=self.recording.checkpoint_summary()
        self.state.speed_state=self.recording.speed_summary()
        self.state.status=self.projects.status
        if not self.projects.busy and not self.projects.error and self.recording.owner:
            self.recording.pull()
            self.state.record_state=self.recording.state
            self.state.policy_errors=self.recording.policy['errors']
            if self.state.policy_errors:self.state.status='；'.join(self.state.policy_errors)+'；可修改工具键。'
            elif self.recording.state['mode']=='recording':
                self.state.status=f"正在录制 · {self.recording.state['count']} 条目"+(' · 下一动作前将插入额外等待' if self.recording.state['pending'] else '')
            else:self.state.status=self.recording.notice or self.recording.state['reason'] or self.projects.status
            mode=self.state.record_state['mode']
            if mode=='recording' and self.state._last_mode!='recording':
                self.state.folded=True;self.state.timeline_folded=False
            self.state._last_mode=mode
            timeline=self.projects.session.timeline
            from .panel_actions import key_label
            self.state.action_keys={symbol:key_label(self.recording.policy.get('primary',{}).get(symbol)) for symbol in ('X','V')}
            self.state.active_solve_key=timeline.tool_keys['solve']
            self.state.active_extra_wait=timeline.extra_wait_ms
            self.state.active_interval=timeline.interval_ms
            self.state.playhead=timeline.playhead
            if self._form_version!=self.recording.form_version:
                values=dict(interval=timeline.interval_ms,extra=timeline.extra_wait_ms)
                if getattr(self,'_key_owner',None)!=self.recording.owner:
                    from .save_backup import register_project
                    register_project(self.projects.session.root)
                    values.update(solve_key=timeline.tool_keys['solve'],correct_key=timeline.tool_keys['correct'],wait_key=timeline.tool_keys['wait'])
                    self._key_owner=self.recording.owner
                for field_id,value in values.items():
                    self.state.set_field(field_id,value)
                self._form_version=self.recording.form_version
            marker=(id(timeline),self.recording.ui_revision)
            if marker!=self._timeline_marker:
                self.state.steps=timeline.to_document()['steps'];self._timeline_marker=marker
                self.state.timeline_revision+=1
                self.state.timeline_offset=min(self.state.timeline_offset,max(0,len(self.state.steps)-12))
                if self.state.selected not in timeline.ids:
                    self.state.selected=None
                    if not self.state.inserting:self.state.delay_open=False;self.state.action_open=False
        if not self.projects.busy:
            controller=self.projects.session
            self.state.project_state=controller.state
            title=next((row['name'] for row in self.projects.projects if Path(row['root'])==controller.root),
                controller.root.name if controller.root else '')
            self.state.project_label=(title+(' *' if controller.timeline.dirty else '')
                if controller.runtime is not None else '未打开工程')
            self.state.projects=self.projects.projects
            self.state.project_offset=min(self.state.project_offset,max(0,(len(self.state.projects)-3)))
        if self.state.delay_open:
            self.state.delay_state=self.recording.delay_info(self.state.selected)
        if self.state.project_state=='closed':
            self.state.checkpoint_open=False
            self.state.delay_open=False;self.state.action_open=False;self._key_owner=None
            self.state.inserting=False;self.state.timeline_offset=0;self.state.selected=None;self.state.follow_current=True
        self.state.closing=self.projects.ready_to_close
        status=self.script.exports_sync.status()
        if status.get('error'):raise RuntimeError(status['error'])
        dimensions=(status.get('width',0),status.get('height',0))
        if dimensions[0]>200 and dimensions[1]>200:
            model=self.state.model(*dimensions)
            if model!=self.last_model:
                self.script.exports_sync.model(model);self.last_model=model
        return status

    def close(self):
        if self.recording is not None:
            try:
                if self.session is not None and not self.session.is_detached:self.recording.stop()
            finally:
                try:self.recording.shutdown_completion()
                finally:
                    if self.projects is not None:self.projects.session.preserve_draft()
                    self.recording=None
        if self.projects is not None:self.projects.shutdown();self.projects=None
        if self.session is not None:
            if not self.session.is_detached and hasattr(self,'script'):
                for attempt in range(40):
                    try:self.script.exports_sync.close();break
                    except Exception as error:
                        if not any(reason in str(error) for reason in ('Render callback in progress','Cursor restoration in progress')):raise
                        time.sleep(.05)
                else:raise RuntimeError('Renderer is still busy; cannot unload safely')
            self.session.detach();self.session=None
        if self.lease is not None:self.lease.close();self.lease=None
        self.reader.close()
        if self.app_lease is not None:self.app_lease.close();self.app_lease=None


def main():
    from .startup_status import report,friendly_error
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds',type=float,default=0)
    parser.add_argument('--log',type=Path,help='启动器诊断日志')
    parser.add_argument('--startup-status',type=Path,help='启动器就绪反馈')
    args=parser.parse_args()
    panel=None;ready=False;timeout_requested=False
    try:
        if args.log:
            import sys
            args.log.parent.mkdir(parents=True,exist_ok=True)
            log=args.log.open('a',encoding='utf-8',buffering=1)
            sys.stdout=sys.stderr=log
        report(args.startup_status,'starting')
        panel=IngamePanel();started=time.monotonic()
        print(json.dumps(dict(pid=panel.pid,window=panel.window,creation=panel.creation)),flush=True)
        last=None
        while not panel.state.closing:
            status=panel.tick()
            if not ready and status.get('frames') and not status.get('error'):
                report(args.startup_status,'ready');ready=True
            if status!=last:print(json.dumps(status),flush=True);last=status
            if args.seconds and time.monotonic()-started>=args.seconds and not timeout_requested and not panel.projects.busy:
                panel.recording.before_project('close')
                panel.projects.request('close');timeout_requested=True
            time.sleep(.05)
    except BaseException as error:
        if not ready:
            try:report(args.startup_status,'failed',friendly_error(error))
            except OSError:pass
        raise
    finally:
        if panel is not None:
            panel.close()
            print(json.dumps(dict(closed=True)),flush=True)


if __name__=='__main__':main()
