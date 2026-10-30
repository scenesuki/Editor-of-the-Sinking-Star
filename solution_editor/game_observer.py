"""按已核对构建读取游戏时钟与场景。"""

from dataclasses import dataclass
import math
import re
import struct
from .game_builds import LEGACY


GAME_SHA256 = LEGACY.sha256  # 旧接口默认值；真实进程由完整指纹选择地址表。


@dataclass(frozen=True)
class GameSample:
    manager: int
    level_name: str
    game_ms: float


def read_game_sample(read, base: int, *, build=LEGACY) -> GameSample:
    """调用者必须先核验 EXE 指纹。双读检测变化，不是暂停或原子快照。"""
    def take(address, size):
        if not 0 < address < 2**64 or address + size > 2**64:
            raise ValueError('Invalid game address')
        data = read(address, size)
        if len(data) != size:
            raise OSError('Incomplete game sample')
        return data

    mode_address = base + build.rvas['mode']
    manager_address = base + build.rvas['manager']
    mode = take(mode_address, 8)
    if mode != bytes(8):
        raise ValueError('Gameplay mode is not active')
    root = take(manager_address, 8)
    manager = struct.unpack('<Q', root)[0]
    if not manager:
        raise ValueError('No gameplay manager')
    header = take(manager, 16)
    count, name_pointer = struct.unpack('<QQ', header)
    if not 1 <= count <= 128 or not name_pointer:
        raise ValueError('Invalid scene name header')
    raw_name = take(name_pointer, count)
    if not re.fullmatch(rb'[A-Za-z0-9_.-]+', raw_name) or raw_name in (b'.', b'..'):
        raise ValueError('Invalid scene name')
    seconds = struct.unpack('<d', take(base + build.rvas['clock'], 8))[0]
    milliseconds = seconds * 1000
    if not math.isfinite(milliseconds) or milliseconds < 0:
        raise ValueError('Invalid game clock')
    if (take(manager_address, 8) != root or take(manager, 16) != header
            or take(name_pointer, count) != raw_name or take(mode_address, 8) != mode
            or take(manager_address, 8) != root):
        raise ValueError('Game scene changed during observation')
    return GameSample(manager, raw_name.decode('ascii'), milliseconds)
