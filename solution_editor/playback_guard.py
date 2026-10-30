"""受控实验播放的观测与停止保护。"""

from collections.abc import Callable
from dataclasses import dataclass
import math

from .transport import EmitKey, OperationTransport


@dataclass(frozen=True)
class GameObservation:
    identity: tuple[int, int, int]  # PID、窗口、进程创建时间；防止 PID／句柄复用。
    foreground: bool
    game_ms: float
    scene: int
    keymap_digest: str
    emergency: bool
    level_name: str = ''
    pressed_keys: tuple[str, ...] = ()  # 当前采样按键；不能识别同键来源或轮询间短按。


class GuardedPlayback:
    """只保证发送流程，不能证明游戏接受动作或完整现场对齐。

    tick 必须由调用者持续调度。它能发现上次轮询后的延误，但不能在调用者
    挂起／崩溃期间执行释放；正式发送端还需要独立的失联释放机制。
    """

    def __init__(self, transport: OperationTransport, expected: GameObservation,
                 observe: Callable[[], GameObservation], emit: EmitKey,
                 *, stall_ms: int = 500) -> None:
        if type(stall_ms) is not int or stall_ms <= 0:
            raise ValueError('Invalid stall timeout')
        self.transport = transport
        self.expected = expected
        self.observe = observe
        self.emit = emit
        self.stall_ms = stall_ms
        self.running = False
        self.fault: str | None = None
        self.cleanup_error: str | None = None
        self._last_wall: float | None = None
        self._last_game: float | None = None
        self._progress_wall = 0.0

    @property
    def cleanup_pending(self) -> bool:
        return self.cleanup_error is not None

    def _validate(self, observed: GameObservation) -> None:
        if observed.identity != self.expected.identity:
            raise RuntimeError('Game process or window identity changed')
        if not observed.foreground:
            raise RuntimeError('Game focus lost')
        if observed.emergency:
            raise RuntimeError('Emergency stop')
        if any(key != self.transport.held_key for key in observed.pressed_keys):
            raise RuntimeError('External gameplay key or modifier detected')
        if (not observed.scene or observed.scene != self.expected.scene
                or observed.level_name != self.expected.level_name):
            raise RuntimeError('Gameplay scene changed')
        if observed.keymap_digest != self.expected.keymap_digest:
            raise RuntimeError('Game keymap changed')
        if (type(observed.game_ms) not in (int, float)
                or not math.isfinite(observed.game_ms) or observed.game_ms < 0):
            raise ValueError('Invalid game clock')

    @staticmethod
    def _wall(value: float) -> None:
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError('Invalid monotonic clock')

    def start(self, wall_ms: float, *, single_step: bool = False) -> None:
        if self.fault is not None or self.cleanup_pending:
            raise RuntimeError('Playback fault requires a new verified session')
        if self.running:
            raise RuntimeError('Playback is already running')
        self._wall(wall_ms)
        first = self.transport.timeline.playhead
        last = first + 1 if single_step else len(self.transport.timeline.steps)
        if any(s.symbol == '!' for s in self.transport.timeline.steps[first:last]):
            raise ValueError('Restart confirmation is not implemented')
        observed = self.observe()
        self._validate(observed)
        if single_step:
            self.transport.step()
        else:
            self.transport.play()
        self._last_wall = wall_ms
        self._last_game = observed.game_ms
        self._progress_wall = wall_ms
        self.running = self.transport.active

    def _emit_guarded(self, key: str, down: bool) -> float | None:
        # 焦点检查不阻止释放。不得因失焦而留下本工具持有的按键。
        if down:
            self._validate(self.observe())
        self.emit(key, down)
        if down:
            acknowledged = self.observe()
            self._validate(acknowledged)
            return acknowledged.game_ms
        return None

    def stop(self) -> None:
        self.running = False
        try:
            self.transport.stop(self.emit)
        except Exception as error:
            self.cleanup_error = str(error)
            self.fault = self.fault or f'Key release failed: {error}'
        else:
            self.cleanup_error = None

    def tick(self, wall_ms: float) -> None:
        if not self.running:
            return
        try:
            self._wall(wall_ms)
            if self._last_wall is not None:
                if wall_ms < self._last_wall:
                    raise RuntimeError('Monotonic clock moved backwards')
                if wall_ms - self._last_wall >= self.stall_ms:
                    raise RuntimeError('Playback polling stalled')
            self._last_wall = wall_ms
            observed = self.observe()
            self._validate(observed)
            if observed.game_ms != self._last_game:
                self._last_game = observed.game_ms
                self._progress_wall = wall_ms
            elif wall_ms - self._progress_wall >= self.stall_ms:
                raise RuntimeError('Game clock stalled')
            self.transport.tick(observed.game_ms, self._emit_guarded)
            self.running = self.transport.active
        except Exception as error:
            self.fault = str(error)
            self.transport.aligned = False
            self.stop()
