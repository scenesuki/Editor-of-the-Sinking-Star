"""统一面板、控件圆角与语义层级；不改变操作标识和禁用条件。"""

def decorate(model):
    scale=model.get('scale',1);items=[]
    for original in model['items']:
        i=dict(original);kind=i['kind'];id=i.get('id','');label=i.get('text','');role=i.get('role')
        i['font']='body'
        if kind=='rect' and i.get('color')=='background':
            i.update(radius=12*scale,outline='border')
        elif kind=='button':
            i['radius']=8*scale
            primary=id in ('new','record','trial_wait','recover','replace_step','insert_step') or (id=='prepare_delay' and not any(x.get('id')=='trial_wait' and x.get('enabled') for x in model['items']))
            i['tone']='primary' if primary else 'danger' if id in ('stop','end_record','delete_step','stop_delay','prune_checkpoints') else 'quiet' if id in ('toggle','toggle_timeline','close_delay','close_action','close_checkpoints','close_settings','close','previous','next','steps_previous','steps_next','toggle_settings','refresh') else 'normal'
            if id.startswith(('step:','select:')):
                i['tone']='row';i['font']='row';i['textColor']='gold' if '等待' in label else 'text'
            else:i['font']='button'
            if id in ('close','toggle_settings'):i['outline']='border'
        elif kind=='field':i['radius']=8*scale
        elif kind=='text':
            i['textColor']='text' if role in ('title','project') else 'muted'
            if role=='title':i['font']='title'
            elif role=='hint':i['font']='small'
            elif role=='status' and any(t in label for t in ('失败','错误','无法','冲突')):i['textColor']='dangerText'
            elif role=='status' and label=='起点已就绪':i['textColor']='accent'
        items.append(i)
    return dict(model,items=items,theme='deep-sea-2')
