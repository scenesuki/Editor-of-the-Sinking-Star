"""编辑器与备份工具的本机互斥；不关闭用户进程。"""
import ctypes
from ctypes import wintypes as w
from .identity import environment_id

_kernel=ctypes.WinDLL('kernel32',use_last_error=True)
_kernel.CreateMutexW.argtypes=[ctypes.c_void_p,w.BOOL,w.LPCWSTR];_kernel.CreateMutexW.restype=w.HANDLE
_kernel.OpenMutexW.argtypes=[w.DWORD,w.BOOL,w.LPCWSTR];_kernel.OpenMutexW.restype=w.HANDLE
_kernel.CloseHandle.argtypes=[w.HANDLE]


def _name():return 'Local\\SinkingStarEditor-'+environment_id()


class EditorLease:
    def __init__(self):
        self.handle=_kernel.CreateMutexW(None,False,_name())
        if not self.handle:raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error()==183:
            self.close();raise RuntimeError('该游戏已有存档控制器，请先退出其他编辑器。')
    def close(self):
        if self.handle:_kernel.CloseHandle(self.handle);self.handle=None
    def __enter__(self):return self
    def __exit__(self,*args):self.close()


def editor_running():
    handle=_kernel.OpenMutexW(0x100000,False,_name())
    if handle:_kernel.CloseHandle(handle);return True
    if ctypes.get_last_error()!=2:raise ctypes.WinError(ctypes.get_last_error())
    return False
