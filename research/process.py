"""调查用只读进程连接，不提供写内存、输入或启动进程的接口。"""

import ctypes
from ctypes import wintypes as w
import os


kernel = ctypes.WinDLL('kernel32', use_last_error=True)
kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
kernel.OpenProcess.restype = w.HANDLE
kernel.CloseHandle.argtypes = [w.HANDLE]
kernel.CloseHandle.restype = w.BOOL
kernel.ReadProcessMemory.argtypes = [w.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                    ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
kernel.ReadProcessMemory.restype = w.BOOL
kernel.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
kernel.QueryFullProcessImageNameW.restype = w.BOOL
kernel.K32EnumProcessModulesEx.argtypes = [w.HANDLE, ctypes.POINTER(w.HMODULE), w.DWORD,
                                         ctypes.POINTER(w.DWORD), w.DWORD]
kernel.K32EnumProcessModulesEx.restype = w.BOOL
kernel.K32GetModuleFileNameExW.argtypes = [w.HANDLE, w.HMODULE, w.LPWSTR, w.DWORD]
kernel.K32GetModuleFileNameExW.restype = w.DWORD


class ProcessReader:
    def __init__(self, pid):
        self.handle = kernel.OpenProcess(0x0410, False, pid)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            path = ctypes.create_unicode_buffer(32768)
            length = w.DWORD(len(path))
            if not kernel.QueryFullProcessImageNameW(self.handle, 0, path, ctypes.byref(length)):
                raise ctypes.WinError(ctypes.get_last_error())
            self.path = path.value
            count = 256
            while True:
                modules = (w.HMODULE * count)()
                needed = w.DWORD()
                if not kernel.K32EnumProcessModulesEx(self.handle, modules, ctypes.sizeof(modules),
                                                      ctypes.byref(needed), 3):
                    raise ctypes.WinError(ctypes.get_last_error())
                if needed.value <= ctypes.sizeof(modules):
                    break
                count = needed.value // ctypes.sizeof(w.HMODULE)
            self.image_base = None
            for module in modules[:needed.value // ctypes.sizeof(w.HMODULE)]:
                if not kernel.K32GetModuleFileNameExW(self.handle, module, path, len(path)):
                    raise ctypes.WinError(ctypes.get_last_error())
                if os.path.normcase(path.value) == os.path.normcase(self.path):
                    self.image_base = module
                    break
            if self.image_base is None:
                raise OSError('Executable module was not found')
        except OSError:
            self.close()
            raise

    def read(self, address, size):
        if not self.handle:
            raise ValueError('Reader is closed')
        if size < 0:
            raise ValueError('Negative read size')
        buffer = ctypes.create_string_buffer(size)
        received = ctypes.c_size_t()
        if not kernel.ReadProcessMemory(self.handle, address, buffer, size, ctypes.byref(received)):
            raise ctypes.WinError(ctypes.get_last_error())
        if received.value != size:
            raise OSError('Incomplete memory read')
        return buffer.raw

    def close(self):
        if self.handle:
            kernel.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exception):
        self.close()
