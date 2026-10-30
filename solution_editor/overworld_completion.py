"""工程副本内的大世界快速完成命令；固定起点和返回战役不参与写入。"""
from pathlib import Path
from .campaign_project import _json
from .save_workspace import _plain


def require_owned_temporary(runtime,binding):
    p=runtime.project(verify_initial=False);session=p.pending()
    if (session is None or session['phase']!='active'
            or binding['campaign']!=session['temporary_campaign']
            or Path(binding['save_root']).resolve()!=Path(session['save_root']).resolve()):
        raise ValueError('快速完成仅允许在当前工程的临时副本内执行。')
    target=Path(session['save_root'])/session['temporary_campaign'];_plain(target)
    if _json(target/'.ootss-editor-owner.json')!={'project_id':session['project_id'],'session_id':session['session_id']}:
        raise ValueError('临时副本归属不一致，拒绝执行快速完成。')
    return session


def complete_current_tile(runtime,*,cancel=None):
    from research.overworld_target import read_overworld_target
    from research.overworld_commands import execute_completion
    from .campaign_runtime import read_campaign_binding
    from .macro_input import find_game_window
    from .windows_observer import _user
    binding=runtime.binding();session=require_owned_temporary(runtime,binding)
    if cancel is not None and cancel.is_set():raise RuntimeError('快速完成已取消。')
    window=find_game_window(runtime.pid)
    if _user.GetForegroundWindow()!=window or _user.GetAsyncKeyState(27)&0x8000:
        raise ValueError('请保持游戏前台，释放紧急停止键。')
    samples={}
    def read(address,size):
        data=runtime.reader.read(address,size)
        if (address,size) in samples and samples[address,size]!=data:
            raise ValueError('游戏状态发生变化，请重新按 P。')
        samples[address,size]=data
        return data
    base=runtime.reader.image_base
    target=read_overworld_target(read,base,build=runtime.build)
    captured=read_campaign_binding(read,base,build=runtime.build)
    if captured!=binding:raise ValueError('当前战役已变化。')
    # 所有本次取址依据在游戏帧入口逐字节复核，避免把旧实体指针排队执行。
    frames=getattr(runtime,'frames',None)
    config=runtime.build.code_config(runtime.image,base,('frame','progress','entry','tower','world'))
    config['frame_owned']=frames is not None and not frames.session.is_detached
    require_owned_temporary(runtime,runtime.binding())
    result=execute_completion(runtime.pid,config,dict(window=hex(window),entry=hex(target.entry),
        manager=hex(target.manager),guards=[dict(address=hex(a),bytes=b.hex()) for (a,n),b in samples.items()]),cancel=cancel)
    if not result['ok']:
        raise RuntimeError(result['error']+('；现场可能已改变，请从工程起点重放。' if result['changed'] else ''))
    # 结果描述的是命令完成；不通过实体效果判断路线是否正确。
    if runtime.binding()!=binding:raise RuntimeError('完成期间战役变化，停止后续保存。')
    require_owned_temporary(runtime,binding)
    saved=runtime.save_current()
    return dict(**result,level_name=target.level_name,entity_id=target.entity_id,save=saved)
