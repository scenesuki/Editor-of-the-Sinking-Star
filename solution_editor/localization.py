"""中文消息 ID 与英文显示分离；动作、状态和控件 ID 不参与翻译。"""
import ctypes
import json
from pathlib import Path
import re
from functools import lru_cache
from .paths import paths

_language=None
_catalog=None
_zh_catalog=None


def language():
    global _language
    if _language is None:
        try:
            preferred=json.loads((paths().config/'language.json').read_text(encoding='utf-8'))['language']
            if preferred not in ('zh-CN','en'):raise ValueError()
        except (OSError,ValueError,KeyError,TypeError):
            preferred='zh-CN' if ctypes.windll.kernel32.GetUserDefaultUILanguage()&0x3ff==4 else 'en'
        _language=preferred
    return _language


def set_language(value):
    global _language
    if value not in ('zh-CN','en'):raise ValueError('Unsupported language')
    from .campaign_project import _publish
    paths().config.mkdir(parents=True,exist_ok=True)
    _publish(paths().config/'language.json',dict(language=value))
    _language=value


def tr(text,locale=None):
    text=str(text)
    if (locale or language())!='en':
        global _zh_catalog
        if _zh_catalog is None:_zh_catalog=json.loads((paths().resources/'locales/zh-CN.json').read_text(encoding='utf-8'))
        return _zh_catalog.get(text,text)
    return _english(text)


@lru_cache(maxsize=4096)
def _english(text):
    global _catalog
    if _catalog is None:_catalog=json.loads((paths().resources/'locales/en.json').read_text(encoding='utf-8'))
    if text in _catalog:return _catalog[text]
    result=text
    for source,target in sorted(_catalog.items(),key=lambda pair:len(pair[0]),reverse=True):
        if source in result:result=result.replace(source,target)
    # 非预期底层诊断的原文进入日志；界面不把未经翻译的整段当作英文。
    if re.search('[\u3400-\u9fff]',result):return 'Operation unavailable. Open the log for details.'
    return result


def localize_model(model,locale):
    items=[]
    for original in model['items']:
        item=dict(original);ident=item.get('id','');role=item.get('role')
        if item['kind']!='field' and not ident.startswith('select:'):
            if role=='toggle_hint':
                item['text']=item.get('text','').replace(' 切换鼠标 · 录制请短按',' toggles mouse · use short taps') if locale=='en' else item.get('text','')
            elif role=='project' and item.get('text')!='未打开工程':
                item['text']=item.get('text','').replace(' · 未保存',' · Unsaved') if locale=='en' else item.get('text','')
            else:item['text']=tr(item.get('text',''),locale)
        items.append(item)
    return dict(model,items=items,locale=locale)
