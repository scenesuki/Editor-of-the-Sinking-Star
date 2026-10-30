"""在已核对主线程帧入口执行正常保存／载入命令；不控制逻辑帧或恢复内存。"""
import frida


AGENT=r'''
let hook=null, pending=null, state='idle', result=null, retained=[];
rpc.exports={
 install(c) {
  for(const k of ['frame','load','save','menu']) {
   const expected=c[k+'_code'];
   const actual=Array.from(new Uint8Array(ptr(c[k]).readByteArray(expected.length/2)))
                     .map(x=>x.toString(16).padStart(2,'0')).join('');
   if(actual!==expected)throw Error('Code fingerprint mismatch: '+k);
  }
  const context=ptr(c.context);
  const save=new NativeFunction(ptr(c.save),'void',['pointer']);
  const menu=new NativeFunction(ptr(c.menu),'void',['pointer']);
  const load=new NativeFunction(ptr(c.load),'void',['pointer','pointer','uchar','pointer']);
  hook=Interceptor.attach(ptr(c.frame),{onEnter(){
   if(state!=='waiting')return;
   const command=pending;pending=null;
   if(Date.now()>command.deadline){state='expired';return;}
   state='executing';
   try {
    if(command.action==='save'){save(context);result={action:'save',thread:Process.getCurrentThreadId()};}
    else if(command.action==='menu'){menu(context);result={action:'menu',thread:Process.getCurrentThreadId()};}
    else {
     // 游戏可能借用名称指针；整个控制器会话内保留，同名读档复用稳定地址。
     let storage=retained.find(row=>row.campaign===command.campaign);
     if(!storage){
      const data=Memory.allocUtf8String(command.campaign), box=Memory.alloc(16), output=Memory.alloc(8);
      box.writeU64(unescape(encodeURIComponent(command.campaign)).length);box.add(8).writePointer(data);
      storage={campaign:command.campaign,data,box,output};retained.push(storage);
     }
     const {box,output}=storage;output.writeU64(0);
     load(context,box,1,output);
     result={action:'load',success:output.readU8()!==0,thread:Process.getCurrentThreadId()};
    }
    state='complete';
   } catch(error){result={error:String(error)};state='error';}
  }});
  Interceptor.flush();
 },
 request(action,campaign){
  if(state==='waiting'||state==='executing')throw Error('Native command already pending');
  if(!['save','load','menu'].includes(action))throw Error('Unsupported native command');
  pending={action,campaign,deadline:Date.now()+5000};result=null;state='waiting';
 },
 status(){if(state==='waiting'&&Date.now()>pending.deadline){pending=null;state='expired';}
          return {state,result,retained_count:retained.length};},
 borrowed(slot){const data=ptr(slot).add(8).readPointer();return retained.some(row=>row.data.equals(data));},
 close(){if(state==='executing')throw Error('Native command in progress');pending=null;
         if(hook!==null){hook.detach();hook=null;Interceptor.flush();}state='closed';}
};
'''


class CampaignFrameCommands:
    def __init__(self,pid,config):
        self.session=frida.attach(pid)
        try:
            self.script=self.session.create_script(AGENT)
            self.script.load();self.script.exports_sync.install(config)
        except BaseException:
            self.session.detach();self.session=None;raise

    def request(self,action,campaign=None):
        if action not in ('save','load','menu'):raise ValueError('Unsupported native command')
        if action=='load':
            if (not isinstance(campaign,str) or not 1<=len(campaign)<=128 or campaign in ('.','..')
                or campaign[-1] in ' .' or any(c in '<>:"/\\|?*' or ord(c)<32 for c in campaign)):
                raise ValueError('Invalid campaign name')
        self.script.exports_sync.request(action,campaign)

    def status(self):return self.script.exports_sync.status()

    def close(self):
        if self.session is None:return
        if not self.session.is_detached:self.script.exports_sync.close()
        self.session.detach();self.session=None
