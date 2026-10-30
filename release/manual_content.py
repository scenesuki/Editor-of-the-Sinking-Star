"""发行 Markdown 文稿；程序包与源码包共用，避免维护 TXT/HTML 副本。"""
from pathlib import Path
import shutil

HASHES=[
'0ae10a513dae25286fe93d0db4fa8a2df9a473bc07e1734e12bc1ad30166db1c',
'd802098b7cb85eadfc733b88d1554042fad950c572e916febea3f669a474a549']


def render(destination, *, source=False):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    templates=Path(__file__).resolve().parent/'docs'
    docs=destination/'docs';docs.mkdir(exist_ok=True)
    for name in ('README.md','README.en.md'):
        text=(templates/name).read_text(encoding='utf-8')
        if source:
            english=name=='README.en.md'
            begin='## Quick start' if english else '## 快速开始'
            end='## Current limits' if english else '## 当前边界'
            guide=(templates/('BUILD.en.md' if english else 'BUILD.zh-CN.md')).read_text(encoding='utf-8')
            guide=guide.replace('(USAGE.en.md)','(docs/USAGE.en.md)').replace('(使用细则.md)','(docs/使用细则.md)')
            guide='\n'.join('#'+line if line.startswith('#') else line for line in guide.splitlines())+'\n'
            text=text[:text.index(begin)]+guide+'\n'+text[text.index(end):]
        (destination/name).write_text(text,encoding='utf-8')
    for name in ('使用细则.md','USAGE.en.md'):
        shutil.copyfile(templates/name,docs/name)
    if source:
        for name in ('BUILD.zh-CN.md','BUILD.en.md'):
            shutil.copyfile(templates/name,docs/name)
    artwork=Path(__file__).resolve().parents[1]/'assets/order-of-the-sinking-star-store.jpg'
    (docs/'assets').mkdir(exist_ok=True)
    shutil.copyfile(artwork,docs/'assets'/artwork.name)
