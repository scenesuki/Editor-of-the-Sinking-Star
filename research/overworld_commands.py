"""游戏主线程执行所在格快速完成；仅由已确认归属的工程临时副本调用。"""
from pathlib import Path
import time


AGENT=r'''
let hook=null,state='idle',result=null,command=null,config=null;
const hex=p=>Array.from(new Uint8Array(p)).map(x=>x.toString(16).padStart(2,'0')).join('');
rpc.exports={
 install(c){
  config=c;
  for(const name of ['frame','progress','entry','tower','world']){
   // 同一 CampaignRuntime 已安装的存档帧钩子会改写入口；它在安装时已核对原码。
   if(name==='frame'&&c.frame_owned===true)continue;
   if(hex(ptr(c[name]).readByteArray(c[name+'_code'].length/2))!==c[name+'_code'])
    throw Error('Completion code fingerprint mismatch: '+name);
  }
  const context=ptr(c.context);
  const progress=new NativeFunction(ptr(c.progress),'void',['pointer','pointer','pointer']);
  const entry=new NativeFunction(ptr(c.entry),'void',['pointer','pointer']);
  const tower=new NativeFunction(ptr(c.tower),'void',['pointer','pointer','uchar']);
  const world=new NativeFunction(ptr(c.world),'void',['pointer','pointer']);
  const user=Process.getModuleByName('user32.dll');
  const foreground=new NativeFunction(user.getExportByName('GetForegroundWindow'),'pointer',[]);
  const key=new NativeFunction(user.getExportByName('GetAsyncKeyState'),'int16',['int']);
  hook=Interceptor.attach(ptr(c.frame),{onEnter(){
   if(state!=='waiting')return;
   const q=command;command=null;state='executing';
   let output;
   result=completeOverworld({
    validate(){
     if(Date.now()>q.deadline)throw Error('完成请求已过期，没有执行。');
     if(!foreground().equals(ptr(q.window))||(key(27)&0x8000))throw Error('游戏失焦或紧急停止，没有执行。');
     for(const sample of q.guards){
      if(hex(ptr(sample.address).readByteArray(sample.bytes.length/2))!==sample.bytes)
       throw Error('角色、入口或工程已变化，没有执行。');
     }
    },
    progress(){output=Memory.alloc(Process.pointerSize);output.writePointer(ptr(0));
     progress(context,ptr(q.entry).add(0x330),output);const p=output.readPointer();
     if(p.isNull())throw Error('无法取得关卡进度记录。');return p;},
    readFlags(p){return p.readU8();},writeFlags(p,v){p.writeU8(v);},
    refreshEntry(){entry(context,ptr(q.entry));},
    recount(){tower(context,ptr(q.manager),0);},
    refreshWorld(){world(context,ptr(q.manager));}
   });
   state='complete';
  }});Interceptor.flush();
 },
 request(q){if(state==='waiting'||state==='executing')throw Error('Completion already pending');
  command={...q,deadline:Date.now()+1000};state='waiting';result=null;},
 status(){if(state==='waiting'&&Date.now()>command.deadline){command=null;result={ok:false,changed:false,error:'完成请求超时，没有执行。'};state='complete';}
  return {state,result};},
 cancel(){if(state==='waiting'){command=null;result={ok:false,changed:false,error:'完成请求已取消，没有执行。'};state='complete';}},
 close(){if(state==='executing')throw Error('Completion still executing');command=null;
  if(hook){hook.detach();hook=null;Interceptor.flush();}state='closed';}
};
'''


def execute_completion(pid,config,command,*,cancel=None):
    import frida
    session=frida.attach(pid)
    script=None
    try:
        source=Path(__file__).with_name('overworld_complete.js').read_text(encoding='utf8')
        script=session.create_script(source+'\n'+AGENT);script.load();script.exports_sync.install(config)
        if cancel is not None and cancel.is_set():raise RuntimeError('快速完成已取消。')
        script.exports_sync.request(command)
        deadline=time.monotonic()+2
        while time.monotonic()<deadline:
            if cancel is not None and cancel.is_set():script.exports_sync.cancel()
            status=script.exports_sync.status()
            if status['state']=='complete':return status['result']
            time.sleep(.01)
        raise TimeoutError('完成请求未返回，现场状态未知；不要自动重试。')
    finally:
        try:
            if script is not None and not session.is_detached:script.exports_sync.close()
        finally:session.detach()
