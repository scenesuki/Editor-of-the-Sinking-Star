"""以游戏时间驱动的操作周期。调用方负责窗口、焦点和真实游戏结果核验。"""

from collections.abc import Callable
import math

from .keymap import GameKeymap, key_for_step
from .timeline import SolutionTimeline


EmitKey = Callable[[str, bool], float | None]


class OperationTransport:
    def __init__(self, timeline: SolutionTimeline, mapping: GameKeymap,
                 *, cycle_ms: int = 250, hold_ms: int = 60, speed: float = 1, special=None) -> None:
        if type(cycle_ms) is not int or type(hold_ms) is not int or not 0 < hold_ms < cycle_ms:
            raise ValueError("Invalid operation key cycle")
        if type(speed) not in (int,float) or not math.isfinite(speed) or not .25 <= speed <= 4:
            raise ValueError('Playback speed must be between 0.25 and 4')
        self.timeline = timeline
        self.mapping = mapping
        self.cycle_ms = max(hold_ms+1,round(cycle_ms/speed))
        self.hold_ms = hold_ms
        self.speed = speed
        self.special = special
        self.aligned = True
        self._target = timeline.playhead
        self._phase = "idle"
        self._deadline = 0.0
        self._pressed_at = 0.0
        self._held_key: str | None = None
        self._last_now: float | None = None
        self._planned_steps: tuple | None = None
        self._expected_playhead = timeline.playhead
        self._next_step_at = 0.0

    @property
    def held_key(self) -> str | None:
        return self._held_key

    @property
    def active(self) -> bool:
        return self._target > self.timeline.playhead or self._phase != "idle" or self._held_key is not None

    def play(self) -> None:
        if not self.aligned:
            raise RuntimeError("Game and timeline alignment is unknown")
        self._target = len(self.timeline.steps)
        self._planned_steps = tuple(self.timeline.steps)
        self._expected_playhead = self.timeline.playhead

    def step(self) -> None:
        self.play()
        self._target = min(self.timeline.playhead + 1, len(self.timeline.steps))

    def stop(self, emit: EmitKey) -> None:
        self._target = self.timeline.playhead
        self._planned_steps = None
        if self._phase in ("hold", "wait", "special"):
            self.aligned = False
        if self._held_key is not None:
            try:
                emit(self._held_key, False)
            except Exception:
                self.aligned = False
                self._target = self.timeline.playhead
                raise
            self._held_key = None
        self._phase = "idle"

    def tick(self, game_now_ms: float, emit: EmitKey) -> None:
        if not self.aligned:
            raise RuntimeError("Game and timeline alignment is unknown")
        if not isinstance(game_now_ms, (int, float)) or not math.isfinite(game_now_ms) or game_now_ms < 0:
            self.stop(emit)
            self.aligned = False
            raise ValueError("Invalid game clock")
        if self._planned_steps is not None and tuple(self.timeline.steps) != self._planned_steps:
            self.stop(emit)
            self.aligned = False
            raise RuntimeError("Timeline changed during playback")
        if self._planned_steps is not None and self.timeline.playhead != self._expected_playhead:
            self.stop(emit)
            self.aligned = False
            raise RuntimeError("Timeline position changed during playback")
        if self._last_now is not None and game_now_ms < self._last_now:
            self.stop(emit)
            self.aligned = False
            raise RuntimeError("Game clock moved backwards")
        self._last_now = game_now_ms
        if self._phase == "wait":
            if game_now_ms < self._deadline:
                return
            self.timeline.playhead += 1
            self._expected_playhead = self.timeline.playhead
            self._phase = "idle"
            return
        if self._phase == "hold":
            if game_now_ms < self._deadline:
                return
            assert self._held_key is not None
            try:
                emit(self._held_key, False)
            except Exception:
                self.aligned = False
                self._target = self.timeline.playhead
                raise
            self._held_key = None
            self.timeline.playhead += 1
            self._expected_playhead = self.timeline.playhead
            self._phase = "gap"
            self._deadline = self._pressed_at + self.cycle_ms
            return
        if self._phase == "gap":
            if game_now_ms < self._deadline:
                return
            self._phase = "idle"
        if self._target <= self.timeline.playhead:
            self._planned_steps = None
            return
        if game_now_ms < self._next_step_at:
            return
        step = self.timeline.steps[self.timeline.playhead]
        if step.symbol == 'P':
            if self.special is None:raise ValueError('当前发送器不支持 P 快速完成。')
            self._phase='special'
            if self.special('P'):
                self.timeline.playhead+=1;self._expected_playhead=self.timeline.playhead
                self._phase='gap';self._deadline=game_now_ms+self.cycle_ms
            return
        if step.symbol == "_":
            assert step.wait_ms is not None
            self._phase = "wait"
            self._deadline = game_now_ms + step.wait_ms / self.speed
            return
        key = key_for_step(self.mapping, step)
        if key is None:
            raise ValueError("No key for operation step")
        self._held_key = key
        try:
            acknowledged_at = emit(key, True)
            if acknowledged_at is not None:
                if (type(acknowledged_at) not in (int, float)
                        or not math.isfinite(acknowledged_at) or acknowledged_at < game_now_ms):
                    raise ValueError('Invalid acknowledged game clock')
                game_now_ms = acknowledged_at
                self._last_now = acknowledged_at
        except Exception:
            self.aligned = False
            self._target = self.timeline.playhead
            try:
                emit(key, False)
            except Exception:
                pass
            else:
                self._held_key = None
            raise
        self._pressed_at = game_now_ms
        self._next_step_at = game_now_ms + self.cycle_ms
        self._deadline = game_now_ms + self.hold_ms
        self._phase = "hold"
