"""游戏内面板的串行工程任务；原生保存期间界面继续绘制。"""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import uuid

from .campaign_editor_session import CampaignEditorSession


class PanelProjects:
    def __init__(self, projects_root, *, session=None):
        self.projects_root = Path(projects_root).absolute()
        self.session = session if session is not None else CampaignEditorSession()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='ingame-project')
        self.task = None
        self.ready_to_close = False
        self.error = None
        self.status = '选择工程，或为当前存档创建新工程。'
        self.projects = []
        self.result = None
        self.completion=0;self.last_action=None;self.last_success=False
        self.refresh()

    @property
    def busy(self): return self.task is not None

    def refresh(self):
        rows = []
        for manifest in sorted(self.projects_root.glob('*/project.json')):
            try:
                if manifest.stat().st_size > 1024*1024: continue
                row = json.loads(manifest.read_text(encoding='utf-8'))
                if row.get('format') != 'ootss-campaign-project': continue
                rows.append(dict(name=str(row.get('name', manifest.parent.name)), root=str(manifest.parent)))
            except (OSError, ValueError, TypeError, AttributeError): continue
        self.projects = rows

    def request(self, action, *, name='', path='', key=None, plan=None, protected=()):
        if self.busy:
            self.status = '正在处理工程，请等待；窗口和游戏继续运行。'
            return
        self.error = None
        self.result = None
        self.ready_to_close = False
        def operation():
            if action in ('new', 'open'):
                if self.session.runtime is not None:
                    raise ValueError('请先退出当前工程或恢复原存档，再切换工程。')
                if action == 'new':
                    title = name.strip()
                    if not title or len(title) > 64: raise ValueError('工程名称须为 1～64 个字符。')
                    slug = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', title).strip(' .')[:40] or '工程'
                    target = self.projects_root/(slug+'-'+uuid.uuid4().hex[:10])
                    self.session.create(target, title)
                else:
                    if not path.strip(): raise ValueError('请选择工程，或填写工程目录／project.json 路径。')
                    target = Path(path.strip().strip('"'))
                    if not target.is_absolute(): target = self.projects_root/target
                    if target.name.casefold() == 'project.json': target = target.parent
                    self.session.open(target)
            elif action == 'save': self.session.save()
            elif action in ('leave', 'close'):
                if self.session.state == 'recovery':
                    raise ValueError('会话需要恢复，请先点击“恢复原存档”；窗口及恢复材料已保留。')
                if self.session.runtime is not None:
                    if self.session.timeline.dirty: self.session.save()
                    self.session.leave()
            elif action == 'recover': self.session.recover()
            elif action == 'reset': self.session.reset_start()
            elif action in ('checkpoint_capture','checkpoint_restore'):self.session.checkpoint(action,key)
            elif action in ('checkpoint_scan','checkpoint_prune'):
                from .campaign_project import CampaignProject
                from .delay_checkpoints import Checkpoints
                project=CampaignProject.open(self.session.root,game_sha256=self.session.game_sha256,verify_initial=False)
                store=Checkpoints(project)
                return (store.inventory(protected=protected) if action=='checkpoint_scan'
                        else store.prune(plan,protected=protected))
            else: raise ValueError('未知工程操作。')
        self.action = action
        self.status = dict(new='正在原生保存、复制工程起点并载入副本……',
            open='正在读取工程并载入起点副本……', save='正在保存工程脚本……',
            leave='正在返回原存档并清理临时副本……',
            close='正在安全退出，完成后卸载面板……', recover='正在恢复原存档……',
            reset='正在重新载入工程固定起点……',checkpoint_capture='正在保存等待前检查点……',
            checkpoint_restore='正在载入检查点的新副本……',checkpoint_scan='正在核对检查点容量……',
            checkpoint_prune='正在清理历史检查点……').get(action, '处理中……')
        self.task = self.executor.submit(operation)

    def poll(self):
        if self.task is None or not self.task.done(): return False
        task, self.task = self.task, None
        self.completion+=1;self.last_action=self.action;self.last_success=False
        try: self.result=task.result()
        except Exception as error:
            self.error = str(error)
            self.status = '操作失败：'+self.error
        else:
            self.last_success=True
            if self.action == 'close': self.ready_to_close = True
            self.status = ('发现未结束会话，请恢复原存档。' if self.session.state == 'recovery' else
                '检查点容量已更新。' if self.action in ('checkpoint_scan','checkpoint_prune') else
                '已载入工程副本。' if self.action in ('new','open','reset') else
                '延时检查点已准备。' if self.action in ('checkpoint_capture','checkpoint_restore') else
                '脚本已保存，固定起点不变。' if self.action == 'save' else
                '已返回原存档，所属临时副本已清理。')
            if self.action in ('open','recover') and self.session.notice:
                self.status += ' '+self.session.notice
        self.refresh()
        return True

    def shutdown(self):
        # 非正常退出只断开，不假装原生返回或删除仍在使用的副本。
        self.executor.shutdown(wait=True)
        self.session.disconnect()
