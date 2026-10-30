"""编辑器全局工具键；工程延迟仍保存在各自 script.json 中。"""
import json
import os
from pathlib import Path
import tempfile

from .native_bindings import tool_keys
from .release_profile import active_tools
from .key_settings import parse_toggle,toggle_label


class ToolPreferences:
    def __init__(self,path=None):
        self.path=Path(path) if path is not None else None
        self.keys=dict(solve='P',correct='E',wait='T');self.configured=False;self.error=''
        self.toggle_vk=0xc0
        if self.path is not None and self.path.exists():
            try:
                if self.path.stat().st_size>4096:raise ValueError('快捷键配置过大。')
                row=json.loads(self.path.read_text(encoding='utf-8'))
                if row.get('format')!='ootss-tool-keys' or row.get('version')!=1:raise ValueError('快捷键配置格式无效。')
                keys=tool_keys(row['keys'])
                active=active_tools(keys)
                if len(set(active.values()))!=len(active):raise ValueError('工具键不能重复。')
                self.toggle_vk=parse_toggle(row.get('toggle','Backquote'))
                self.keys=keys;self.configured=True
            except (ValueError,OSError,KeyError,AttributeError) as error:
                self.error='无法读取快捷键设置：'+str(error)

    def save(self,values,*,toggle=None):
        values=tool_keys(values)
        active=active_tools(values)
        if len(set(active.values()))!=len(active):raise ValueError('工具键不能重复。')
        toggle_vk=self.toggle_vk if toggle is None else parse_toggle(toggle)
        if self.path is not None:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temporary=None
            try:
                with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=self.path.parent,
                                                 prefix='.keys-',suffix='.tmp',delete=False) as stream:
                    temporary=Path(stream.name)
                    json.dump(dict(format='ootss-tool-keys',version=1,keys=values,toggle=toggle_label(toggle_vk)),stream,ensure_ascii=False,indent=2)
                    stream.flush();os.fsync(stream.fileno())
                os.replace(temporary,self.path);temporary=None
            finally:
                if temporary is not None:temporary.unlink(missing_ok=True)
        self.keys=values;self.toggle_vk=toggle_vk;self.configured=True;self.error=''
