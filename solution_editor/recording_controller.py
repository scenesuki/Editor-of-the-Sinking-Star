"""游戏内录制协调：当前位置追加，显式起点播放及按需延时试调。"""
import time
import uuid

from .recording_timeline import RecordingTimeline
from .native_bindings import tool_keys


class RecordingController:
    def __init__(self,projects,bridge,read_bindings,*,preferences=None):
        from .tool_preferences import ToolPreferences
        from .edit_history import EditHistory
        self.history=EditHistory()
        self.preferences=preferences if preferences is not None else ToolPreferences()
        self.projects,self.bridge,self.read_bindings=projects,bridge,read_bindings
        self.owner=None;self.state=None;self.policy=None;self.last_doc_revision=0
        self.notice='';self.form_version=0;self._next_refresh=0
        self.intent=None;self.wait_completion=0;self.playing=False
        self.ui_revision=0;self.last_native_reason=''
        self.delay=None;self.delay_ready=None;self.delay_signature=None
        self.completion_job=None
        self.checkpoint_plan=None;self.checkpoint_pending=None;self.checkpoint_status=''
        self._paused=False
        self._speed_source=None;self._speed_state=dict(value=None,available=False,error='')

    @property
    def session(self):return self.projects.session

    def refresh_policy(self,*,force=False):
        if self.owner is None:return
        now=time.monotonic()
        if not force and now<self._next_refresh:return
        self._next_refresh=now+.5
        try:
            from .release_profile import preview,active_tools
            from .key_settings import validate_toggle
            snapshot=self.read_bindings();policy=snapshot.policy(panel_key=self.preferences.toggle_vk)
            policy['errors']+=snapshot.conflicts(self.session.timeline.tool_keys)
            policy['solve_enabled']=not preview()
            try:validate_toggle(self.preferences.toggle_vk,snapshot,active_tools(self.session.timeline.tool_keys))
            except ValueError as error:policy['errors'].append(str(error))
        except Exception as error:
            policy=dict(record={},undo=[],unsupported=[],errors=['无法读取当前键位：'+str(error)],digest='unavailable',guards=[])
            self.bridge.recording_stop('无法读取当前键位，录制已停止。')
            self.bridge.recording_mode('idle',True)
        if self.policy!=policy:self.bridge.recording_policy(policy)
        self.policy=policy

    def _load(self,*,needs_replay):
        self.refresh_policy(force=True)
        self.bridge.recording_load(self.session.timeline.to_document(),self.policy,uuid.uuid4().hex[:16],needs_replay)
        self._sync_speed_pause(force=True)
        self.last_doc_revision=0;self.state=self.bridge.recording_status()
        self.ui_revision+=1;self.last_native_reason=''

    def pull(self):
        if self.owner is None:return
        self.state=self.bridge.recording_status()
        if self.state is not None and self.state['reason']!=self.last_native_reason:
            self.last_native_reason=self.state['reason']
            if self.last_native_reason:self.notice=self.last_native_reason
        if self.state is None or self.state['documentRevision']==self.last_doc_revision:return
        snapshot=self.bridge.recording_snapshot()
        timeline=RecordingTimeline.from_document(snapshot['document'])
        timeline.playhead=timeline.caret=timeline.anchor=len(timeline.steps)
        timeline.dirty=True;self.session.timeline=timeline
        self.history.clear()
        self.state=snapshot['state'];self.last_doc_revision=self.state['documentRevision']
        self.ui_revision+=1

    def stop(self,reason='录制／播放已停止。'):
        if self.completion_job is not None:self.completion_job.cancel()
        self.intent=None
        was_playing=self.playing
        try:
            if self.owner is not None:self.bridge.recording_stop(reason)
        finally:
            # 原生界面 RPC 失联也必须尝试独立输入工作进程的松键。
            self.session.stop_playback();self.playing=False
        if self.owner is not None:self.pull()
        if self.owner is not None and was_playing:
            self.bridge.recording_mode('idle',True);self.state=self.bridge.recording_status()
        self.notice=reason

    def before_project(self,action):
        if self.completion_job is not None:raise ValueError('请等待 P 操作收尾后再切换工程。')
        if self.projects.busy:raise ValueError('正在处理工程，请等待。')
        self.stop('录制已结束，正在处理工程。')

    def _available(self):
        if self.completion_job is not None:
            self.notice='正在处理 P 操作，请等待。';return False
        if self.projects.busy or self.session.state!='active' or self.owner is None:
            self.notice='请先进入工程，并等待存档任务完成。';return False
        if self.session.playback is not None and self.session.playback.cleanup_pending:
            try:self.session.stop_playback()
            except Exception as error:
                self.notice='按键释放尚未完成：'+str(error);return False
        self.refresh_policy(force=True)
        if self.policy['errors']:
            self.notice='；'.join(self.policy['errors']);return False
        return True

    def start_recording(self):
        if not self._available():return
        self.pull()
        if self.playing:return
        try:self.state=self.bridge.recording_start();self.notice=''
        except Exception as error:self.notice='无法开始录制：'+str(error)

    def _sync_speed_pause(self,*,force=False):
        speed=getattr(self.session.runtime,'speed',None)
        self._speed_source=speed
        try:
            value=speed.read() if speed is not None else None
            self._speed_state=dict(value=value,available=speed is not None and self.session.state=='active',error='')
        except Exception as error:
            self._speed_state=dict(value=None,available=False,error='调速不可用：'+str(error))
            raise
        paused=value==0
        if force or paused!=self._paused:
            if hasattr(self.bridge,'recording_paused'):self.bridge.recording_paused(paused)
            self._paused=paused

    def speed_summary(self):
        speed=getattr(self.session.runtime,'speed',None)
        if speed is None:return dict(value=None,available=False,error='')
        if speed is not self._speed_source:
            try:self._sync_speed_pause()
            except Exception:pass
        # 与本轮暂停同步共享采样，不再为绘制额外发起一次同步 RPC。
        return dict(self._speed_state,available=self._speed_state['available'] and self.session.state=='active')

    def set_speed(self,value):
        if self.projects.busy or self.session.state!='active' or self.owner is None:
            raise ValueError('请先进入工程并等待存档任务完成。')
        self.pull()
        if self.playing or self.intent is not None or self.completion_job is not None or self.state['mode'] not in ('idle','recording'):
            raise ValueError('自动播放、试调及准备期间固定 1×，不能调速。')
        speed=getattr(self.session.runtime,'speed',None)
        if speed is None:raise ValueError('游戏调速尚未连接。')
        self.session.stop_playback()
        # 暂停先关输入；若倍率写入失败，按实际可核验状态回置。
        if value==0 and hasattr(self.bridge,'recording_paused'):self.bridge.recording_paused(True)
        try:speed.set(value)
        finally:self._sync_speed_pause(force=True)
        self.notice='游戏已暂停；恢复速度后继续录制。' if value==0 else f'游戏速度 {value:g}×'

    def _normal_speed(self):
        speed=getattr(self.session.runtime,'speed',None)
        if speed is not None:speed.set(1)
        self._sync_speed_pause(force=True)

    def begin_replay(self,intent='play'):
        if not self._available():return
        from .release_profile import check_steps
        check_steps(self.session.timeline.steps)
        self._normal_speed()
        self.stop('正在准备从工程起点重放。')
        self.intent=intent;self.wait_completion=self.projects.completion
        self.bridge.recording_mode('preparing',True)
        self.projects.request('reset')

    def delay_info(self,wait_id):
        from .delay_checkpoints import delay_plan
        try:
            plan=delay_plan(self.session.timeline,wait_id)
            ready=self.delay_ready is not None and self.delay_signature==plan.digest
            return dict(ready=ready,error='',before=plan.trial.steps[0].symbol,after=plan.trial.steps[-1].symbol,
                        message=self.notice if self.delay is not None and self.delay.key['wait_id']==wait_id else '')
        except (ValueError,AttributeError):return dict(ready=False,error='请选择前后都有动作的单条等待；连续等待须手动整理。')

    def close_delay(self):
        if self.intent and self.intent.startswith('trial_'):self.stop('延时调试已停止，保留当前现场。')
        self.delay_ready=None;self.delay_signature=None

    def prepare_delay(self,wait_id):
        from .delay_checkpoints import delay_plan
        from dataclasses import replace
        import hashlib
        self._editable()
        plan=delay_plan(self.session.timeline,wait_id)
        from .release_profile import check_steps
        check_steps(self.session.timeline.steps)
        if not self._available():return
        self._normal_speed()
        self.stop('正在从工程起点准备 A 执行前的检查点。')
        self.delay_ready=None;self.delay_signature=plan.digest
        # 每次明确准备都发布新的不可变快照，旧检查点不冒充本次保存。
        key=dict(plan.key,prefix_sha256=hashlib.sha256((plan.digest+uuid.uuid4().hex).encode()).hexdigest())
        self.delay=replace(plan,key=key)
        self.intent='trial_prefix';self._delay_task('reset')

    def trial(self,wait_id,wait_ms=None,*,restore_only=False):
        from .delay_checkpoints import Checkpoints,delay_plan
        from .campaign_project import CampaignProject
        from dataclasses import replace
        self._editable()
        plan=delay_plan(self.session.timeline,wait_id)
        if not restore_only:
            from .release_profile import check_steps
            check_steps(self.session.timeline.steps)
        if self.delay_ready is None or self.delay_signature!=plan.digest:
            raise ValueError('请先点击“调试延时”准备有效的 A 执行前检查点。')
        if wait_ms is not None and not restore_only:
            self.edit(wait_id,wait_ms=wait_ms)
            plan=delay_plan(self.session.timeline,wait_id)
        p=CampaignProject.open(self.session.root,game_sha256=self.session.game_sha256)
        if not Checkpoints(p).exists(self.delay_ready):
            self.delay_ready=None;raise ValueError('检查点不可用，请重新准备。')
        if not self._available():return
        if not restore_only:self._normal_speed()
        key=self.delay_ready
        self.stop('正在恢复 A 执行前的调试起点。')
        self.delay=replace(plan,key=key)
        self.intent='trial_return' if restore_only else 'trial_restore'
        self._delay_task('checkpoint_restore')

    def _delay_task(self,action):
        self.wait_completion=self.projects.completion
        self.bridge.recording_mode('preparing',True)
        self.projects.request(action,key=self.delay.key)

    def _after_prefix(self):
        self.intent='trial_capture';self._delay_task('checkpoint_capture')

    def _arm(self):
        if not self._available():
            self.intent=None;self.bridge.recording_mode('idle',True);return
        if self.intent in ('trial_capture','trial_return'):
            if self.intent=='trial_capture':
                self.delay_ready=dict(self.delay.key);self.notice='调试起点已准备：A 执行前。'
            else:self.notice='已返回 A 执行前，未发送调试动作。'
            self.intent=None;self.bridge.recording_mode('idle',True);return
        timeline=(self.delay.prefix if self.intent=='trial_prefix' else
                  self.delay.trial if self.intent=='trial_restore' else self.session.timeline)
        if not timeline.steps:
            try:
                if self.intent=='trial_prefix':
                    self.bridge.leave_panel();self._after_prefix();return
                if self.intent in ('play','record','trial_prefix','trial_restore'):self.bridge.leave_panel()
            except Exception as error:
                self.intent=None;self.bridge.recording_mode('idle',True)
                self.notice='无法准备播放：'+str(error);return
            intent,self.intent=self.intent,None
            self.bridge.recording_mode('idle',False)
            if intent=='record':self.start_recording()
            return
        try:
            self.session.start_playback(timeline=timeline,focus_delay_ms=0 if self.intent=='trial_restore' else 1000)
            tag=getattr(self.session._input_connection,'own_tag',None)
            if tag is not None:self.bridge.recording_own_tag(tag)
            if self.bridge.recording_status()['mode']!='preparing':
                self.session.stop_playback();self.intent=None
                self.notice='重放准备已取消，请重新开始。';return
            if self.intent in ('play','record','trial_prefix','trial_restore'):self.bridge.leave_panel()
            self.bridge.recording_mode('playing',True);self.playing=True
            self.notice=('正在试调等待及下一动作；效果由你判断。' if self.intent=='trial_restore' else
                         '从工程起点重放；Escape／失焦可停止。')
        except Exception as error:
            self.intent=None;self.playing=False
            try:self.session.stop_playback()
            except Exception as release_error:error=RuntimeError(f'{error}；按键释放待重试：{release_error}')
            self.notice='无法准备播放：'+str(error)
            self.bridge.recording_mode('idle',True)

    def tick(self):
        if self.projects.busy:return
        if self.session.state!='active':
            self.history.clear()
            self.checkpoint_plan=None;self.checkpoint_pending=None;self.checkpoint_status=''
            self.delay_ready=None
            if self.projects.error:self.notice='调试／播放准备失败：'+str(self.projects.error)
            if self.owner is not None:
                self.bridge.recording_clear();self.owner=None;self.state=None
                self._paused=False
            self.intent=None;self.playing=False;return
        if self.owner!=str(self.session.root):
            self.history.clear()
            self.checkpoint_plan=None;self.checkpoint_pending=None;self.checkpoint_status=''
            self.session.timeline=RecordingTimeline.from_timeline(self.session.timeline)
            if self.preferences.configured and self.session.timeline.tool_keys!=self.preferences.keys:
                self.session.timeline.tool_keys=dict(self.preferences.keys);self.session.timeline.dirty=True
            self.owner=str(self.session.root);self.form_version+=1
            self._load(needs_replay=self.projects.last_action!='new')
            self.notice=self.session.notice
            if self.projects.last_action=='new' and self.projects.last_success:self.start_recording()
        if self.checkpoint_pending is not None and self.projects.completion!=self.checkpoint_pending:
            self.checkpoint_pending=None
            if self.projects.error:
                self.checkpoint_plan=None;self.checkpoint_status='检查点操作失败：'+self.projects.error
            else:
                self.checkpoint_plan=self.projects.result
                removed=self.checkpoint_plan.get('removed_count')
                self.checkpoint_status=f'已清理 {removed} 项历史检查点。' if removed is not None else '容量已核对。'
            self.notice=self.checkpoint_status
        self.refresh_policy();self.pull()
        try:self._sync_speed_pause()
        except Exception as error:
            self.stop('游戏速度状态无法核验：'+str(error));return
        if self.completion_job is not None:
            if self.state['mode']!='completing':self.completion_job.cancel()
            if not self.completion_job.done:return
            job,self.completion_job=self.completion_job,None
            try:job.poll();ok=True;error=''
            except Exception as failure:ok=False;error=str(failure)
            self.bridge.recording_solve_result(ok,error);self.pull()
            return
        if self.state['mode']=='completing':
            if not self._available():self.bridge.recording_solve_result(False,self.notice);self.pull();return
            from .completion_job import CompletionJob
            self.completion_job=CompletionJob(self.session.runtime)
            return
        if self.playing and self.state['mode']!='playing':
            try:self.stop(self.state['reason'] or '自动播放已取消。')
            except Exception as error:
                self.notice='停止尚未完成：'+str(error);return
        if self.intent is not None and not self.playing and self.state['mode']!='preparing':
            self.intent=None
        if self.intent is not None and not self.playing and self.projects.completion!=self.wait_completion:
            if self.projects.error:
                if self.intent in ('trial_prefix','trial_capture'):self.delay_ready=None
                self.notice='调试／播放准备失败：'+str(self.projects.error)
                self.intent=None;self.bridge.recording_mode('idle',True)
            else:self._arm()
        if self.playing:
            self.session.tick_playback(time.monotonic()*1000)
            playback=self.session.playback
            if not playback.busy:
                succeeded=playback.state=='finished' and not playback.cleanup_pending
                intent,self.intent=self.intent,None;self.playing=False
                trial=intent in ('trial_prefix','trial_restore')
                self.bridge.recording_mode('idle',not succeeded or trial)
                self.notice=('试调已结束；可改数值后重复试调，或确认当前等待。' if trial else '重放完成。') if succeeded else '播放停止：'+str(playback.error or '用户停止')
                if succeeded and intent=='trial_prefix':self._after_prefix()
                if succeeded and intent=='record':self.start_recording()
        self.state=self.bridge.recording_status()

    def _editable(self):
        if self.projects.busy or self.playing or self.session.state!='active' or self.owner is None:
            raise ValueError('请先停止播放并等待工程任务完成。')
        if self.session.playback is not None and self.session.playback.cleanup_pending:self.session.stop_playback()
        self.pull()
        if self.completion_job is not None or self.state['mode'] in ('recording','preparing','playing','completing'):
            raise ValueError('请先结束录制／播放，并等待 P 操作完成。')

    def shutdown_completion(self):
        if self.completion_job is None:return
        job=self.completion_job;job.cancel()
        try:job.future.result()
        except Exception:pass
        self.completion_job=None

    def apply_options(self,interval,extra,keys):
        self._editable();previous=self.session.timeline
        before=previous.to_document();timeline=RecordingTimeline.from_document(before)
        timeline.interval_ms=int(interval);timeline.extra_wait_ms=int(extra);timeline.tool_keys=tool_keys(keys)
        if timeline.interval_ms<2:raise ValueError('普通间隔至少为 2ms。')
        timeline.to_document()
        changed_interval=timeline.interval_ms!=previous.interval_ms
        if changed_interval:timeline.invalidate_from(0)
        timeline.dirty=True;self.session.timeline=timeline
        self.history.push(before,timeline.to_document())
        self._load(needs_replay=self.state['needsReplay'] or changed_interval)
        self.form_version+=1
        self.notice='设置已应用；额外等待默认值只影响新标记。'

    def apply_delays(self,interval,extra):
        self.apply_options(interval,extra,self.session.timeline.tool_keys)

    def apply_keys(self,keys,*,toggle=None):
        if self.projects.busy or self.playing or self.completion_job is not None:
            raise ValueError('请先停止任务再修改快捷键。')
        if self.owner is not None:self._editable()
        elif self.session.state!='closed':raise ValueError('请先完成会话恢复。')
        keys=tool_keys(keys);conflicts=self.read_bindings().conflicts(keys)
        if conflicts:raise ValueError('；'.join(conflicts))
        from .key_settings import parse_toggle,validate_toggle
        from .release_profile import active_tools
        vk=self.preferences.toggle_vk if toggle is None else parse_toggle(toggle)
        validate_toggle(vk,self.read_bindings(),active_tools(keys))
        self.preferences.save(keys,toggle=toggle)
        if hasattr(self.bridge,'set_toggle'):self.bridge.set_toggle(vk)
        if self.owner is not None:
            self.session.timeline.tool_keys=dict(keys);self.session.timeline.dirty=True
            self._load(needs_replay=self.state['needsReplay'])
        self.notice='快捷键已保存'

    def edit(self,id,*,delete=False,wait_ms=None,confirm=False,symbol=None):
        self._editable();timeline=self.session.timeline;needs=self.state['needsReplay']
        if symbol=='P':
            from .release_profile import check_steps
            check_steps([{'symbol':'P'}])
        before=timeline.to_document()
        if delete:timeline.delete_step(id);needs=True
        elif wait_ms is not None:
            from .timeline import Step
            replacement=Step('_',int(wait_ms))
            if timeline.steps[timeline.ids.index(id)]!=replacement:
                timeline.set_wait(id,replacement.wait_ms);needs=True
        elif symbol is not None:timeline.set_action(id,symbol);needs=True
        if confirm:timeline.mark_review(id,False)
        self.history.push(before,timeline.to_document())
        self._load(needs_replay=needs)
        self.notice=('已应用并标记已调；后续等待保留，受影响项待复核。' if confirm and needs else
                     '所选延时已确认。' if confirm else
                     '修改已保留；后续延时数值保留，受影响项待复核。' if needs else '修改已应用。')

    def insert(self,after_id,symbol):
        from .timeline import Step
        self._editable();timeline=self.session.timeline
        before=timeline.to_document()
        if symbol not in 'UDLRXV123456789P_' or len(symbol)!=1:raise ValueError('不支持的新增动作。')
        from .release_profile import check_steps
        check_steps([{'symbol':symbol}])
        id=timeline.insert_after(after_id,Step(symbol,timeline.extra_wait_ms if symbol=='_' else None))
        self.history.push(before,timeline.to_document())
        self._load(needs_replay=True)
        self.notice='已插入；后续等待保留并待复核。'
        return id

    def reorder(self,id,index):
        self._editable()
        before=self.session.timeline.to_document()
        if self.session.timeline.move_step(id,index):
            self.history.push(before,self.session.timeline.to_document())
            self._load(needs_replay=True)
            self.notice='顺序已修改；后续等待保留并待复核。'

    def _restore_edit(self,document):
        keys=dict(self.session.timeline.tool_keys)
        timeline=RecordingTimeline.from_document(document)
        timeline.tool_keys=keys;timeline.dirty=True
        self.session.timeline=timeline
        self._load(needs_replay=True);self.form_version+=1

    def undo_edit(self):
        self._editable();self._restore_edit(self.history.undo())
        self.notice='已撤销编辑；可在当前现场追加，或选择从起点播放。'

    def redo_edit(self):
        self._editable();self._restore_edit(self.history.redo())
        self.notice='已重做编辑；可在当前现场追加，或选择从起点播放。'

    def checkpoint_storage(self,*,prune=False):
        self._editable()
        if prune and (self.checkpoint_plan is None or not self.checkpoint_plan['candidates']):
            raise ValueError('请先查看容量，没有可清理的历史检查点。')
        protected=[dict(self.delay_ready)] if self.delay_ready is not None else []
        self.checkpoint_pending=self.projects.completion
        self.checkpoint_status='正在清理……' if prune else '正在核对容量……'
        self.projects.request('checkpoint_prune' if prune else 'checkpoint_scan',
                              plan=self.checkpoint_plan if prune else None,protected=protected)

    def checkpoint_summary(self):
        plan=self.checkpoint_plan or {}
        return dict(count=plan.get('count',0),bytes=plan.get('bytes',0),
            protected_count=plan.get('protected_count',0),skipped_count=plan.get('skipped_count',0),
            removable_count=len(plan.get('candidates',[])),
            removable_bytes=sum(e['bytes'] for e in plan.get('candidates',[])),
            message=self.checkpoint_status,ready=self.checkpoint_plan is not None)
