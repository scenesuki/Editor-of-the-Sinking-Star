"""以单调实时时钟播放操作宏；计数表示已发送，不要求场景或游戏时钟对齐。"""
from .key_worker import ALLOWED_KEYS
from .keymap import key_for_step
from .transport import OperationTransport


class MacroPlayback:
    def __init__(self, timeline, mapping, expected, observe, emit, cleanup, *, speed=1, focus_delay_ms=1000,
                 cycle_ms=250,hold_ms=60,special=None):
        self.timeline = timeline
        self.transport = OperationTransport(timeline, mapping, speed=speed,cycle_ms=cycle_ms,hold_ms=hold_ms,special=special)
        self.expected, self.observe, self.emit, self.cleanup = expected, observe, emit, cleanup
        self.focus_delay_ms = focus_delay_ms
        self.state = 'idle'; self.error = None; self.cleanup_pending = False
        self._cleaned = False; self._focus_since = None; self._last_wall = None
        self._accepted_step = None

    @property
    def busy(self): return self.state in ('armed','running')

    def arm(self, wall_ms, *, single_step=False):
        if self.state != 'idle': raise ValueError('请创建新的宏发送会话。')
        self._wall(wall_ms)
        first = self.timeline.playhead
        last = min(first+1,len(self.timeline.steps)) if single_step else len(self.timeline.steps)
        if first == last: raise ValueError('没有待发送步骤，请回到工程起点或添加步骤。')
        for step in self.timeline.steps[first:last]:
            if step.symbol=='P':
                if self.transport.special is None:raise ValueError('当前发送器不支持 P 快速完成。')
                continue
            if step.symbol != '_' and key_for_step(self.transport.mapping,step) not in ALLOWED_KEYS:
                raise ValueError('操作绑定不受当前按键发送器支持。')
        self._plan = (tuple(self.timeline.steps), first)
        self._single = single_step; self._armed_at = wall_ms; self._last_wall = wall_ms
        self.state = 'armed'

    @staticmethod
    def _wall(value):
        from .playback_guard import GuardedPlayback
        GuardedPlayback._wall(value)

    def _validate(self, sample, *, focused):
        if sample.identity != self.expected.identity: raise RuntimeError('游戏进程或窗口已变化。')
        if sample.keymap_digest != self.expected.keymap_digest: raise RuntimeError('游戏键位已变化，请重新准备播放。')
        if sample.emergency: raise RuntimeError('已触发 Escape 紧急停止。')
        if focused:
            if not sample.foreground: raise RuntimeError('游戏失焦，已停止发送。')
            if any(key != self.transport.held_key for key in sample.pressed_keys):
                raise RuntimeError('检测到其他游戏按键，已停止发送。')

    def _emit(self, key, down):
        if down: self._validate(self.observe(), focused=True)
        result = self.emit(key,down)
        if down:
            self._accepted_step=self.timeline.playhead
            self._validate(self.observe(), focused=True)
        return result

    def _finish(self, state):
        release_error = None
        try: self.transport.stop(self.emit)
        except Exception as error: release_error = str(error)
        if self._accepted_step == self.timeline.playhead:self.timeline.playhead += 1
        self._accepted_step=None
        try:
            confirmed = self.cleanup()
        except Exception as error:
            self.error = self.error or str(error); self.cleanup_pending = True
        else:
            self.cleanup_pending = release_error is not None and confirmed is not True
            self._cleaned = not self.cleanup_pending
        if release_error: self.error = self.error or release_error
        self.state = 'fault' if self.cleanup_pending else state

    def stop(self):
        if self._cleaned and not self.busy and not self.cleanup_pending: return
        self._finish('stopped' if self.state != 'fault' else 'fault')

    def tick(self, wall_ms):
        if not self.busy: return
        try:
            self._wall(wall_ms)
            if wall_ms < self._last_wall: raise ValueError('单调时钟倒退。')
            gap = wall_ms-self._last_wall
            self._last_wall = wall_ms
            sample = self.observe()
            self._validate(sample, focused=self.state == 'running')
            if self.state == 'armed':
                if self._plan != (tuple(self.timeline.steps),self.timeline.playhead):
                    raise RuntimeError('准备期间操作序列发生变化。')
                if wall_ms-self._armed_at >= 30000: raise RuntimeError('等待游戏前台超时。')
                if not sample.foreground or sample.pressed_keys or gap >= 500:
                    self._focus_since = None
                elif self._focus_since is None: self._focus_since = wall_ms
                if self._focus_since is None or wall_ms-self._focus_since < self.focus_delay_ms: return
                if self._single: self.transport.step()
                else: self.transport.play()
                self.state = 'running'
            elif gap >= 500: raise RuntimeError('界面轮询停顿，已停止发送。')
            self.transport.tick(wall_ms,self._emit)
            self._last_wall = max(wall_ms,self.transport._last_now or wall_ms)
            if not self.transport.active: self._finish('finished')
        except Exception as error:
            self.error = str(error)
            self._finish('fault')
