"""存档工程窗口的会话逻辑；脚本和固定起点分别保存，失败保留恢复材料。"""
from pathlib import Path
import time

from .campaign_project import CampaignProject
from .game_observer import GAME_SHA256
from .script_store import read_script, write_script
from .timeline import SolutionTimeline


def connect_runtime(root):
    from .campaign_connection import discover_game
    from .campaign_runtime import CampaignRuntime
    return CampaignRuntime(discover_game(), root)


def connect_input(runtime):
    from .macro_input import MacroConnection
    return MacroConnection(runtime)


class CampaignEditorSession:
    def __init__(self, connect=connect_runtime, *, game_sha256=GAME_SHA256):
        self.connect, self.game_sha256 = connect, game_sha256
        self.runtime = self.root = None
        self.timeline = SolutionTimeline()
        self.fingerprint = None
        self.state = 'closed'
        self.notice = ''
        self._script_loaded = False

        self.playback = None
        self._input_connection = None
        self.connect_input = connect_input

    @property
    def script_path(self):
        return self.root / 'script.json' if self.root else None

    def _attach(self, root):
        if self.runtime is not None: raise ValueError('请先退出当前工程或完成恢复。')
        self.root = Path(root).absolute()
        self.runtime = self.connect(self.root)
        build = getattr(self.runtime, 'build', None)
        if build is not None: self.game_sha256 = build.sha256
        self.timeline, self.fingerprint = SolutionTimeline(), None
        self.notice = ''; self._script_loaded = False
        self.state = 'connected'

    def _failed(self):
        # 发布过的工程可能有中断会话，不能因响应丢失而假定未载入副本。
        if (self.root / 'project.json').exists(): self.state = 'recovery'
        else: self.disconnect()

    def create(self, root, name):
        if Path(root).exists(): raise FileExistsError('工程目录已存在，请选择新的目录。')
        self._attach(root)
        try:
            self.runtime.command(dict(action='create_auto', name=name))
            self.fingerprint = write_script(self.script_path, self.timeline, expected_fingerprint=None)
            self._script_loaded = True
            self.runtime.command(dict(action='enter_auto'))
            self.state = 'active'
        except Exception:
            self._failed(); raise

    def open(self, root):
        self._attach(root)
        try:
            # 恢复不依赖脚本或固定起点仍完好，避免损坏文件阻塞返回及清理。
            project = CampaignProject.open(self.root, game_sha256=self.game_sha256, verify_initial=False)
            if project.pending() is not None:
                self.state = 'recovery'
                try: self._load_script(project)
                except Exception as error:
                    self.notice = '脚本／草稿未载入，仍可恢复原存档：'+str(error)
                return
            self._load_script(project)
            self.runtime.command(dict(action='enter_auto'))
            self.state = 'active'
        except Exception:
            # 未进入且没有待恢复会话时可以安全释放控制器。
            try:
                pending = CampaignProject.open(self.root, game_sha256=self.game_sha256,
                                               verify_initial=False).pending()
            except Exception:
                self._failed()
            else:
                if pending is None: self.disconnect()
                else: self.state = 'recovery'
            raise

    def _load_script(self, project):
        from .script_recovery import restore
        timeline, fingerprint = (read_script(self.script_path) if self.script_path.exists()
                                 else (SolutionTimeline(), None))
        draft = restore(project, timeline, fingerprint)
        self.timeline, self.fingerprint = (draft if draft is not None else timeline), fingerprint
        self._script_loaded = True
        if draft is not None: self.notice = '已恢复未保存草稿，请保存工程。'

    def preserve_draft(self):
        if self.root is None or not self.timeline.dirty: return
        if not self._script_loaded: raise ValueError('脚本未成功载入，不能覆盖恢复草稿。')
        from .script_recovery import preserve
        project = CampaignProject.open(self.root, game_sha256=self.game_sha256, verify_initial=False)
        preserve(project, self.timeline, self.fingerprint)
        self.notice = '未保存操作已保全为草稿，重新打开工程可继续。'

    def save(self):
        if self.runtime is None or self.state not in ('active', 'recovery'):
            raise ValueError('请先打开工程。')
        if not self._script_loaded: raise ValueError('脚本未成功载入，不能用空白稿覆盖原文件。')
        self.fingerprint = write_script(self.script_path, self.timeline,
                                        expected_fingerprint=self.fingerprint)
        from .script_recovery import clear
        try:
            clear(CampaignProject.open(self.root, game_sha256=self.game_sha256, verify_initial=False))
        except Exception:
            self.timeline.dirty = True
            raise
        self.notice = ''

    def leave(self, *, discard=False):
        if self.runtime is None: return
        if self.timeline.dirty and not discard: raise ValueError('请先保存或明确放弃修改。')
        self.stop_playback()
        try:
            self.runtime.command(dict(action='exit_auto'))
            if discard:
                from .script_recovery import clear
                clear(CampaignProject.open(self.root, game_sha256=self.game_sha256, verify_initial=False))
            self.disconnect(preserve=not discard)
        except Exception:
            self.state = 'recovery'
            raise

    def recover(self):
        if self.state != 'recovery': raise ValueError('当前没有待恢复的会话。')
        self.stop_playback()
        self.preserve_draft()
        try:
            self.runtime.command(dict(action='recover_auto'))
            self.disconnect()
        except Exception:
            self.state = 'recovery'
            raise

    def disconnect(self, *, preserve=True):
        # 仅解除钩子和控制器；从不把“断开”当作清理会话。
        self.stop_playback()
        if preserve: self.preserve_draft()
        if self.runtime is not None:
            self.runtime.close()
            self.runtime = None
        self.state = 'closed'
        self.playback = None

    def stop_playback(self):
        if self.playback is not None:
            self.playback.stop()
            if self.playback.cleanup_pending:
                raise RuntimeError('按键释放尚未确认，不能切换存档；请再次停止或等待输入进程结束。')
            self._input_connection = None
        elif self._input_connection is not None:
            self._input_connection.close()
            self._input_connection = None

    def start_playback(self, *, single_step=False, speed=1, timeline=None, focus_delay_ms=1000):
        if self.state != 'active' or self.runtime is None:raise ValueError('请先进入工程副本。')
        self.stop_playback()
        from .macro_playback import MacroPlayback
        from .transport import OperationTransport
        from .keymap import GameKeymap
        timeline=self.timeline if timeline is None else timeline
        from .release_profile import check_steps
        check_steps(timeline.steps)
        cycle=getattr(timeline,'interval_ms',250)
        if type(cycle) is not int or cycle<2:raise ValueError('普通间隔至少为 2ms。')
        hold=min(60,max(1,cycle//3))
        OperationTransport(timeline,GameKeymap(),speed=speed,cycle_ms=cycle,hold_ms=hold)
        if timeline.playhead >= len(timeline.steps):raise ValueError('没有待发送步骤，请回到起点或添加步骤。')
        self.playback = None
        connection = self.connect_input(self.runtime)
        self._input_connection = connection
        try:
            self.playback = MacroPlayback(timeline,connection.mapping,connection.initial,
                connection.observe,connection.emit,connection.close,speed=speed,cycle_ms=cycle,hold_ms=hold,
                focus_delay_ms=focus_delay_ms,special=getattr(connection,'special',None))
            self.playback.arm(time.monotonic()*1000,single_step=single_step)
        except Exception:
            self.stop_playback();raise

    def tick_playback(self,wall_ms):
        if self.playback is not None:self.playback.tick(wall_ms)

    def reset_start(self):
        if self.state != 'active' or self.runtime is None:raise ValueError('请先进入工程副本。')
        self.stop_playback()
        try:
            self.runtime.command(dict(action='exit_auto'))
            self.runtime.command(dict(action='enter_auto'))
            self.timeline.playhead=0
            self.playback=None
        except Exception:
            self.state='recovery';raise

    def checkpoint(self,action,key):
        if self.state!='active' or self.runtime is None:raise ValueError('请先进入工程副本。')
        if action not in ('checkpoint_capture','checkpoint_restore'):raise ValueError('Invalid checkpoint action')
        self.stop_playback()
        try:return self.runtime.command(dict(action=action,key=key))
        except Exception:
            if action=='checkpoint_restore':self.state='recovery'
            raise
