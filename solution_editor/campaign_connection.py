"""发现游戏进程；以进程创建身份限制同一游戏的存档控制器。"""
import ctypes
from ctypes import wintypes as w


_kernel = ctypes.WinDLL('kernel32', use_last_error=True)
_kernel.CreateMutexW.argtypes = [ctypes.c_void_p, w.BOOL, w.LPCWSTR]
_kernel.CreateMutexW.restype = w.HANDLE
_kernel.CloseHandle.argtypes = [w.HANDLE]
_kernel.CloseHandle.restype = w.BOOL


class GameLease:
    def __init__(self, pid, creation):
        # 只利用命名对象的存在性，不使用可被同一线程递归获取的 mutex 所有权。
        self.handle = _kernel.CreateMutexW(None, False, f'Local\\ootss-editor-campaign-{pid}-{creation}')
        error = ctypes.get_last_error()
        if not self.handle: raise ctypes.WinError(error)
        if error == 183:
            self.close()
            raise RuntimeError('该游戏已有存档控制器，请先退出其他编辑器。')

    def close(self):
        if self.handle:
            _kernel.CloseHandle(self.handle)
            self.handle = None


def select_game(rows):
    matches = [pid for pid, name in rows if name.casefold() == 'sinking_star.exe']
    if len(matches) != 1:
        raise ValueError('请打开且只保留一个《沉星之序》游戏进程。')
    return matches[0]


def process_rows():
    class ProcessEntry(ctypes.Structure):
        _fields_ = [('size', w.DWORD), ('usage', w.DWORD), ('pid', w.DWORD),
                    ('heap', ctypes.c_size_t), ('module', w.DWORD), ('threads', w.DWORD),
                    ('parent', w.DWORD), ('priority', w.LONG), ('flags', w.DWORD),
                    ('exe', w.WCHAR * 260)]
    _kernel.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
    _kernel.CreateToolhelp32Snapshot.restype = w.HANDLE
    for name in ('Process32FirstW', 'Process32NextW'):
        function = getattr(_kernel, name)
        function.argtypes = [w.HANDLE, ctypes.POINTER(ProcessEntry)]
        function.restype = w.BOOL
    handle = _kernel.CreateToolhelp32Snapshot(2, 0)
    if handle == ctypes.c_void_p(-1).value: raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry = ProcessEntry(); entry.size = ctypes.sizeof(entry)
        if not _kernel.Process32FirstW(handle, ctypes.byref(entry)):
            raise ctypes.WinError(ctypes.get_last_error())
        rows = []
        while True:
            rows.append((entry.pid, entry.exe))
            if not _kernel.Process32NextW(handle, ctypes.byref(entry)):
                error = ctypes.get_last_error()
                if error != 18: raise ctypes.WinError(error)
                break
        return rows
    finally: _kernel.CloseHandle(handle)


def discover_game():return select_game(process_rows())
