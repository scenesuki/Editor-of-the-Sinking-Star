"""独立恢复事件使旧会话失效；未知归属材料始终保留。"""
import json
from pathlib import Path
from .paths import paths


def check_session(row):
    directory=paths().config/'restore-events'
    for p in directory.glob('*.json'):
        if p.stat().st_size>1024*1024:raise ValueError('恢复事件记录异常，保留会话。')
        event=json.loads(p.read_text(encoding='utf-8'))
        if (event.get('state') in ('preparing','applied','complete') and event.get('environment')==row.get('environment')
            and str(Path(event.get('save_root','')).resolve()).casefold()==str(Path(row['save_root']).resolve()).casefold()
            and row['session_id'] in event.get('sessions',[])):
            raise ValueError('存档已由独立备份工具恢复；旧会话禁止自动返回或清理，请完成恢复工具的收尾。')
