"""面板切换键：单键可配置，与游戏及启用的工具键分开校验。"""
NAMES={'`':0xc0,'~':0xc0,'Backquote':0xc0,'Tab':9,'Home':36,'End':35,'Insert':45,'Delete':46,
       **{f'F{i}':0x6f+i for i in range(1,13)}}


def parse_toggle(value):
    value=str(value).strip()
    for name,vk in NAMES.items():
        if value.casefold()==name.casefold():return vk
    if len(value)==1 and value.isascii() and value.isalnum():return ord(value.upper())
    raise ValueError('切换键须为单个字母、数字、F1–F12、Tab、Home、End、Insert、Delete 或 Backquote。')


def toggle_label(vk):
    if 48<=vk<=57 or 65<=vk<=90:return chr(vk)
    return next((name for name,key in NAMES.items() if key==vk and name not in ('`','~')),'Backquote')


def actual_toggle_label(vk):
    import ctypes
    from ctypes import wintypes as w
    user=ctypes.WinDLL('user32');text=ctypes.create_unicode_buffer(80)
    user.GetKeyNameTextW.argtypes=[w.LONG,w.LPWSTR,ctypes.c_int]
    scan=user.MapVirtualKeyW(vk,0)
    flags=(scan<<16)|(0x1000000 if vk in (35,36,45,46) else 0)
    if scan and user.GetKeyNameTextW(flags,text,len(text)):return text.value
    return toggle_label(vk)


def validate_toggle(vk,snapshot,tools):
    from .native_bindings import virtual_key
    # Native Key_Code is not a Win32 VK for navigation and function keys.
    # Keep this conversion local: macro replay supports a narrower key set.
    extra={96:0xc0,126:0xc0,132:33,133:34,134:36,135:35,136:45,
           137:19,138:145,142:91,167:44}
    def conflict_vk(key):
        if 143<=key<=166:return key-31
        return extra.get(key,virtual_key(key))
    if any(conflict_vk(row['key'])==vk for _,row in snapshot.rows()) or any(ord(value)==vk for value in tools.values()):
        raise ValueError('鼠标切换键与游戏／工具绑定冲突，请先调整按键。')
