"""发行能力开关，不删除已保存的旧动作。"""
from .paths import paths
import sys

VERSION='0.1.0-preview'


def preview():return bool(getattr(sys,'frozen',False) or (paths().resources/'release_profile.json').exists())


def check_steps(steps,*,preview=None):
    if preview is None:preview=globals()['preview']()
    if preview and any((step.get('symbol') if isinstance(step,dict) else step.symbol)=='P' for step in steps):
        raise ValueError('预览版已停用 P；请删除或替换 P 步骤后再播放。')


def active_tools(values):return {k:v for k,v in values.items() if k!='solve' or not preview()}
