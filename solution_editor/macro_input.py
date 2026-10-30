"""工程宏的 Windows 连接：只绑定进程、战役、键位和焦点，不观察动作结果。"""
import ctypes
from ctypes import wintypes as w
from pathlib import Path
import sys
import time

from research.process import ProcessReader
from .campaign_runtime import read_campaign_binding
from .game_builds import select_build
from .input_client import InputWorkerClient
from .playback_guard import GameObservation
from .windows_observer import _kernel, _user, process_creation_id, read_keymap, sample_pressed_keys


def key_worker_prefix():
    if getattr(sys,'frozen',False):return [str(Path(sys.executable).with_name('SSEKeyWorker.exe'))]
    python=Path(sys.executable)
    if python.name.casefold()=='pythonw.exe':python=python.with_name('python.exe')
    from .paths import paths
    return [str(python),'-B','-u',str(paths().app/'release/entry.py'),'--key-worker']


def validate_target(binding, save_root, campaign):
    if Path(binding['save_root']).resolve()!=Path(save_root).resolve() or binding['campaign']!=campaign:
        raise ValueError('当前战役已离开工程副本，停止宏发送。')


def select_game_window(rows,pid):
    matches=[hwnd for hwnd,owner,visible,owned in rows if owner==pid and visible and not owned]
    if len(matches)!=1:raise ValueError('无法唯一绑定游戏主窗口，请保留一个游戏窗口。')
    return matches[0]


def find_game_window(pid):
    callback_type=ctypes.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
    _user.EnumWindows.argtypes=[callback_type,w.LPARAM]; _user.EnumWindows.restype=w.BOOL
    _user.IsWindowVisible.argtypes=[w.HWND]; _user.IsWindowVisible.restype=w.BOOL
    _user.GetWindow.argtypes=[w.HWND,w.UINT]; _user.GetWindow.restype=w.HWND
    rows=[]
    @callback_type
    def visit(hwnd,unused):
        owner=w.DWORD(); _user.GetWindowThreadProcessId(hwnd,ctypes.byref(owner))
        rows.append((hwnd,owner.value,bool(_user.IsWindowVisible(hwnd)),bool(_user.GetWindow(hwnd,4))))
        return True
    if not _user.EnumWindows(visit,0):raise ctypes.WinError(ctypes.get_last_error())
    return select_game_window(rows,pid)


class CampaignInputObserver:
    def __init__(self,pid,window,keymap_path,save_root,campaign,*,creation=None,live_bindings=False):
        self.reader=ProcessReader(pid)
        try:
            path=Path(self.reader.path)
            if path.name.casefold()!='sinking_star.exe':
                raise ValueError('Unsupported game executable')
            self.build=select_build(path.read_bytes())
            self.creation=process_creation_id(self.reader.handle)
            if creation is not None and creation!=self.creation:raise ValueError('Game process changed')
            self.pid,self.window,self.keymap_path=pid,window,Path(keymap_path)
            self.save_root,self.campaign=Path(save_root),campaign
            self.live_bindings=live_bindings
            self.mapping,self.digest=self._read_mapping()
            self.initial=self.observe()
        except BaseException:
            self.reader.close();raise

    def _read_mapping(self):
        if not self.live_bindings:return read_keymap(self.keymap_path)
        from .native_bindings import read_bindings
        snapshot=read_bindings(self.reader.read,[self.reader.image_base+rva for rva in self.build.keymap_pools])
        if snapshot.policy()['errors']:raise ValueError('; '.join(snapshot.policy()['errors']))
        return snapshot.game_keymap(),snapshot.digest

    def observe(self):
        code=w.DWORD()
        if not _kernel.GetExitCodeProcess(self.reader.handle,ctypes.byref(code)) or code.value!=259:
            raise RuntimeError('游戏进程已退出。')
        if process_creation_id(self.reader.handle)!=self.creation:raise RuntimeError('游戏进程已变化。')
        owner=w.DWORD()
        if not _user.GetWindowThreadProcessId(self.window,ctypes.byref(owner)) or owner.value!=self.pid:
            raise RuntimeError('游戏窗口已变化。')
        validate_target(read_campaign_binding(self.reader.read,self.reader.image_base,build=self.build),self.save_root,self.campaign)
        _,digest=self._read_mapping()
        return GameObservation((self.pid,self.window,self.creation),_user.GetForegroundWindow()==self.window,
            time.monotonic()*1000,1,digest,bool(_user.GetAsyncKeyState(27)&0x8000),
            pressed_keys=sample_pressed_keys(self.mapping))

    def close(self):self.reader.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()


class MacroConnection:
    def __init__(self,runtime,*,live_bindings=False):
        self.runtime=runtime;self.completion_job=None
        binding=runtime.binding()
        session=runtime.project(verify_initial=False).pending()
        if session is None or session['phase']!='active':raise ValueError('工程副本尚未载入。')
        validate_target(binding,session['save_root'],session['temporary_campaign'])
        window=find_game_window(runtime.pid)
        root=Path(binding['save_root']); keymap=root/'User.keymap'
        self.observer=CampaignInputObserver(runtime.pid,window,keymap,root,binding['campaign'],creation=runtime.creation,
                                           live_bindings=live_bindings)
        self.client=None
        try:
            command=key_worker_prefix()+[
                '--pid',str(runtime.pid),'--window',str(window),'--keymap',str(keymap),
                '--campaign',binding['campaign'],'--save-root',str(root),'--creation',str(runtime.creation),
                '--ready']
            if live_bindings:command.append('--live-bindings')
            self.client=InputWorkerClient(command,require_ready=True,require_release=True)
            self.own_tag=self.client.own_tag
            self.mapping,self.initial=self.observer.mapping,self.observer.initial
        except BaseException:
            self.observer.close();raise

    def observe(self):
        self.client.check()
        return self.observer.observe()

    def emit(self,key,down):
        self.client.emit(key,down)
        return time.monotonic()*1000 if down else None

    def close(self):
        self.client.close()
        if not self.client.released:raise RuntimeError('未确认按键工作进程已释放持键。')
        if self.completion_job is not None:
            self.completion_job.cancel()
            if not self.completion_job.done:raise RuntimeError('正在收尾 P 操作，请等待后重试停止。')
            self.completion_job=None
        self.observer.close()
        return True

    def special(self,symbol):
        from .release_profile import check_steps
        check_steps([{'symbol':symbol}])
        if symbol!='P':raise ValueError('Unsupported special action')
        if self.completion_job is None:
            from .completion_job import CompletionJob
            self.completion_job=CompletionJob(self.runtime)
        if not self.completion_job.poll():return False
        self.completion_job=None
        return True
