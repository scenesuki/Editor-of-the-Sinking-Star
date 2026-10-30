"""操作时间轴模型。这里不发送游戏输入，也不声称游戏现场已同步。"""

from dataclasses import dataclass


_SYMBOLS = frozenset("UDLRCXFVP0123456789_!")
_NON_UNDOABLE = frozenset("CP0123456789_!")


@dataclass(frozen=True)
class Step:
    symbol: str
    wait_ms: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or len(self.symbol) != 1 or self.symbol not in _SYMBOLS:
            raise ValueError("Unsupported operation symbol")
        if self.symbol == "_":
            if type(self.wait_ms) is not int or not 0 < self.wait_ms <= 2_147_483_647:
                raise ValueError("Wait duration must be a positive millisecond count")
        elif self.wait_ms is not None:
            raise ValueError("Only wait steps have durations")


class SolutionTimeline:
    def __init__(self, steps: list[Step] | None = None, *, playhead: int = 0):
        self.steps = list(steps or [])
        if any(not isinstance(step, Step) for step in self.steps):
            raise ValueError("Timeline contains an invalid step")
        if type(playhead) is not int or not 0 <= playhead <= len(self.steps):
            raise ValueError("Playhead outside timeline")
        self.playhead = playhead
        self.caret = playhead
        self.anchor = playhead
        self.dirty = False

    def move_caret(self, position: int, *, select: bool = False) -> None:
        if type(position) is not int or not 0 <= position <= len(self.steps):
            raise ValueError("Caret outside timeline")
        self.caret = position
        if not select:
            self.anchor = position

    def replace_selection(self, replacement: list[Step]) -> bool:
        first, last = sorted((self.caret, self.anchor))
        if first < self.playhead:
            raise ValueError("Cannot insert into executed steps")
        if any(not isinstance(step, Step) for step in replacement):
            raise ValueError("Replacement contains an invalid step")
        if self.steps[first:last] == replacement:
            return False
        self.steps[first:last] = replacement
        self.move_caret(first + len(replacement))
        self.dirty = True
        return True

    def record(self, step: Step) -> None:
        """在游戏实际收到操作后记录；调用方负责确认游戏侧结果。"""
        if not isinstance(step, Step):
            raise ValueError("Invalid recorded step")
        self.steps.insert(self.playhead, step)
        if self.caret >= self.playhead:
            self.caret += 1
        if self.anchor >= self.playhead:
            self.anchor += 1
        self.playhead += 1
        self.dirty = True

    def acknowledge_game_undo(self) -> bool:
        """游戏撤销成功后，移动到被撤销的上一操作；不自行发送 Z。"""
        for index in range(self.playhead - 1, -1, -1):
            symbol = self.steps[index].symbol
            if symbol in ("!", "P"):
                return False
            if symbol not in _NON_UNDOABLE:
                following = self.caret == self.playhead and self.anchor == self.playhead
                self.playhead = index
                if following:
                    self.caret = index
                    self.anchor = index
                return True
        return False
