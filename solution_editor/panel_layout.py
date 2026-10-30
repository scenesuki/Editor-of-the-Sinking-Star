"""游戏内双栏布局：按当前任务组织控制，绘制模型不操作游戏。"""
import math


def concise_status(value):
    return {
        '选择旧工程，或为当前存档新建工程。':'选择或新建工程',
        '选择工程，或为当前存档创建新工程。':'选择或新建工程',
        '已载入工程副本。':'编辑中',
        '脚本已保存，固定起点不变。':'已保存',
        '已返回原存档，所属临时副本已清理。':'已返回原存档',
        '延时检查点已准备。':'起点已就绪',
        '录制／播放已停止。':'已停止',
        '试调已结束；可改数值后重复试调，或确认当前等待。':'试调结束',
        'A 执行前检查点已准备。':'起点已就绪',
    }.get(value,value)


def split_model(p,width,height):
    scale=min(max(1,min(width/1920,height/1080)),(width-48)/(1140 if p.delay_open or p.action_open or p.checkpoint_open else 780),(height-40)/(1200 if p.settings_open else 1000))
    y=20;left=12;right=width-12-320*scale
    items=[];regions=[];lists=[];delay_x=None;delay_offset=0
    def box(x,w,h):
        regions.append([x,y,w*scale,h*scale])
        items.append(dict(kind='rect',x=x,y=y,w=w*scale,h=h*scale,color='background',text=''))
    def item(x,kind,yy,text,xx=16,ww=388,hh=32,**extra):
        if x==delay_x and yy>=196:yy+=delay_offset
        items.append(dict(kind=kind,x=x+xx*scale,y=y+yy*scale,w=ww*scale,h=hh*scale,text=text,color=extra.pop('color','text'),**extra))
    def text(x,yy,s,**kw):item(x,'text',yy,s,**kw)
    def button(x,yy,s,id,ww=388,enabled=True,hh=40,**kw):item(x,'button',yy,s,ww=ww,hh=hh,id=id,enabled=enabled,**kw)
    mode=p.record_state['mode'];recording=mode=='recording';playing=mode in ('playing','preparing','completing')
    available=not p.busy;active=p.project_state=='active';recovery=p.project_state=='recovery'
    editable=active and available and not recording and not playing
    permitted=editable and not p.policy_errors
    from .panel_actions import action_labels,CHARACTERS
    labels=action_labels(p.action_keys,p.active_solve_key)
    if p.preview:labels['P']='P · 已停用'
    selected=next((r for r in p.steps if r['id']==p.selected),None)
    wait=selected is not None and selected['symbol']=='_'
    if p.follow_current and p.steps and (recording or mode=='playing'):
        target=len(p.steps)-1 if recording else min(p.playhead,len(p.steps)-1)
        if target<p.timeline_offset:p.timeline_offset=target
        elif target>=p.timeline_offset+12:p.timeline_offset=target-11
    p.timeline_offset=max(0,min(p.timeline_offset,max(0,len(p.steps)-12)))
    if p.folded:
        box(left,160,60);button(left,10,'展开控制','toggle',ww=128)
    else:
        message=concise_status(p.status)
        status_h=max(32,min(224,24*sum(max(1,math.ceil(len(line)/35)) for line in message.split('\n'))))
        action_y=88+status_h+16
        settings_y=action_y+(104 if not recovery else 152)
        footer_y=settings_y+(500+(64 if p.settings_status else 0) if p.settings_open and not recovery else 64)
        box(left,420,footer_y+160)
        text(left,12,'沉星编辑器',ww=240,role='title')
        button(left,8,'收起','toggle',xx=324,ww=80)
        text(left,52,p.project_label.replace(' *',' · 未保存'),role='project')
        text(left,88,message,hh=status_h,role='status')
        if recovery:
            button(left,action_y,'恢复原存档','recover',enabled=available)
            button(left,action_y+48,'保存修改','save',enabled=available)
            text(left,action_y+98,'恢复后可退出或继续打开工程。',role='hint')
        else:
            button(left,action_y,'进入编辑状态','record',ww=188,enabled=permitted)
            button(left,action_y,'从头播放','play',xx=216,ww=188,enabled=permitted)
            button(left,action_y+48,'保存','save',ww=188,enabled=editable)
            button(left,action_y+48,'退出工程','leave',xx=216,ww=188,enabled=active and available)
            button(left,settings_y,'收起设置' if p.settings_open else '设置','toggle_settings')
            if p.settings_open:
                def field(yy,id,xx=236,ww=168):item(left,'field',yy,getattr(p,id),xx=xx,ww=ww,hh=36,id=id,limit=p.limits[id],revision=p.revisions[id],enabled=editable)
                text(left,settings_y+48,'本工程 · 延迟',role='hint')
                for yy,label,id in [(settings_y+84,'普通间隔 ms','interval'),(settings_y+128,'默认额外等待 ms','extra')]:
                    text(left,yy,label,ww=200);field(yy,id)
                button(left,settings_y+180,'应用延迟','apply_options',enabled=editable)
                text(left,settings_y+236,'全局 · 工具键',role='hint')
                keys=[('仅撤销记录','correct_key'),('插入等待','wait_key')] if p.preview else [('快速完成','solve_key'),('仅撤销记录','correct_key'),('插入等待','wait_key')]
                spacing=200 if p.preview else 136;kw=188 if p.preview else 116
                for n,(label,id) in enumerate(keys):
                    text(left,settings_y+272,label,xx=16+n*spacing,ww=kw)
                    field(settings_y+312,id,16+n*spacing,kw)
                text(left,settings_y+360,'鼠标切换键',ww=200);field(settings_y+360,'toggle_key')
                button(left,settings_y+412,'保存快捷键','apply_keys',enabled=editable)
                if p.settings_status:text(left,settings_y+460,p.settings_status,hh=64,role='status')
        text(left,footer_y,p.toggle_hint+' 切换鼠标 · 录制请短按',role='toggle_hint')
        button(left,footer_y+48,'退出并卸载','close',enabled=available and not recovery)
        button(left,footer_y+104,'中文 / English','language',ww=188)
        button(left,footer_y+104,'打开数据目录','open_data',xx=216,ww=188)
    visible=min(12,max(1,len(p.steps)));list_top=192;list_bottom=list_top+visible*42
    activity=recording or playing or p.busy
    timeline_h=112 if p.timeline_folded else list_bottom+72+(56 if activity else 0)
    box(right,320,timeline_h)
    text(right,12,'时间轴',ww=180,role='title')
    button(right,8,'展开' if p.timeline_folded else '收起','toggle_timeline',xx=224,ww=80)
    status={'recording':'录制中','playing':'播放中','preparing':'准备中','completing':'处理中'}.get(mode,'编辑中')
    speed=p.speed_state
    speed_label=('暂停' if speed['value']==0 else f"{speed['value']:g}×") if speed['value'] is not None else ''
    text(right,56,f'{status}'+(f' · {speed_label}' if active and speed_label else '')+f' · {len(p.steps)} / 65536 步',ww=288,role='status')
    if not p.timeline_folded:
        if active:
            for n,(value,label) in enumerate(((0,'暂停'),(.25,'0.25×'),(1,'1×'),(4,'4×'))):
                button(right,92,label,f'speed:{value:g}',xx=16+n*74,ww=66,hh=36,
                       enabled=available and not playing and speed['available'],selected=speed['value']==value)
        if not p.follow_current and activity:
            button(right,140,'回到当前步骤','follow_current',ww=288,hh=32)
        elif p.record_state.get('pending'):text(right,140,'下一步添加等待',ww=288,role='hint')
        elif editable:
            button(right,140,'撤销编辑','edit_undo',ww=138,hh=32,enabled=p.can_undo)
            button(right,140,'重做编辑','edit_redo',xx=166,ww=138,hh=32,enabled=p.can_redo)
        view=dict(id='timeline',bounds=[right+16*scale,y+list_top*scale,268*scale,visible*42*scale],
            bar=[right+292*scale,y+list_top*scale,12*scale,visible*42*scale],count=len(p.steps),visible=12,
            offset=p.timeline_offset,rowHeight=42*scale,version=p.timeline_revision,editable=editable,rows=[])
        lists.append(view)
        for offset,row in enumerate(p.steps[p.timeline_offset:p.timeline_offset+12]):
            idx=p.timeline_offset+offset;symbol=row['symbol']
            title=(f"等待 {row['wait_ms']} ms · "+('待调' if row['review'] else '已调') if symbol=='_' else labels.get(symbol,'人物 '+symbol))
            highlight=(idx==min(p.playhead,len(p.steps)-1) if mode=='playing' else idx==len(p.steps)-1 if recording else p.selected==row['id'])
            yy=list_top+offset*42
            item(right,'drag_handle',yy,'',xx=16,ww=20,hh=40,id='grip:'+row['id'],enabled=editable)
            view['rows'].append(dict(id=row['id'],index=idx,handle=[right+16*scale,y+yy*scale,20*scale,40*scale]))
            button(right,yy,f'{idx+1:02d}  {title}','step:'+row['id'],xx=40,ww=240,enabled=editable or (p.delay_open and mode in ('idle','preparing','playing')),selected=highlight)
        if not p.steps:text(right,list_top+4,'尚无步骤',ww=268,role='hint')
        button(right,list_bottom+16,'＋添加','new_step',ww=138,enabled=editable)
        button(right,list_bottom+16,'检查点','open_checkpoints',xx=166,ww=138,enabled=editable)
        if recording:button(right,list_bottom+64,'结束录制','end_record',ww=288,enabled=available)
        elif activity:button(right,list_bottom+64,'停止播放' if playing else '停止','stop',ww=288,enabled=True)
    elif activity:button(right,64,'停止','stop',xx=224,ww=80)
    if p.checkpoint_open:
        cx=right-12-360*scale;info=p.checkpoint_state
        box(cx,360,440)
        text(cx,12,'检查点',ww=230,role='title');button(cx,8,'关闭','close_checkpoints',xx=264,ww=80)
        mib=lambda size:f'{size/1048576:.2f} MiB'
        text(cx,64,f"已核验 {info.get('count',0)} 项 · {mib(info.get('bytes',0))}",ww=328)
        text(cx,108,f"可清理 {info.get('removable_count',0)} 项 · {mib(info.get('removable_bytes',0))}",ww=328)
        text(cx,152,f"当前起点保留 {info.get('protected_count',0)} 项；未识别材料保留 {info.get('skipped_count',0)} 项",ww=328,hh=64,role='hint')
        text(cx,220,info.get('message') or '点击查看容量。',ww=328,hh=64,role='status')
        button(cx,296,'刷新容量','refresh_checkpoints',ww=328,enabled=editable)
        button(cx,348,f"确认清理 {info.get('removable_count',0)} 项历史检查点",'prune_checkpoints',ww=328,
               enabled=editable and info.get('ready') and info.get('removable_count',0)>0)
        text(cx,400,'固定起点与游戏存档保持原位。',ww=328,role='hint')
    elif p.delay_open:
        dx=right-12-360*scale
        info=p.delay_state
        status=(p.status if p.busy else info.get('message') or '试调中') if p.busy or playing else info.get('error') or info.get('message') or ('起点已就绪' if info.get('ready') else '请先准备起点')
        status=concise_status(status)
        status_h=max(32,min(120,24*sum(max(1,math.ceil(len(line)/28)) for line in status.split('\n'))))
        delay_x=dx;delay_offset=status_h-76
        box(dx,360,652+delay_offset+(52 if activity else 0))
        text(dx,12,'延时',ww=230,role='title')
        button(dx,8,'关闭','close_delay',xx=264,ww=80)
        before=labels.get(info.get('before'),info.get('before','—'));after=labels.get(info.get('after'),info.get('after','—'))
        text(dx,64,f'{before} → 等待 → {after}',ww=328)
        text(dx,108,status,ww=328,hh=status_h,role='status')
        button(dx,196,'重新准备起点' if info.get('ready') else '准备起点','prepare_delay',ww=328,enabled=permitted and not info.get('error'))
        text(dx,252,'额外等待 ms',ww=328)
        item(dx,'field',292,p.wait_value,id='wait_value',limit=10,revision=p.revisions['wait_value'],enabled=editable and wait,ww=328,hh=40)
        try:formula=f'{p.active_interval} + {int(p.wait_value)} = {p.active_interval+int(p.wait_value)} ms'
        except ValueError:formula='请输入有效毫秒数'
        text(dx,344,formula,ww=328,role='hint')
        ready=bool(info.get('ready')) and permitted and wait
        button(dx,392,'开始试调','trial_wait',ww=328,enabled=ready)
        button(dx,440,'返回起点','return_delay',ww=328,enabled=ready)
        button(dx,504,'应用','set_wait',ww=156,enabled=editable and wait)
        button(dx,504,'应用并标记已调','confirm_wait',xx=188,ww=156,enabled=editable and wait)
        text(dx,556,'返回起点不播放',ww=328,role='hint')
        button(dx,600,'删除等待','delete_step',ww=328,enabled=editable and wait)
        if activity:button(dx,652,'停止调试','stop_delay',ww=328,enabled=True)
    elif p.action_open and (selected is not None or p.inserting):
        ax=right-12-360*scale
        box(ax,360,536)
        text(ax,12,'添加操作' if p.inserting else '操作',ww=230,role='title');button(ax,8,'关闭','close_action',xx=264,ww=80)
        index=next((i for i,row in enumerate(p.steps) if row['id']==p.selected),None)
        caption=(f'插在第 {index+1} 步之后' if index is not None else '追加到末尾') if p.inserting else f"第 {index+1} 步 · {labels.get(selected['symbol'],'人物 '+selected['symbol'])}"
        text(ax,64,caption,ww=328)
        choices=[(symbol,labels[symbol]) for symbol in ('UDLRXV' if p.preview else 'UDLRXVP')]
        for i,(symbol,label) in enumerate(choices):
            button(ax,112+(i//4)*48,label,'choose_action:'+symbol,xx=16+(i%4)*84,ww=76,
                   enabled=editable,selected=p.action_symbol==symbol)
        for i,number in enumerate(CHARACTERS):
            button(ax,220+(i//3)*48,labels[number],'choose_action:'+number,xx=16+(i%3)*112,ww=104,
                   enabled=editable,selected=p.action_symbol==number)
        if p.inserting:
            button(ax,376,f'额外等待 · {p.active_extra_wait} ms','choose_action:_',ww=328,enabled=editable,selected=p.action_symbol=='_')
            button(ax,432,'插入','insert_step',ww=328,enabled=editable)
        else:
            button(ax,376,'应用修改','replace_step',ww=328,enabled=editable and p.action_symbol!=selected['symbol'])
            button(ax,432,'删除步骤','delete_step',ww=328,enabled=editable)
        text(ax,488,'只改脚本；已有等待值保留。',ww=328,role='hint')
    x=min(r[0] for r in regions);r=max(r[0]+r[2] for r in regions);b=max(r[1]+r[3] for r in regions)
    return dict(bounds=[x,y,r-x,b-y],regions=regions,items=items,lists=lists,scale=scale)


def startup_model(p,width,height):
    scale=min(max(1,min(width/1920,height/1080)),(width-48)/780,(height-40)/840)
    left=12;right=width-12-320*scale;y=20;items=[];regions=[];lists=[]
    def add(kind,xx,yy,w,h,text='',**extra):
        items.append(dict(kind=kind,x=left+xx*scale,y=y+yy*scale,w=w*scale,h=h*scale,text=text,color=extra.pop('color','text'),**extra))
    def button(yy,text,id,xx=16,ww=388,enabled=True):add('button',xx,yy,ww,40,text,id=id,enabled=enabled)
    def text(yy,label,**extra):add('text',16,yy,388,32,label,**extra)
    available=not p.busy
    if p.folded:
        regions.append([left,y,160*scale,60*scale]);add('rect',0,0,160,60,color='background')
        button(10,'展开工程','toggle',ww=128)
    else:
        regions.append([left,y,420*scale,816*scale]);add('rect',0,0,420,816,color='background')
        text(12,'沉星编辑器',role='title');button(8,'收起','toggle',xx=324,ww=80)
        text(60,concise_status(p.status),role='status')
        text(112,'工程名称')
        add('field',16,152,388,40,p.name,id='name',limit=64,revision=p.revisions['name'],enabled=available)
        button(204,'新建并录制','new',enabled=available)
        text(272,'已有工程')
        p.project_offset=max(0,min(p.project_offset,max(0,len(p.projects)-3)))
        lists.append(dict(id='projects',bounds=[left+16*scale,y+312*scale,368*scale,144*scale],
            bar=[left+392*scale,y+312*scale,12*scale,144*scale],count=len(p.projects),visible=3,
            offset=p.project_offset,rowHeight=48*scale,version=len(p.projects),editable=False,rows=[]))
        for offset,row in enumerate(p.projects[p.project_offset:p.project_offset+3]):
            index=p.project_offset+offset;button(312+offset*48,row['name'][:20],f'select:{index}',ww=368,enabled=available)
            items[-1]['selected']=p.open_path==row['root']
        if not p.projects:text(320,'暂无工程',role='hint')
        add('text',16,468,200,32,f'{len(p.projects)} 个工程',role='hint')
        button(464,'刷新','refresh',xx=316,ww=88,enabled=available)
        text(520,'工程路径')
        add('field',16,560,388,40,p.open_path,id='open_path',limit=512,revision=p.revisions['open_path'],enabled=available)
        button(612,'打开工程','open',enabled=available and bool(p.open_path.strip()))
        button(664,'收起快捷键设置' if p.settings_open else '快捷键设置','toggle_settings',enabled=available)
        text(716,p.toggle_hint+' 切换鼠标 · 录制请短按',role='toggle_hint')
        button(764,'退出并卸载','close',enabled=available)
    rh=560 if p.settings_open else 64 if p.timeline_folded else 260
    regions.append([right,y,320*scale,rh*scale])
    def rt(kind,xx,yy,w,h,label='',**extra):
        items.append(dict(kind=kind,x=right+xx*scale,y=y+yy*scale,w=w*scale,h=h*scale,text=label,color=extra.pop('color','text'),**extra))
    rt('rect',0,0,320,rh,color='background')
    if p.settings_open:
        rt('text',16,12,180,32,'工具键',role='title')
        rt('button',224,8,80,40,'关闭',id='close_settings',enabled=True)
        rt('text',16,64,288,32,'全局设置',role='hint')
        keys=[('仅撤销记录','correct_key'),('插入等待','wait_key')] if p.preview else [('快速完成','solve_key'),('仅撤销记录','correct_key'),('插入等待','wait_key')]
        for n,(label,id) in enumerate(keys):
            yy=112+n*52
            rt('text',16,yy,180,32,label)
            rt('field',208,yy,96,40,getattr(p,id),id=id,limit=1,revision=p.revisions[id],enabled=available)
        rt('text',16,280,150,32,'鼠标切换键')
        rt('field',168,280,136,40,p.toggle_key,id='toggle_key',limit=16,revision=p.revisions['toggle_key'],enabled=available)
        rt('button',16,336,288,40,'保存快捷键',id='apply_keys',enabled=available)
        rt('button',16,392,288,40,'中文 / English',id='language',enabled=True)
        rt('button',16,440,288,40,'打开数据目录',id='open_data',enabled=True)
        if p.settings_status:rt('text',16,488,288,64,p.settings_status,role='status')
    else:
        rt('text',16,12,180,32,'时间轴',role='title')
        rt('button',224,8,80,40,'展开' if p.timeline_folded else '收起',id='toggle_timeline',enabled=True)
        if not p.timeline_folded:
            rt('text',16,96,288,40,'打开工程后显示步骤',role='hint')
            rt('button',16,152,288,40,'中文 / English',id='language',enabled=True)
            rt('button',16,204,288,40,'打开数据目录',id='open_data',enabled=True)
    return dict(bounds=[left,y,width-24,max(r[3] for r in regions)],regions=regions,items=items,lists=lists,scale=scale)
