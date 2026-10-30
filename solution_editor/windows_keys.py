"""Windows 键盘事件与独立工作进程入口，仅供受控实验。"""

import argparse
import ctypes
from ctypes import wintypes as w
from pathlib import Path
import sys
import json
import secrets

from .key_worker import ALLOWED_KEYS, PressRejected, serve
from .windows_observer import WindowsGameObserver, _user
from .windows_input_events import WindowsInputEvents


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk', w.WORD), ('wScan', w.WORD), ('dwFlags', w.DWORD),
                ('time', w.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [('dx', w.LONG), ('dy', w.LONG), ('mouseData', w.DWORD),
                ('dwFlags', w.DWORD), ('time', w.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


class INPUTUNION(ctypes.Union):
    _fields_ = [('ki', KEYBDINPUT), ('mi', MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ('data',)
    _fields_ = [('type', w.DWORD), ('data', INPUTUNION)]


_user.SendInput.argtypes = [w.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
_user.SendInput.restype = w.UINT
_SPECIAL = {'Up': 0x26, 'Down': 0x28, 'Left': 0x25, 'Right': 0x27, 'Space': 0x20,
            'Tab':9, 'Enter':13, 'Backspace':8, 'Delete':46}


def send_key(key: str, down: bool, *, send_input=None, extra_info=0) -> None:
    if key not in ALLOWED_KEYS or type(down) is not bool:
        raise ValueError('Unsupported experimental input key')
    vk = _SPECIAL[key] if key in _SPECIAL else ord(key)
    flags = (0 if down else 2) | (1 if key in ('Up', 'Down', 'Left', 'Right', 'Delete') else 0)
    packet = INPUT(type=1, data=INPUTUNION(ki=KEYBDINPUT(vk, 0, flags, 0, extra_info)))
    native = send_input if send_input is not None else _user.SendInput
    if native(1, ctypes.byref(packet), ctypes.sizeof(packet)) != 1:
        raise OSError('SendInput did not accept the keyboard event')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--window', type=int, required=True)
    parser.add_argument('--keymap', type=Path, required=True)
    parser.add_argument('--ready', action='store_true')
    parser.add_argument('--campaign')
    parser.add_argument('--save-root',type=Path)
    parser.add_argument('--creation',type=int)
    parser.add_argument('--live-bindings',action='store_true')
    args = parser.parse_args()
    if args.campaign:
        if args.save_root is None or args.creation is None:parser.error('Macro target requires save root and creation identity')
        from .macro_input import CampaignInputObserver
        target=CampaignInputObserver(args.pid,args.window,args.keymap,args.save_root,args.campaign,creation=args.creation,
                                    live_bindings=args.live_bindings)
    else:target=WindowsGameObserver(args.pid,args.window,args.keymap)
    with target as observer:
        initial = observer.initial
        owned_key = None
        own_tag = secrets.randbits(63) | 1
        events = WindowsInputEvents(args.window, own_tag)

        def check_held():
            events.check()
            current = observer.observe()
            if (not current.foreground or current.emergency
                    or current.identity != initial.identity
                    or (current.scene, current.level_name) != (initial.scene, initial.level_name)
                    or current.keymap_digest != initial.keymap_digest):
                raise RuntimeError('Input target is no longer safe')
            if any(key != owned_key for key in current.pressed_keys):
                raise RuntimeError('External gameplay key or modifier detected')

        def emit(key, down):
            nonlocal owned_key
            if down:
                try:
                    check_held()
                    vk = _SPECIAL[key] if key in _SPECIAL else ord(key)
                    # 已按下的物理键或组合修饰键会改变输入含义；不抢占用户按键。
                    if any(_user.GetAsyncKeyState(code) & 0x8000
                           for code in (vk, 0x10, 0x11, 0x12, 0x5b, 0x5c)):
                        raise RuntimeError('Physical key or modifier is already held')
                except Exception as error:
                    raise PressRejected(str(error)) from error
            send_key(key, down, extra_info=own_tag)
            owned_key = key if down else None

        try:
            if args.ready:
                ready={'ready':True}
                if args.live_bindings:ready['own_tag']=str(own_tag)
                print(json.dumps(ready), flush=True)
            released=serve(sys.stdin, sys.stdout, emit, check_held=check_held, check_pending=events.check)
            if args.campaign:
                print(json.dumps({'released':released}),flush=True)
        finally:
            events.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'error': str(error)}), flush=True)
        raise SystemExit(1)
