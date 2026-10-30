"""等待前缀计划与不可变原生战役快照；只接受本工程活动临时副本。"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import shutil
import uuid

from .campaign_project import _copy, _json, _lock, _publish, _tree
from .save_workspace import _plain
from .timeline import SolutionTimeline
from .game_builds import compatible_saved_build


@dataclass(frozen=True)
class DelayPlan:
    key: dict
    prefix: SolutionTimeline
    trial: SolutionTimeline
    index: int

    @property
    def digest(self):return self.key['prefix_sha256']


def delay_plan(timeline, wait_id):
    document=timeline.to_document();index=timeline.ids.index(wait_id)
    if timeline.steps[index].symbol!='_':raise ValueError('请选择一条额外等待。')
    if index==0 or index+1==len(timeline.steps):raise ValueError('延时前后都必须有动作 A 和 B。')
    if timeline.steps[index-1].symbol=='_' or timeline.steps[index+1].symbol=='_':
        raise ValueError('存在连续等待，请手动调整数值并删除多余等待。')
    rows=[{k:v for k,v in row.items() if k!='review'} for row in document['steps'][:index-1]]
    neighbors=[document['steps'][index-1],document['steps'][index+1]]
    payload=dict(version=2,wait_id=wait_id,prefix=rows,neighbors=neighbors,interval_ms=timeline.interval_ms)
    digest=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    prefix=SolutionTimeline(timeline.steps[:index-1]);trial=SolutionTimeline(timeline.steps[index-1:index+2])
    prefix.interval_ms=trial.interval_ms=timeline.interval_ms
    return DelayPlan(dict(wait_id=wait_id,prefix_sha256=digest),prefix,trial,index)


class Checkpoints:
    def __init__(self,project):self.project=project

    def path(self,key):
        if (not isinstance(key,dict) or set(key)!={'wait_id','prefix_sha256'}
            or not isinstance(key['wait_id'],str) or not re.fullmatch('[0-9a-f]{32}',key['wait_id'])
            or not isinstance(key['prefix_sha256'],str) or not re.fullmatch('[0-9a-f]{64}',key['prefix_sha256'])):
            raise ValueError('Invalid checkpoint identity')
        path=self.project.root/'checkpoints'/key['wait_id']/key['prefix_sha256']
        for parent in (path.parent.parent,path.parent,path):
            if parent.exists():_plain(parent)
        return path

    def resolve(self,key):
        path=self.path(key);row=_json(path/'checkpoint.json')
        if (row.get('format')!='ootss-delay-checkpoint' or row.get('version')!=1
            or row.get('project_id')!=self.project.row['id'] or row.get('key')!=key
            or not compatible_saved_build(row.get('game_sha256'),self.project.game_sha256)):
            raise ValueError('Checkpoint identity changed')
        source=path/'campaign';inventory=_tree(source)
        if inventory!=row.get('inventory') or '.ootss-editor-owner.json' in inventory['files']:
            raise ValueError('Checkpoint campaign changed')
        return source,inventory

    def exists(self,key):
        path=self.path(key)
        if not path.exists():return False
        self.resolve(key);return True

    def _storage_entry(self,key):
        path=self.path(key);_plain(path)
        root=self.project.root/'checkpoints';_plain(root)
        resolved=path.resolve(strict=True)
        if resolved.parent.parent!=root.resolve(strict=True):raise ValueError('Unsafe checkpoint path')
        if {p.name for p in path.iterdir()}!={'campaign','checkpoint.json'}:
            raise ValueError('检查点含额外材料，保留不清理。')
        _,inventory=self.resolve(key)
        row=_json(path/'checkpoint.json')
        signature=hashlib.sha256(json.dumps(row,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        size=sum(r['bytes'] for r in inventory['files'].values())+(path/'checkpoint.json').stat().st_size
        return dict(key=dict(key),signature=signature,bytes=size)

    def inventory(self,*,protected=()):
        keep={self.path(key).as_posix() for key in protected}
        result=dict(project_id=self.project.row['id'],count=0,bytes=0,protected_count=0,
                    skipped_count=0,candidates=[])
        root=self.project.root/'checkpoints'
        if not root.exists():return result
        _plain(root)
        for wait in sorted(root.iterdir()):
            try:
                _plain(wait)
                if not wait.is_dir() or not re.fullmatch('[0-9a-f]{32}',wait.name):raise ValueError('Unknown wait')
            except (ValueError,OSError):result['skipped_count']+=1;continue
            for path in sorted(wait.iterdir()):
                try:
                    entry=self._storage_entry(dict(wait_id=wait.name,prefix_sha256=path.name))
                except (ValueError,OSError):result['skipped_count']+=1;continue
                result['count']+=1;result['bytes']+=entry['bytes']
                if path.as_posix() in keep:result['protected_count']+=1
                else:result['candidates'].append(entry)
        return result

    def prune(self,plan,*,protected=()):
        if not isinstance(plan,dict) or plan.get('project_id')!=self.project.row['id']:
            raise ValueError('检查点清理计划不属于当前工程。')
        if not isinstance(plan.get('candidates'),list):raise ValueError('Invalid cleanup plan')
        keep={self.path(key).as_posix() for key in protected}
        with _lock(self.project.root):
            from .campaign_project import CampaignProject
            fresh=CampaignProject.open(self.project.root,game_sha256=self.project.game_sha256,verify_initial=False)
            if fresh.row['id']!=self.project.row['id']:raise ValueError('Project identity changed')
            targets=[];seen=set()
            # 先复核全部目标；任一变化都在删除前拒绝，客户端不能提供任意文件路径。
            for expected in plan['candidates']:
                key=expected.get('key') if isinstance(expected,dict) else None
                target=self.path(key)
                if target.as_posix() in keep:raise ValueError('当前调试起点须保留，请刷新容量。')
                if target.as_posix() in seen:raise ValueError('Duplicate cleanup entry')
                seen.add(target.as_posix())
                if self._storage_entry(key)!=expected:raise ValueError('检查点已变化，请刷新容量。')
                if not target.resolve().is_relative_to((self.project.root/'checkpoints').resolve()):
                    raise ValueError('Unsafe cleanup target')
                targets.append(target)
            for target in targets:shutil.rmtree(target)
            result=self.inventory(protected=protected)
            result.update(removed_count=len(targets),freed_bytes=sum(e['bytes'] for e in plan['candidates']))
            return result

    def capture(self,key,*,current_campaign):
        p=self.project;path=self.path(key)
        with _lock(p.root):
            session=p.pending()
            if session is None or session['phase']!='active' or current_campaign!=session['temporary_campaign']:
                raise ValueError('Checkpoint requires the active owned temporary campaign')
            source=Path(session['save_root'])/current_campaign
            expected=dict(project_id=p.row['id'],session_id=session['session_id'])
            if _json(source/'.ootss-editor-owner.json')!=expected:raise ValueError('Temporary ownership changed')
            if path.exists():self.resolve(key);return path
            inventory=_tree(source);inventory['files'].pop('.ootss-editor-owner.json',None)
            path.parent.mkdir(parents=True,exist_ok=True);self.path(key)
            stage=path.with_name('.preparing-'+uuid.uuid4().hex);stage.mkdir()
            _copy(source,stage/'campaign',inventory,exclude_owner=True)
            if _json(source/'.ootss-editor-owner.json')!=expected:raise ValueError('Temporary ownership changed during checkpoint copy')
            _publish(stage/'checkpoint.json',dict(format='ootss-delay-checkpoint',version=1,
                project_id=p.row['id'],game_sha256=p.game_sha256,key=key,inventory=inventory))
            stage.rename(path)  # 仅发布完整快照；失败留下准备材料，不替换已有快照。
            return path
