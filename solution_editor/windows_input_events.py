"""独立消息线程观察键盘事件；不拦截按键、不注入游戏进程。"""
import ctypes
from ctypes import wintypes as w
import threading
import time

from .input_events import ExternalInputLatch


class KeyboardEvent(ctypes.Structure):
    _fields_ = [('vkCode', w.DWORD), ('scanCode', w.DWORD), ('flags', w.DWORD),
                ('time', w.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


_user = ctypes.WinDLL('user32', use_last_error=True)
_kernel = ctypes.WinDLL('kernel32', use_last_error=True)
_Callback = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t)
_user.SetWindowsHookExW.argtypes = [ctypes.c_int, _Callback, w.HINSTANCE, w.DWORD]
_user.SetWindowsHookExW.restype = w.HANDLE
_user.CallNextHookEx.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t]
_user.CallNextHookEx.restype = ctypes.c_ssize_t
_user.UnhookWindowsHookEx.argtypes = [w.HANDLE]
_user.UnhookWindowsHookEx.restype = w.BOOL
_user.GetForegroundWindow.restype = w.HWND
_user.PeekMessageW.argtypes = [ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT, w.UINT]
_user.PeekMessageW.restype = w.BOOL
_user.TranslateMessage.argtypes = [ctypes.POINTER(w.MSG)]
_user.DispatchMessageW.argtypes = [ctypes.POINTER(w.MSG)]
_user.DispatchMessageW.restype = ctypes.c_ssize_t
_kernel.GetModuleHandleW.argtypes = [w.LPCWSTR]
_kernel.GetModuleHandleW.restype = w.HMODULE


class WindowsInputEvents:
    def __init__(self, window, own_tag):
        # 只在目标游戏前台观察操作相关键；不保留键名、文本或事件序列。
        watched = set(range(0x30, 0x5b)) | set(range(0xa0, 0xa6))
        watched.update((8, 9, 13, 16, 17, 18, 27, 32, 37, 38, 39, 40, 46, 0x5b, 0x5c))
        self.latch = ExternalInputLatch(watched, own_tag)
        self.window = window
        self.error = None
        self._ready = threading.Event()
        self._stop = threading.Event()
        self._heartbeat = time.monotonic()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        if not self._ready.wait(2):
            self.close()
            raise RuntimeError('Input event observer startup timed out')
        if self.error:
            self.close()
            raise RuntimeError(self.error)

    def _run(self):
        handle = None
        @_Callback
        def callback(code, message, pointer):
            try:
                if code == 0 and message in (0x100, 0x104):
                    event = ctypes.cast(pointer, ctypes.POINTER(KeyboardEvent)).contents
                    self.latch.feed(event.vkCode, True, event.flags, event.dwExtraInfo,
                                    _user.GetForegroundWindow() == self.window)
            except BaseException:
                self.error = 'Input event callback failed'
            return _user.CallNextHookEx(None, code, message, pointer)
        try:
            handle = _user.SetWindowsHookExW(13, callback, _kernel.GetModuleHandleW(None), 0)
            if not handle:
                raise ctypes.WinError(ctypes.get_last_error())
            self._heartbeat = time.monotonic()
            self._ready.set()
            message = w.MSG()
            while not self._stop.is_set():
                while _user.PeekMessageW(ctypes.byref(message), None, 0, 0, 1):
                    if message.message == 0x12:
                        raise RuntimeError('Input observer message loop ended')
                    _user.TranslateMessage(ctypes.byref(message))
                    _user.DispatchMessageW(ctypes.byref(message))
                now = time.monotonic()
                if now - self._heartbeat >= .5:
                    raise RuntimeError('Input event observer message loop stalled')
                self._heartbeat = now
                self._stop.wait(.005)
        except BaseException as error:
            self.error = str(error)
        finally:
            if handle and not _user.UnhookWindowsHookEx(handle):
                self.error = 'Input observer unhook failed'
            self._ready.set()

    def check(self):
        if self.error or not self._thread.is_alive() or time.monotonic() - self._heartbeat >= .5:
            raise RuntimeError(self.error or 'Input event observer stopped or stalled')
        self.latch.check()

    def close(self):
        self._stop.set()
        self._thread.join(timeout=2)
        if self._thread.is_alive():
            raise RuntimeError('Input event observer did not stop')
        if self.error:
            raise RuntimeError(self.error)
