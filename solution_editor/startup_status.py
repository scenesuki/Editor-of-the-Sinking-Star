"""启动器与隐藏面板的单次就绪／失败反馈，不操作游戏。"""
import json
import os
from pathlib import Path
import tempfile


def friendly_error(error):
    if isinstance(error,ModuleNotFoundError) and ('frida' in str(error) or error.name=='frida'):
        return '运行依赖缺失，请重新安装编辑器依赖。'
    if isinstance(error,PermissionError) or getattr(error,'winerror',None)==5:
        return '无法连接游戏，请确认游戏与编辑器的运行权限一致。'
    if 'Unsupported game executable' in str(error):
        return '当前游戏版本与编辑器不匹配，请使用受支持的游戏版本。'
    return str(error) or type(error).__name__


def report(path,stage,message=''):
    if path is None:return
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,temporary=tempfile.mkstemp(prefix=path.name+'-',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            json.dump(dict(stage=stage,message=message,pid=os.getpid()),stream,ensure_ascii=False)
            stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:Path(temporary).unlink(missing_ok=True)
