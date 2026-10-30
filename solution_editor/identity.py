"""仅本地保存的设备／Windows 用户摘要；不联网、不猜测旧会话归属。"""
import ctypes
from ctypes import wintypes as w
from functools import lru_cache
import hashlib
import winreg


@lru_cache(maxsize=1)
def environment_id():
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'SOFTWARE\Microsoft\Cryptography',0,winreg.KEY_READ|winreg.KEY_WOW64_64KEY) as key:
            machine=winreg.QueryValueEx(key,'MachineGuid')[0]
        adv=ctypes.WinDLL('advapi32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.GetCurrentProcess.restype=w.HANDLE
        adv.OpenProcessToken.argtypes=[w.HANDLE,w.DWORD,ctypes.POINTER(w.HANDLE)]
        adv.GetTokenInformation.argtypes=[w.HANDLE,w.DWORD,ctypes.c_void_p,w.DWORD,ctypes.POINTER(w.DWORD)]
        adv.ConvertSidToStringSidW.argtypes=[ctypes.c_void_p,ctypes.POINTER(w.LPWSTR)]
        kernel.CloseHandle.argtypes=[w.HANDLE];kernel.LocalFree.argtypes=[ctypes.c_void_p]
        token=w.HANDLE();length=w.DWORD()
        if not adv.OpenProcessToken(kernel.GetCurrentProcess(),8,ctypes.byref(token)):raise ctypes.WinError(ctypes.get_last_error())
        try:
            adv.GetTokenInformation(token,1,None,0,ctypes.byref(length))
            data=ctypes.create_string_buffer(length.value)
            if not adv.GetTokenInformation(token,1,data,length,ctypes.byref(length)):raise ctypes.WinError(ctypes.get_last_error())
            sid=ctypes.c_void_p.from_buffer(data).value;text=w.LPWSTR()
            if not adv.ConvertSidToStringSidW(sid,ctypes.byref(text)):raise ctypes.WinError(ctypes.get_last_error())
            try:user=text.value
            finally:kernel.LocalFree(ctypes.cast(text,ctypes.c_void_p))
        finally:kernel.CloseHandle(token)
        return hashlib.sha256((machine.lower()+'\0'+user).encode('utf-8')).hexdigest()
    except Exception as error:raise ValueError('无法核验本机／Windows 用户环境，保留会话材料。') from error
