"""解析游戏 User.keymap 中与操作编辑器相关的键位；不发送输入。"""

from dataclasses import dataclass, replace
from pathlib import Path

from .timeline import Step


@dataclass(frozen=True)
class GameKeymap:
    up: str = "W"
    down: str = "S"
    left: str = "A"
    right: str = "D"
    activate: str = "X"
    switch_character: str = "C"
    dragon: str = "F"
    take: str = "V"
    restart: str = "R"
    undo: str = "Z"
    fast: str = "Space"
    slow: str = "Control"
    select_1: str = '1'
    select_2: str = '2'
    select_3: str = '3'
    select_4: str = '4'
    select_5: str = '5'
    select_6: str = '6'
    select_7: str = '7'
    select_8: str = '8'
    select_9: str = '9'


_ACTIONS = {
    "forward": "up", "backward": "down", "left": "left", "right": "right",
    "activate": "activate", "characterswitch": "switch_character",
    "friendlydragon": "dragon", "takeordrop": "take", "restart": "restart",
    "undo": "undo", "holdforfasttime": "fast", "holdforslowtime": "slow",
}
_NAMES = {name.casefold(): name for name in (
    "Space", "Shift", "Control", "Alt", "Tab", "Enter", "Backspace",
    "Up", "Down", "Left", "Right", "Escape",
)}


def _key_name(raw: str) -> str:
    if len(raw) == 1 and raw.isascii() and raw.isalnum():
        return raw.upper()
    key = _NAMES.get(raw.casefold())
    if key is None:
        raise ValueError(f"Unsupported User.keymap key: {raw}")
    return key


def parse_user_keymap(source: str) -> GameKeymap:
    mapping = GameKeymap()
    keyboard = False
    for raw in source.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("["):
            keyboard = line.casefold() == "[userkeyboard]"
            continue
        if not keyboard:
            continue
        parts = line.split()
        if len(parts) != 2:
            continue
        name, action = parts
        field = _ACTIONS.get(action.casefold())
        if field is not None:
            mapping = replace(mapping, **{field: _key_name(name)})
    return mapping


def load_game_keymap(path: Path) -> tuple[GameKeymap, bool]:
    try:
        source = Path(path).read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return GameKeymap(), False
    return parse_user_keymap(source), True


def key_for_step(mapping: GameKeymap, step: Step) -> str | None:
    field = {
        "U": "up", "D": "down", "L": "left", "R": "right",
        "X": "activate", "C": "switch_character", "F": "dragon",
        "V": "take", "!": "restart",
    }.get(step.symbol)
    if field is not None:
        return getattr(mapping, field)
    if step.symbol.isdigit():
        return getattr(mapping,'select_'+step.symbol,step.symbol)
    return None
