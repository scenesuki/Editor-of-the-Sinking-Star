"""Windows 只读接入；不发送输入、不加载存档、不更改游戏现场。"""

import ctypes
from ctypes import wintypes as w
import hashlib
from pathlib import Path
from dataclasses import asdict

from research.pe import PeImage
from research.process import ProcessReader
from .game_observer import read_game_sample
from .game_builds import select_build
from .keymap import GameKeymap, parse_user_keymap
from .playback_guard import GameObservation


_kernel = ctypes.WinDLL('kernel32', use_last_error=True)
_kernel.GetProcessTimes.argtypes = [w.HANDLE, *([ctypes.POINTER(w.FILETIME)] * 4)]
_kernel.GetProcessTimes.restype = w.BOOL
_kernel.GetExitCodeProcess.argtypes = [w.HANDLE, ctypes.POINTER(w.DWORD)]
_kernel.GetExitCodeProcess.restype = w.BOOL
_user = ctypes.WinDLL('user32', use_last_error=True)
_user.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
_user.GetWindowThreadProcessId.restype = w.DWORD
_user.GetForegroundWindow.argtypes = []
_user.GetForegroundWindow.restype = w.HWND
_user.GetAsyncKeyState.argtypes = [ctypes.c_int]
_user.GetAsyncKeyState.restype = ctypes.c_short


def sample_pressed_keys(mapping: GameKeymap, key_state=None) -> tuple[str, ...]:
    """采样操作绑定、方向键、数字和修饰键；不区分物理输入与工具注入。"""
    native = key_state if key_state is not None else _user.GetAsyncKeyState
    special = {'Up': 0x26, 'Down': 0x28, 'Left': 0x25, 'Right': 0x27,
               'Space': 0x20, 'Control': 0x11, 'Shift': 0x10, 'Alt': 0x12,
               'LeftWindows': 0x5b, 'RightWindows': 0x5c,
               'Tab': 9, 'Enter': 13, 'Backspace': 8, 'Escape': 27,'Delete':46}
    names = set(asdict(mapping).values()) | set(special) | set('0123456789')
    return tuple(sorted(key for key in names
                        if native(special[key] if key in special else ord(key)) & 0x8000))


def process_creation_id(handle) -> int:
    if not handle:
        raise ValueError('Process reader is closed')
    created, exited, kernel, user = [w.FILETIME() for _ in range(4)]
    if not _kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                                   ctypes.byref(kernel), ctypes.byref(user)):
        raise ctypes.WinError(ctypes.get_last_error())
    return (created.dwHighDateTime << 32) | created.dwLowDateTime


def read_keymap(path: Path) -> tuple[GameKeymap, str]:
    try:
        with Path(path).open('rb') as stream:
            data = stream.read(1024 * 1024 + 1)
    except FileNotFoundError:
        return GameKeymap(), 'missing:defaults'
    if len(data) > 1024 * 1024:
        raise ValueError('User.keymap is too large')
    return parse_user_keymap(data.decode('utf-8-sig')), hashlib.sha256(data).hexdigest()


class WindowsGameObserver:
    def __init__(self, pid: int, window: int, keymap_path: Path) -> None:
        self.reader = ProcessReader(pid)
        try:
            path = Path(self.reader.path)
            if path.name.casefold() != 'sinking_star.exe':
                raise ValueError('Expected sinking_star.exe')
            data = path.read_bytes()
            self.sha256 = hashlib.sha256(data).hexdigest()
            self.build=select_build(data)
            image = PeImage(data)
            self._code = []
            for rva in self.build.observer_guards:
                offset = image.rva_to_offset(rva)
                self._code.append((self.reader.image_base + rva, data[offset:offset + 32]))
            self.pid, self.window = pid, window
            self.creation_id = process_creation_id(self.reader.handle)
            self.keymap_path = Path(keymap_path)
            self.mapping, self.keymap_digest = read_keymap(self.keymap_path)
            self.initial = self.observe()
        except BaseException:
            self.reader.close()
            raise

    def observe(self) -> GameObservation:
        if not self.reader.handle:
            raise ValueError('Game observer is closed')
        exit_code = w.DWORD()
        if not _kernel.GetExitCodeProcess(self.reader.handle, ctypes.byref(exit_code)):
            raise ctypes.WinError(ctypes.get_last_error())
        if exit_code.value != 259:
            raise RuntimeError('Game process exited')
        creation = process_creation_id(self.reader.handle)
        if creation != self.creation_id:
            raise RuntimeError('Game process identity changed')
        window_pid = w.DWORD()
        if not _user.GetWindowThreadProcessId(self.window, ctypes.byref(window_pid)) or window_pid.value != self.pid:
            raise RuntimeError('Game window identity changed')
        for address, expected in self._code:
            if self.reader.read(address, len(expected)) != expected:
                raise ValueError('Game code differs from verified build')
        _, digest = read_keymap(self.keymap_path)
        sample = read_game_sample(self.reader.read, self.reader.image_base,build=self.build)
        return GameObservation(
            identity=(self.pid, self.window, creation),
            foreground=_user.GetForegroundWindow() == self.window,
            game_ms=sample.game_ms, scene=sample.manager, keymap_digest=digest,
            emergency=bool(_user.GetAsyncKeyState(0x1b) & 0x8000),
            level_name=sample.level_name, pressed_keys=sample_pressed_keys(self.mapping))

    def close(self) -> None:
        self.reader.close()

    def __enter__(self):
        return self

    def __exit__(self, *exception):
        self.close()
