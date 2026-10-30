"""Mod式一次性战役载入参数桥；复用游戏自身的菜单调用和线程，不直接调用未知ABI。"""
import re
import frida


AGENT=r'''
let hook=null, request=null, state='idle', last=null, retained=[];
function readString(p) {
  const n=p.readU64().toNumber();
  if(n<1 || n>512) throw Error('Invalid campaign string');
  return p.add(8).readPointer().readUtf8String(n);
}
function makeString(s) {
  const data=Memory.allocUtf8String(s), box=Memory.alloc(16);
  box.writeU64(unescape(encodeURIComponent(s)).length);box.add(8).writePointer(data);
  retained.push({box,data});return box;
}
rpc.exports={
 install(address,expected) {
  if(hook!==null)throw Error('Already installed');
  const p=ptr(address), bytes=Array.from(new Uint8Array(p.readByteArray(expected.length/2)));
  if(bytes.map(x=>x.toString(16).padStart(2,'0')).join('')!==expected)throw Error('Code fingerprint mismatch');
  hook=Interceptor.attach(p,{
   onEnter(args) {
    this.used=false;
    if(state!=='armed')return;
    if(Date.now()>request.deadline){state='expired';return;}
    const wanted=request;request=null;
    let original;
    try {original=readString(args[1]);}
    catch(error){state='error';last={error:String(error)};return;}
    const matched=original===wanted.source;
    // 非预期菜单选择也只重载明确的当前战役，避免误载入别的用户战役。
    const destination=matched?wanted.target:wanted.source;
    args[1]=makeString(destination);this.used=true;this.matched=matched;
    state='loading';last={source:original,target:destination,matched,thread:Process.getCurrentThreadId()};
   },
   onLeave() {if(this.used)state=this.matched?'intercepted':'mismatch';}
  });
  Interceptor.flush();
 },
 arm(source,target,lifetime) {
  if(state==='loading' || state==='armed')throw Error('Load already pending');
  if(retained.length>=16)throw Error('Reconnect bridge after returning to original campaign');
  request={source,target,deadline:Date.now()+lifetime};state='armed';last=null;
 },
 status(){if(state==='armed' && Date.now()>request.deadline){request=null;state='expired';}
          return {state,last,retained:retained.length};},
 borrowed(slot){const data=ptr(slot).add(8).readPointer();return retained.some(row=>row.data.equals(data));},
 close(){if(state==='loading')throw Error('Native load still active');request=null;
         if(hook!==null){hook.detach();hook=null;Interceptor.flush();}state='closed';}
};
'''


class CampaignLoadBridge:
    def __init__(self,pid,address,expected_code):
        if not re.fullmatch('[0-9a-f]{32,128}',expected_code) or len(expected_code)%2:
            raise ValueError('Invalid code fingerprint')
        self.session=frida.attach(pid)
        try:
            self.script=self.session.create_script(AGENT)
            self.script.load()
            self.script.exports_sync.install(str(address),expected_code)
        except BaseException:
            self.session.detach();self.session=None
            raise

    def arm(self,source,target,*,lifetime_ms=30000):
        for name in (source,target):
            if (not isinstance(name,str) or not 1<=len(name)<=128 or name in ('.','..')
                or name[-1] in ' .' or any(c in '<>:"/\\|?*' or ord(c)<32 for c in name)):
                raise ValueError('Invalid campaign name')
        if not 100<=lifetime_ms<=60000:raise ValueError('Invalid request lifetime')
        self.script.exports_sync.arm(source,target,lifetime_ms)

    def status(self):return self.script.exports_sync.status()

    def close(self):
        if self.session is None:return
        if not self.session.is_detached:self.script.exports_sync.close()
        self.session.detach();self.session=None
