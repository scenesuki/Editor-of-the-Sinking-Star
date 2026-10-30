"""naive 录制时间轴：稳定条目标识、独立等待及复核状态。"""
import re
import uuid

from .native_bindings import tool_keys
from .timeline import SolutionTimeline,Step
from .script_limits import MAX_RECORDING_STEPS


class RecordingTimeline(SolutionTimeline):
    def __init__(self,steps=None,*,playhead=0):
        super().__init__(steps,playhead=playhead)
        self.ids=[uuid.uuid4().hex for _ in self.steps]
        self.reviews={id:True for id,step in zip(self.ids,self.steps) if step.symbol=='_'}
        self.interval_ms=250;self.extra_wait_ms=1000
        self.tool_keys=dict(solve='P',correct='E',wait='T')

    @classmethod
    def from_timeline(cls,timeline):
        if isinstance(timeline,cls):return timeline
        result=cls(timeline.steps,playhead=timeline.playhead)
        result.caret,result.anchor=timeline.caret,timeline.anchor
        result.dirty=True
        return result

    def invalidate_from(self,index):
        for id in self.ids[index:]:
            if id in self.reviews:self.reviews[id]=True

    def replace_selection(self,replacement):
        first,last=sorted((self.caret,self.anchor))
        if not super().replace_selection(replacement):return False
        removed=self.ids[first:last]
        for id in removed:self.reviews.pop(id,None)
        added=[uuid.uuid4().hex for _ in replacement]
        self.ids[first:last]=added
        self.reviews.update({id:True for id,step in zip(added,replacement) if step.symbol=='_'})
        self.invalidate_from(first)
        return True

    def record(self,step):
        at=self.playhead;super().record(step)
        id=uuid.uuid4().hex;self.ids.insert(at,id)
        if step.symbol=='_':self.reviews[id]=True
        self.invalidate_from(at)

    def delete_step(self,id):
        index=self.ids.index(id)
        self.ids.pop(index);self.steps.pop(index);self.reviews.pop(id,None)
        if self.playhead>index:self.playhead-=1
        self.move_caret(min(self.caret,len(self.steps)))
        self.invalidate_from(index);self.dirty=True

    def insert_after(self,after_id,step):
        index=self.ids.index(after_id)+1 if after_id is not None else len(self.steps)
        if not isinstance(step,Step):raise ValueError('Invalid inserted step')
        if len(self.steps)>=MAX_RECORDING_STEPS:raise ValueError('操作数量达到上限。')
        id=uuid.uuid4().hex
        self.steps.insert(index,step);self.ids.insert(index,id)
        if step.symbol=='_':self.reviews[id]=True
        self.playhead=0;self.move_caret(index+1)
        self.invalidate_from(index);self.dirty=True
        return id

    def move_step(self,id,before_index):
        source=self.ids.index(id)
        if type(before_index) is not int or not 0<=before_index<=len(self.steps):
            raise ValueError('Invalid drop position')
        target=before_index-(source<before_index)
        if target==source:return False
        step=self.steps.pop(source);self.ids.pop(source)
        self.steps.insert(target,step);self.ids.insert(target,id)
        self.playhead=0;self.move_caret(target+1)
        self.invalidate_from(min(source,target));self.dirty=True
        return True

    def set_wait(self,id,value):
        index=self.ids.index(id)
        if self.steps[index].symbol!='_':raise ValueError('所选条目不是等待。')
        self.steps[index]=Step('_',value)
        self.invalidate_from(index);self.dirty=True

    def set_action(self,id,symbol):
        index=self.ids.index(id)
        if self.steps[index].symbol=='_' or symbol=='_':raise ValueError('只能将普通动作修改为其他动作。')
        replacement=Step(symbol)
        if replacement==self.steps[index]:return
        self.steps[index]=replacement
        self.invalidate_from(index);self.dirty=True

    def mark_review(self,id,pending):
        if id not in self.reviews or type(pending) is not bool:raise ValueError('Invalid delay review')
        self.reviews[id]=pending;self.dirty=True

    def to_document(self):
        if len(self.ids)!=len(self.steps) or len(self.steps)>MAX_RECORDING_STEPS:raise ValueError('Invalid recording length')
        if any(not isinstance(id,str) or not re.fullmatch('[0-9a-f]{32}',id) for id in self.ids) or len(set(self.ids))!=len(self.ids):
            raise ValueError('Invalid recording identifiers')
        for value in (self.interval_ms,self.extra_wait_ms):
            if type(value) is not int or not 0<value<=2147483647:raise ValueError('间隔须为正整数毫秒。')
        if set(self.reviews)!={id for id,step in zip(self.ids,self.steps) if step.symbol=='_'}:
            raise ValueError('Delay metadata does not match steps')
        rows=[]
        for id,step in zip(self.ids,self.steps):
            row=dict(id=id,symbol=step.symbol)
            if step.symbol=='_':
                row.update(wait_ms=step.wait_ms,review=self.reviews[id])
                if type(row['review']) is not bool:raise ValueError('Invalid delay review')
            rows.append(row)
        return dict(format='ootss-step-script',version=2,steps=rows,interval_ms=self.interval_ms,
                    extra_wait_ms=self.extra_wait_ms,tool_keys=tool_keys(self.tool_keys))

    @classmethod
    def from_document(cls,row):
        if not isinstance(row,dict) or set(row)!={'format','version','steps','interval_ms','extra_wait_ms','tool_keys'}:
            raise ValueError('Invalid recording document')
        if row['format']!='ootss-step-script' or row['version']!=2 or not isinstance(row['steps'],list):
            raise ValueError('Unsupported recording document')
        if len(row['steps'])>MAX_RECORDING_STEPS:raise ValueError('Invalid recording length')
        steps=[];ids=[];reviews={}
        for item in row['steps']:
            if not isinstance(item,dict) or set(item) not in ({'id','symbol'},{'id','symbol','wait_ms','review'}):
                raise ValueError('Invalid recording entry')
            step=Step(item['symbol'],item.get('wait_ms'));id=item['id']
            if not isinstance(id,str) or not re.fullmatch('[0-9a-f]{32}',id):raise ValueError('Invalid recording identifier')
            if step.symbol=='_':
                if 'review' not in item:raise ValueError('Missing delay review')
                reviews[id]=item['review']
            elif 'review' in item:raise ValueError('Unexpected delay review')
            steps.append(step);ids.append(id)
        result=cls(steps);result.ids=ids;result.reviews=reviews
        result.interval_ms=row['interval_ms'];result.extra_wait_ms=row['extra_wait_ms'];result.tool_keys=tool_keys(row['tool_keys'])
        result.to_document()  # 同一验证用于载入和保存，非法元数据不降级丢弃。
        return result
