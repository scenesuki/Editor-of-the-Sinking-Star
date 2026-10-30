'use strict';
// 游戏窗口内的绘制与控件消息；工程动作经消息交给 Python 串行后端。
const N=ptr(0), refs=[], hooks=[], targets=[];
const methods=new Map();
let hwnd=N, queue=N, swap=N, dev11=N, ctx11=N, on12=N, factory=N, write=N, format=N;
let closed=false, drawing=false, error=null, width=0, height=0, frames=0;
let scene={bounds:[0,0,0,0],items:[],scale:1}, focus=null, hover=false, captured=null;
let translating=false, chars=0, highSurrogate='', fontScale=1;
const fields=new Map(), textFormats=new Map(), cursorRows=arrowRows();
let recorder=null,recordGuards=[],recordPaused=false;
const ownInputTags=new Set(),ownRawTags=new Set();
let seedingKeys=false;
const panelAccess=new PanelAccess();let panelKey=0xc0,fontLocale='zh-CN',activeFontLocale='';
const listUI=new PanelLists(event=>send({kind:'ui',...event}));
let updateAccess=()=>{},releaseAccess=()=>{},cursorPoint=()=>null;
let releaseListCapture=()=>{};
let listCapturePending=()=>false;
let closing=false;
const foregroundWindow=api('user32.dll','GetForegroundWindow','pointer',[]);
const asyncKey=api('user32.dll','GetAsyncKeyState','int16',['int']);
function prepareRecordGuards(policy){
 recordGuards=policy.guards.map(row=>({address:ptr(row.address),expected:Uint8Array.from(row.bytes.match(/../g)||[],x=>parseInt(x,16)),stride:row.stride}));
}
function recordBindingsValid(){
 try{
  for(const g of recordGuards){const actual=new Uint8Array(g.address.readByteArray(g.expected.length));
   for(let i=0;i<actual.length;i++)if(!(g.stride&&i%g.stride===5)&&actual[i]!==g.expected[i])return false;}
  return true;
 }catch(_){return false;}
}
let createWrapped,acquire,releaseWrapped,flush;
const ids={
 device:'189819f1-1db6-4b57-be54-1821339b85f7',
 resource:'696442be-a72e-4059-bc79-5b5c98040fad',
 factory:'7b7166ec-21c7-44ae-b21a-c9ae321ae369',
 swap3:'94d99bdb-f1f8-4ab0-b236-7da0170edab1',
 on12:'85611e73-70a9-490e-9614-a9e302777904',
 texture:'6f15aaf2-d208-4e89-9ab4-489535d34f9c',
 surface:'cafcb56c-6ac3-4889-bf47-9e23bbd260ec',
 d2d:'06152247-6f50-465a-9245-118bfd3b6007',
 write:'b859ee5a-d838-4b5b-a2e8-1adc7d93db48'
};
function guid(s){const p=Memory.alloc(16),h=s.split('-');let bytes=[];
 for(let i=0;i<h.length;i++){let a=h[i].match(/../g).map(v=>parseInt(v,16));if(i<3)a.reverse();bytes.push(...a);}
 p.writeByteArray(bytes);return p;}
function out(){const p=Memory.alloc(8);p.writePointer(N);return p;}
function check(hr,label){if(hr<0)throw Error(label+': 0x'+(hr>>>0).toString(16));}
function method(obj,index,result,args){
 const address=obj.readPointer().add(index*8).readPointer(),key=address+':'+result+':'+args.join(',');
 if(!methods.has(key))methods.set(key,new NativeFunction(address,result,['pointer',...args]));
 return methods.get(key);
}
function call(obj,index,result,args,values){return method(obj,index,result,args)(obj,...values);}
function api(module,name,result,args){return new NativeFunction(Module.load(module).getExportByName(name),result,args);}
function own(p){if(!p.isNull())refs.push(p);return p;}
function drop(p){if(p&&!p.isNull())call(p,2,'uint',[],[]);}
function qi(p,id){const o=out();check(call(p,0,'int',['pointer','pointer'],[guid(id),o]),'QueryInterface');return o.readPointer();}
function rect(x,y,w,h){const p=Memory.alloc(16);[x,y,x+w,y+h].forEach((v,i)=>p.add(i*4).writeFloat(v));return p;}
function rounded(x,y,w,h,r){const p=Memory.alloc(24);[x,y,x+w,y+h,r,r].forEach((v,i)=>p.add(i*4).writeFloat(v));return p;}
const palette={background:[16/255,27/255,40/255,1],button:[.13,.19,.25,1],field:[.04,.075,.115,1],
 text:[237/255,242/255,247/255,1],muted:[178/255,192/255,208/255,1],disabled:[.075,.11,.15,1],
 selection:[.075,.22,.25,1],accent:[134/255,213/255,195/255,1],
 cursorEdge:[.02,.025,.03,1],cursorFill:[1,1,1,1],border:[49/255,66/255,84/255,1],gold:[.96,.79,.47,1],primary:[134/255,213/255,195/255,1],
 onPrimary:[.025,.09,.105,1],danger:[.25,.12,.15,1],dangerText:[1,.74,.73,1],
 quiet:[.065,.105,.15,1],row:[.075,.13,.185,1],hover:[.17,.25,.31,1],pressed:[.20,.30,.35,1]};
function brush(rt,name){const p=Memory.alloc(16);palette[name].forEach((v,i)=>p.add(i*4).writeFloat(v));
 const o=out();check(call(rt,8,'int',['pointer','pointer','pointer'],[p,N,o]),'CreateSolidColorBrush');return o.readPointer();}
function releaseTargets(){
 for(const t of targets){if(!t)continue;for(const b of Object.values(t.brushes))drop(b);drop(t.rt);drop(t.surface);drop(t.wrapped);}
 targets.length=0;
 if(!ctx11.isNull())flush(ctx11);
}
function shutdown(){
 if(closed)return;if(drawing)throw Error('Render callback in progress');
 closing=true;releaseAccess();
 if(listCapturePending())throw Error('Cursor restoration in progress');
 closed=true;focus=null;hover=false;captured=null;
 for(const h of hooks)h.detach();hooks.length=0;Interceptor.flush();
 releaseTargets();for(const f of fields.values())drop(f.layout);fields.clear();
 for(let i=refs.length-1;i>=0;i--)drop(refs[i]);refs.length=0;
}
function setFont(scale){
 if(!format.isNull()&&fontScale===scale&&activeFontLocale===fontLocale)return;
 const family=fontLocale==='en'?'Segoe UI':'Microsoft YaHei UI';
 const t=out();
 check(call(write,15,'int',['pointer','pointer','uint','uint','uint','float','pointer','pointer'],
  [Memory.allocUtf16String(family),N,400,0,5,18*scale,Memory.allocUtf16String(fontLocale),t]),'Text format');
 if(!format.isNull()){refs.splice(refs.indexOf(format),1);drop(format);}
 format=own(t.readPointer());fontScale=scale;activeFontLocale=fontLocale;
 for(const f of textFormats.values()){refs.splice(refs.indexOf(f),1);drop(f);}textFormats.clear();
 for(const [name,size,weight] of [['body',16,400],['button',16,500],['row',16,400],['small',14,400],['title',21,600]]){
  const o=out();check(call(write,15,'int',['pointer','pointer','uint','uint','uint','float','pointer','pointer'],
   [Memory.allocUtf16String(family),N,weight,0,5,size*scale,Memory.allocUtf16String(fontLocale),o]),'Panel typography');
  if(name==='button'||name==='row'){
   check(call(o.readPointer(),3,'int',['uint'],[name==='button'?2:0]),'Button text alignment');
   check(call(o.readPointer(),4,'int',['uint'],[2]),'Button vertical alignment');
   check(call(o.readPointer(),5,'int',['uint'],[1]),'Button no wrapping');
  }
  textFormats.set(name,own(o.readPointer()));
 }
 for(const f of fields.values()){drop(f.layout);f.layout=N;}
}
function setup(sc){
 const deviceOut=out();check(call(sc,7,'int',['pointer','pointer'],[guid(ids.device),deviceOut]),'SwapChain GetDevice');
 const device=own(deviceOut.readPointer());
 const qdev=out();check(call(queue,7,'int',['pointer','pointer'],[guid(ids.device),qdev]),'Queue GetDevice');
 const matches=qdev.readPointer().equals(device);drop(qdev.readPointer());
 if(!matches)throw Error('Captured queue belongs to another device');
 swap=own(qi(sc,ids.swap3));
 const q=out();q.writePointer(queue);const d=out(),c=out();
 check(api('d3d11.dll','D3D11On12CreateDevice','int',
  ['pointer','uint','pointer','uint','pointer','uint','uint','pointer','pointer','pointer'])(
    device,0x20,N,0,q,1,0,d,c,N),'D3D11On12CreateDevice');
 dev11=own(d.readPointer());ctx11=own(c.readPointer());on12=own(qi(dev11,ids.on12));
 createWrapped=method(on12,3,'int',['pointer','pointer','uint','uint','pointer','pointer']);
 releaseWrapped=method(on12,4,'void',['pointer','uint']);acquire=method(on12,5,'void',['pointer','uint']);
 flush=method(ctx11,111,'void',[]);
 const f=out();check(api('d2d1.dll','D2D1CreateFactory','int',['uint','pointer','pointer','pointer'])(1,guid(ids.d2d),N,f),'D2D factory');
 factory=own(f.readPointer());
 const w=out();check(api('dwrite.dll','DWriteCreateFactory','int',['uint','pointer','pointer'])(0,guid(ids.write),w),'DWrite factory');
 write=own(w.readPointer());setFont(scene.scale);
}
function textField(item){return fields.get(item.id);}
function fieldLayout(item){
 const f=textField(item),key=f.edit.text+':'+fontScale;
 if(!f.layout||f.layout.isNull()||f.layoutKey!==key){
  drop(f.layout);f.layout=N;
  const text=Memory.allocUtf16String(f.edit.text),o=out();
  check(call(write,18,'int',['pointer','uint','pointer','float','float','pointer'],
    [text,f.edit.text.length,format,65536,256,o]),'Text layout');
  f.layout=o.readPointer();f.layoutKey=key;f.string=text;
  f.positions=new Map();
  f.offset=Math.min(f.offset,Math.max(0,caretX(f,f.edit.points.length)-item.w+20*fontScale));
 }
 return f;
}
function caretX(f,index){
 if(f.positions.has(index))return f.positions.get(index);
 const x=Memory.alloc(4),y=Memory.alloc(4),metrics=Memory.alloc(36);
 const position=f.edit.points.slice(0,index).join('').length;
 check(call(f.layout,65,'int',['uint','int','pointer','pointer','pointer'],[position,0,x,y,metrics]),'Text caret');
 const value=x.readFloat();f.positions.set(index,value);return value;
}
function paintField(rt,brushes,i){
 const f=fieldLayout(i),padding=10*fontScale,area=i.w-2*padding,cx=focus===i.id?caretX(f,f.edit.caret):0;
 if(focus===i.id)f.offset=Math.max(0,Math.min(f.offset,cx),cx-area+2);
 call(rt,45,'void',['pointer','uint'],[i.rectangle,0]);
 try{
  const origin=i.x+padding-f.offset,yy=i.y+3*fontScale;
  if(focus===i.id){const [a,b]=f.edit.range;
   if(a!==b)call(rt,17,'void',['pointer','pointer'],
      [rect(origin+caretX(f,a),yy,caretX(f,b)-caretX(f,a),24*fontScale),brushes.selection]);}
  if(f.edit.text)call(rt,27,'void',['pointer','uint','pointer','pointer','pointer','uint','uint'],
      [f.string,f.edit.text.length,format,rect(origin,yy,65536,30*fontScale),brushes[i.enabled===false?'muted':'text'],0,0]);
  if(focus===i.id&&Date.now()%1000<650)call(rt,17,'void',['pointer','pointer'],
      [rect(origin+cx,yy,1.5*fontScale,24*fontScale),brushes.accent]);
 }finally{call(rt,46,'void',[],[]);}
}
function getTarget(index){
 if(targets[index])return targets[index];
 const resource=out();check(call(swap,9,'int',['uint','pointer','pointer'],[index,guid(ids.resource),resource]),'GetBuffer');
 const flags=Memory.alloc(16);flags.writeByteArray(new Array(16).fill(0));flags.writeU32(0x20);
 const wrapped=out();
 try{check(createWrapped(on12,resource.readPointer(),flags,0,0,guid(ids.texture),wrapped),'CreateWrappedResource');}
 finally{drop(resource.readPointer());}
 const texture=wrapped.readPointer(),surface=qi(texture,ids.surface);
 const properties=Memory.alloc(28);properties.writeByteArray(new Array(28).fill(0));
 properties.add(8).writeU32(3);properties.add(12).writeFloat(96);properties.add(16).writeFloat(96);
 const r=out();check(call(factory,15,'int',['pointer','pointer','pointer'],[surface,properties,r]),'CreateDxgiSurfaceRenderTarget');
 const rt=r.readPointer(), brushes={};
 for(const name of Object.keys(palette))brushes[name]=brush(rt,name);
 targets[index]={wrapped:texture,surface,rt,brushes};return targets[index];
}
function paint(sc){
 const desc=Memory.alloc(72);check(call(sc,12,'int',['pointer'],[desc]),'GetDesc');
 if(!desc.add(48).readPointer().equals(hwnd))return;
 updateAccess();
 if(panelAccess.active)listUI.tick(Date.now());
 width=desc.readU32();height=desc.add(4).readU32();
 if(queue.isNull()||scene.items.length===0)return;
 if(swap.isNull())setup(sc);
 setFont(scene.scale);
 const index=call(swap,36,'uint',[],[]),t=getTarget(index),array=out();array.writePointer(t.wrapped);
 acquire(on12,array,1);
 try{
  call(t.rt,48,'void',[],[]);
  const mouse=panelAccess.active?cursorPoint():null;
  for(const i of scene.items){
   const enabled=i.enabled!==false,over=enabled&&mouse&&contains(mouse[0],mouse[1],[i.x,i.y,i.w,i.h]);
   let fill=i.color,ink=i.textColor||'text';
   if(i.kind==='field')fill='field';
   if(i.kind==='button'){
    fill=i.selected?'selection':!enabled?'disabled':i.tone==='primary'?'primary':i.tone==='danger'?'danger':i.tone==='quiet'?'quiet':i.tone==='row'?'row':'button';
    if(enabled&&captured===i.id)fill='pressed';else if(over&&i.tone!=='primary')fill='hover';
    if(enabled&&i.tone==='primary'&&fill==='primary')ink='onPrimary';
    else if(enabled&&i.tone==='danger')ink='dangerText';
   }
   if(!enabled&&!i.selected)ink='muted';
   if(i.kind==='rect'||i.kind==='button'||i.kind==='field'){
    if(i.radius)call(t.rt,19,'void',['pointer','pointer'],[i.roundedRectangle,t.brushes[fill]||t.brushes.button]);
    else call(t.rt,17,'void',['pointer','pointer'],[i.rectangle,t.brushes[fill]||t.brushes.button]);
    if(i.outline||i.kind==='button'||i.kind==='field'){
     const edge=i.selected||focus===i.id?'accent':'border';
     if(i.radius&&(i.outline||i.kind!=='button'||i.tone!=='quiet'||i.selected||over))
      call(t.rt,18,'void',['pointer','pointer','float','pointer'],[i.outlineRectangle,t.brushes[edge],scene.scale,N]);
     if(i.selected)call(t.rt,17,'void',['pointer','pointer'],[i.selectionEdge,t.brushes.accent]);
    }
   }
   if(i.kind==='field')paintField(t.rt,t.brushes,i);
   else if(i.kind==='drag_handle'){
    if(over)call(t.rt,19,'void',['pointer','pointer'],[i.roundedRectangle,t.brushes.quiet]);
    for(const bar of i.gripBars)call(t.rt,17,'void',['pointer','pointer'],[bar,t.brushes[enabled?'muted':'border']]);
   }
   else if(i.text)call(t.rt,27,'void',['pointer','uint','pointer','pointer','pointer','uint','uint'],
      [i.string,i.text.length,textFormats.get(i.font)||format,i.textRectangle,t.brushes[ink]||t.brushes.text,2,0]);
  }
  for(const l of listUI.lists)if(listUI.limit(l)){
   const thumb=listUI.thumb(l);
   call(t.rt,19,'void',['pointer','pointer'],[rounded(...l.bar,4*scene.scale),t.brushes.quiet]);
   call(t.rt,19,'void',['pointer','pointer'],[rounded(...thumb,4*scene.scale),t.brushes.border]);
  }
  const insertion=listUI.indicator();
  if(insertion)call(t.rt,17,'void',['pointer','pointer'],[rect(...insertion),t.brushes.accent]);
  if(panelAccess.active&&mouse){
   const size=Math.max(1,scene.scale);
   for(const row of cursorRows)call(t.rt,17,'void',['pointer','pointer'],
    [rect(mouse[0]+row.x*size,mouse[1]+row.y*size,row.w*size,row.h*size),t.brushes[row.color]]);
  }
  check(call(t.rt,49,'int',['pointer','pointer'],[N,N]),'D2D EndDraw');frames++;
 }finally{releaseWrapped(on12,array,1);flush(ctx11);}
}
function point(lparam){let x=lparam.toInt32()&0xffff,y=(lparam.toInt32()>>>16)&0xffff;
 if(x&0x8000)x-=65536;if(y&0x8000)y-=65536;
 const client=Memory.alloc(16);getClientRect(hwnd,client);
 return [x*width/Math.max(1,client.add(8).readS32()),y*height/Math.max(1,client.add(12).readS32())];}
function contains(x,y,b){return x>=b[0]&&y>=b[1]&&x<b[0]+b[2]&&y<b[1]+b[3];}
const getClientRect=api('user32.dll','GetClientRect','int',['pointer','pointer']);
function installInput(){
 const captureMouse=api('user32.dll','SetCapture','pointer',['pointer']);
 const getCapture=api('user32.dll','GetCapture','pointer',[]);
 const releaseCapture=api('user32.dll','ReleaseCapture','int',[]);
 const inputThread=api('user32.dll','GetWindowThreadProcessId','uint',['pointer','pointer'])(hwnd,N);
 const listCapture=new PanelCapture({onThread:()=>Process.getCurrentThreadId()===inputThread,
  grab:()=>captureMouse(hwnd),captured:()=>getCapture().equals(hwnd),release:()=>releaseCapture()});
 listCapturePending=()=>listCapture.holding;
 releaseListCapture=()=>{
  if(listCapture.end()&&captured==='list')captured=null;
 };
 const getCursor=api('user32.dll','GetCursorPos','int',['pointer']);
 const getCursorClip=api('user32.dll','GetClipCursor','int',['pointer']);
 const clipCursor=api('user32.dll','ClipCursor','int',['pointer']);
 const setCursor=api('user32.dll','SetCursor','pointer',['pointer']);
 let clipBefore=N,cursorBefore=N,cursorOwn=false;
 cursorPoint=()=>{const p=Memory.alloc(8);if(!getCursor(p))return null;screenToClient(hwnd,p);
  const client=Memory.alloc(16);getClientRect(hwnd,client);
  return [p.readS32()*width/Math.max(1,client.add(8).readS32()),p.add(4).readS32()*height/Math.max(1,client.add(12).readS32())];};
 releaseAccess=()=>{
  listUI.cancel();releaseListCapture();
  if(!panelAccess.active)return;
  panelAccess.active=false;focus=null;hover=false;captured=null;highSurrogate='';
  cursorOwn=true;try{if(foregroundWindow().equals(hwnd)){setCursor(cursorBefore);clipCursor(clipBefore);}}finally{cursorOwn=false;}
 };
 updateAccess=()=>{
  let held;seedingKeys=true;try{held=(asyncKey(panelKey)&0x8000)!==0;}finally{seedingKeys=false;}
  const foreground=foregroundWindow().equals(hwnd),was=panelAccess.active;
  const change=panelAccess.update(held,foreground&&!closing);
  if(change==='leave'){panelAccess.active=was;releaseAccess();}
  if(change==='enter'){
   clipBefore=Memory.alloc(16);if(!getCursorClip(clipBefore))clipBefore=N;
   cursorOwn=true;try{cursorBefore=setCursor(N);clipCursor(N);}finally{cursorOwn=false;}
   if(recorder&&['playing','preparing'].includes(recorder.mode)){
    recorder.needsReplay=true;recorder.stop('已进入面板操作，自动播放停止。');
   }
  }
 };
 hooks.push(Interceptor.attach(Module.getGlobalExportByName('ClipCursor'),{onEnter(args){
  if(!panelAccess.active||cursorOwn)return;
  clipBefore=args[0].isNull()?N:Memory.alloc(16);
  if(!args[0].isNull())clipBefore.writeByteArray(args[0].readByteArray(16));args[0]=N;
 }}));
 hooks.push(Interceptor.attach(Module.getGlobalExportByName('SetCursor'),{onEnter(args){
  if(panelAccess.active&&!cursorOwn){cursorBefore=args[0];args[0]=N;}
 }}));
 hooks.push(Interceptor.attach(Module.getGlobalExportByName('SetCursorPos'),{onEnter(args){
  if(!panelAccess.active)return;const p=Memory.alloc(8);
  if(getCursor(p)){args[0]=ptr(p.readS32());args[1]=ptr(p.add(4).readS32());}
 }}));
 const translate=api('user32.dll','TranslateMessage','int',['pointer']);
 const raw=api('user32.dll','GetRawInputData','uint',['pointer','uint','pointer','pointer','uint']);
 const defaultProc=api('user32.dll','DefWindowProcW','int64',['pointer','uint','pointer','pointer']);
 const keyState=api('user32.dll','GetKeyState','int16',['int']);
 const messageExtra=api('user32.dll','GetMessageExtraInfo','int64',[]);
 const screenToClient=api('user32.dll','ScreenToClient','int',['pointer','pointer']);
 const immContext=api('imm32.dll','ImmGetContext','pointer',['pointer']);
 const immRelease=api('imm32.dll','ImmReleaseContext','int',['pointer','pointer']);
 const immString=api('imm32.dll','ImmGetCompositionStringW','int',['pointer','uint','pointer','uint']);
 const openClip=api('user32.dll','OpenClipboard','int',['pointer']),closeClip=api('user32.dll','CloseClipboard','int',[]);
 const getClip=api('user32.dll','GetClipboardData','pointer',['uint']);
 const lock=api('kernel32.dll','GlobalLock','pointer',['pointer']),unlock=api('kernel32.dll','GlobalUnlock','int',['pointer']);
 const globalSize=api('kernel32.dll','GlobalSize','uint64',['pointer']);
 const allocate=api('kernel32.dll','GlobalAlloc','pointer',['uint','size_t']);
 const free=api('kernel32.dll','GlobalFree','pointer',['pointer']);
 const emptyClip=api('user32.dll','EmptyClipboard','int',[]);
 const setClip=api('user32.dll','SetClipboardData','pointer',['uint','pointer']);
 function copy(cut){
  const f=fields.get(focus);if(!f||!f.edit.selected)return;
  const value=f.edit.selected,handle=allocate(2,(value.length+1)*2);if(handle.isNull())return;
  let transferred=false;
  try{
   const data=lock(handle);if(data.isNull())return;
   try{data.writeUtf16String(value);}finally{unlock(handle);}
   if(!openClip(hwnd))return;
   try{if(emptyClip()&&!setClip(13,handle).isNull())transferred=true;}finally{closeClip();}
   if(transferred&&cut)edit(e=>e.insert(''));
  }finally{if(!transferred)free(handle);}
 }
 function paste(){
  if(!openClip(hwnd))return;
  try{const handle=getClip(13);if(handle.isNull())return;
   const bytes=Number(globalSize(handle));if(bytes<=0||bytes>1024*1024)return;
   const data=lock(handle);if(data.isNull())return;
   try{const value=data.readUtf16String(Math.floor(bytes/2)).split('\0')[0];edit(e=>e.insert(value));}
   finally{unlock(handle);}
  }finally{closeClip();}
 }
 function edit(operation){
  const f=fields.get(focus);if(!f)return;
  const before=f.edit.revision;operation(f.edit);
  if(before!==f.edit.revision)send({kind:'ui',action:focus,value:f.edit.text,revision:f.edit.revision});
 }
 function imeResult(){
  const context=immContext(hwnd);if(context.isNull())return;
  try{const bytes=immString(context,0x800,N,0);
   if(bytes>0&&bytes<=4096){const p=Memory.alloc(bytes+2);
    if(immString(context,0x800,p,bytes)===bytes)edit(e=>e.insert(p.readUtf16String(bytes/2)));}
  }finally{immRelease(hwnd,context);}
 }
 function hitField(item,x,y,select){
  const f=textField(item);if(!f.layout||f.layout.isNull())return;
  const trailing=Memory.alloc(4),inside=Memory.alloc(4),metrics=Memory.alloc(36);
  check(call(f.layout,64,'int',['float','float','pointer','pointer','pointer'],
   [x-item.x-10*fontScale+f.offset,y-item.y-3*fontScale,trailing,inside,metrics]),'Text hit test');
  const at=metrics.readU32()+(trailing.readS32()?metrics.add(4).readU32():0);
  f.edit.move(Array.from(f.edit.text.slice(0,at)).length,select);
 }
 function recordKey(vk,down,source,stamp,own){
  if(!foregroundWindow().equals(hwnd))recorder.focusLost();
  const modifiers=[16,17,18,91,92].some(k=>k!==vk&&(keyState(k)&0x8000)!==0);
  const valid=!['recording','preparing'].includes(recorder.mode)||panelAccess.active||recordBindingsValid();
  const consumed=recorder.packet(vk,down,source,stamp,{ui:panelAccess.active,valid,modifiers,own});
  return consumed||(own&&down&&recorder.mode!=='playing');
 }
 function route(window,msg,wparam,lparam,fromPump=false,stamp=0){
  if(!window.equals(hwnd)||closed)return false;
  updateAccess();
  if(msg===0x215){listUI.cancel();listCapture.lost();if(captured==='list')captured=null;}
  if(msg===0x8||(msg===0x6&&(wparam.toUInt32()&0xffff)===0)){
   panelAccess.rearm=true;releaseAccess();
   if(recorder)recorder.focusLost();
   focus=null;hover=false;captured=null;highSurrogate='';return false;
  }
  if([0x100,0x101,0x104,0x105].includes(msg)&&wparam.toUInt32()===panelKey)return true;
  if(msg===0x102&&((panelKey===0xc0&&[96,126].includes(wparam.toUInt32()))||
     (panelKey>=48&&panelKey<=90&&[panelKey,panelKey+32].includes(wparam.toUInt32()))))return true;
  // 同一排队消息还会经过 WndProc；只在 PM_REMOVE 后处理一次录制决策。
  if(fromPump&&recorder&&[0x100,0x101,0x104,0x105].includes(msg)){
   const down=msg===0x100||msg===0x104,vk=wparam.toUInt32();
   const own=ownInputTags.has(messageExtra().toString());
   if(recordKey(vk,down,'message',stamp,own))return true;
   if(own)return false; // 工具松开事件始终交还游戏。
  }
  if(msg===0xff&&(recorder||panelAccess.active)){
   const header=Memory.alloc(24),size=Memory.alloc(4);size.writeU32(24);
   if(raw(lparam,0x10000005,header,size,24)===24){
    const type=header.readU32();
    if(type===1){const data=Memory.alloc(40);size.writeU32(40);
     if(raw(lparam,0x10000003,data,size,24)===40){
      if(data.add(30).readU16()===panelKey){defaultProc(hwnd,msg,wparam,lparam);return true;}
      if(panelAccess.active&&(data.add(26).readU16()&1)!==0){
       if(recorder)recorder.packet(data.add(30).readU16(),false,'raw',stamp,{ui:true});return false;
      }
     }
    }
    if(fromPump&&recorder&&type===1){
     const data=Memory.alloc(40);size.writeU32(40);
     if(raw(lparam,0x10000003,data,size,24)===40){
      const vk=data.add(30).readU16(),down=(data.add(26).readU16()&1)===0;
      const own=ownRawTags.has(data.add(36).readU32().toString())||ownInputTags.has(messageExtra().toString());
      if(vk<255&&recordKey(vk,down,'raw',stamp,own)){
       defaultProc(hwnd,msg,wparam,lparam);return true;
      }
      if(own)return false;
     }
    }
    if(panelAccess.active&&(type===1||type===0)){defaultProc(hwnd,msg,wparam,lparam);return true;}
   }
  }
  if(!panelAccess.active){
   if(fromPump&&msg===0x201&&recorder&&recorder.mode==='idle')recorder.needsReplay=true;
   return false;
  }
  if((msg===0x100||msg===0x104)&&wparam.toUInt32()===27&&listUI.active){
   listUI.cancel();releaseListCapture();return true;
  }
  if(msg===0x101||msg===0x105)return false; // 交还松键，避免进入面板前的游戏持键残留。
  let consume=false;
  if(msg>=0x200&&msg<=0x20e){
   let mouseParam=lparam;
   if(msg===0x20a||msg===0x20e){const p=Memory.alloc(8),v=lparam.toUInt32();
    p.writeS32((v<<16)>>16);p.add(4).writeS32(v>>16);screenToClient(hwnd,p);
    mouseParam=ptr(((p.add(4).readS32()&0xffff)<<16)|(p.readS32()&0xffff));}
   const [x,y]=point(mouseParam);hover=(scene.regions||[scene.bounds]).some(r=>contains(x,y,r));
   if(msg===0x20a&&listUI.wheel(x,y,wparam.toUInt32()>>16))return true;
   if(msg===0x201&&listUI.down(x,y)){
    focus=null;highSurrogate='';captured='list';
    if(!listCapture.begin()){listUI.cancel();captured=null;}
    return true;
   }
   if(msg===0x200&&listUI.active){
    listUI.move(x,y);if(!listUI.active)releaseListCapture();return true;
   }
   if(msg===0x202&&listUI.active){listUI.up(x,y);releaseListCapture();return true;}
   if(fromPump&&msg===0x201&&!hover&&recorder&&recorder.mode==='idle'&&!recorder.needsReplay){
    recorder.needsReplay=true;recorder.revision++;
   }
   if(msg===0x201){captured=hover?'panel':null;focus=null;highSurrogate='';
    if(hover){const item=scene.items.find(i=>(i.kind==='field'||i.kind==='button')&&contains(x,y,[i.x,i.y,i.w,i.h]));
      if(item&&item.enabled!==false){captured=item.id;
       if(item.kind==='field'){
        focus=item.id;hitField(item,x,y,(keyState(0x10)&0x8000)!==0);
        if(item.limit===1)textField(item).edit.key('a',false,true);
       }
      }}}
   if(msg===0x200&&focus&&captured===focus&&(wparam.toUInt32()&1)!==0){
    const item=scene.items.find(i=>i.id===focus);if(item)hitField(item,x,y,true);
   }
   consume=hover||captured;
   if(msg===0x202&&captured){const down=captured;captured=null;
    const item=scene.items.find(i=>i.id===down&&i.enabled!==false&&i.kind==='button'&&contains(x,y,[i.x,i.y,i.w,i.h]));
    if(item)send({kind:'ui',action:item.id});}
  }else if(focus&&msg===0x10f){if((lparam.toUInt32()&0x800)!==0)imeResult();return true;
  }else if(focus&&msg===0x10e){return true;
  }else if(focus&&msg>=0x100&&msg<=0x103){
   consume=true;
   const key=wparam.toUInt32();
   if(msg===0x100){
    const ctrl=(keyState(0x11)&0x8000)!==0,shift=(keyState(0x10)&0x8000)!==0;
    if(key===27||key===13)focus=null;
    else if(key===9){const available=scene.items.filter(i=>i.kind==='field'&&i.enabled!==false);
     const index=available.findIndex(i=>i.id===focus);focus=available[(index+(shift?available.length-1:1))%available.length]?.id||null;}
    else if(ctrl&&key===86)paste();
    else if(ctrl&&(key===67||key===88))copy(key===88);
    else if(ctrl&&key===65)edit(e=>e.key('a',shift,true));
    else{const names={8:'Backspace',46:'Delete',35:'End',36:'Home',37:'Left',39:'Right'};
     if(names[key])edit(e=>e.key(names[key],shift,ctrl));}
   }
   if(msg===0x102){chars++;
    if(key>=0xd800&&key<=0xdbff)highSurrogate=String.fromCharCode(key);
    else if(key>=32&&key!==127){const value=highSurrogate+String.fromCharCode(key);highSurrogate='';edit(e=>e.insert(value));}}
  }
  return consume||(msg>=0x100&&msg<=0x109)||(msg>=0x200&&msg<=0x20e);
 }
 hooks.push(Interceptor.attach(Module.getGlobalExportByName('PeekMessageW'),{
  onEnter(args){if(listCapture.pending)releaseListCapture();this.msg=args[0];this.remove=(args[4].toUInt32()&1)!==0;},
  onLeave(result){
   if(closed||!this.remove||result.toInt32()===0)return;
   const m=this.msg,window=m.readPointer(),msg=m.add(8).readU32();
   if(!window.equals(hwnd))return;
   // 游戏可能在消息泵内自行处理键盘，不能只拦截 WndProc。
   if(focus&&msg===0x100){translating=true;try{translate(m);}finally{translating=false;}}
   if(route(window,msg,m.add(16).readPointer(),m.add(24).readPointer(),true,m.add(32).readU32())){
    m.add(8).writeU32(0);m.add(16).writePointer(N);m.add(24).writePointer(N);
   }
  }
 }));
 const proc=api('user32.dll','GetWindowLongPtrW','pointer',['pointer','int'])(hwnd,-4);
 hooks.push(Interceptor.attach(proc,{onEnter(args){
  if(route(args[0],args[1].toUInt32(),args[2],args[3])){args[1]=N;args[2]=N;args[3]=N;}
 }}));
 hooks.push(Interceptor.attach(Module.getGlobalExportByName('GetAsyncKeyState'),{
  onEnter(args){const vk=args[0].toInt32();this.block=!seedingKeys&&(vk===panelKey||panelAccess.active||(recorder&&recorder.blocksPolling(vk)));},
  onLeave(result){if(this.block&&!closed)result.replace(0);}
 }));
 hooks.push(Interceptor.attach(Module.getGlobalExportByName('GetKeyboardState'),{
  onEnter(args){this.keys=args[0];this.block=panelAccess.active;this.mouse=hover||captured;},
  onLeave(result){if(result.toInt32()&&!closed&&!translating){if(this.block)this.keys.writeByteArray(new Array(256).fill(0));
    else{this.keys.add(panelKey).writeU8(0);if(this.mouse)this.keys.writeByteArray(new Array(7).fill(0));
     if(recorder&&!seedingKeys)for(let vk=8;vk<256;vk++)if(recorder.blocksPolling(vk))this.keys.add(vk).writeU8(0);}}}
 }));
 hooks.push(Interceptor.attach(Module.getGlobalExportByName('TranslateMessage'),{
  onEnter(args){
   // 在 PeekMessage 内只翻译普通字符；控件导航键不生成退格／控制字符。
   if(!focus||translating)return;
   const m=args[0];if(!m.readPointer().equals(hwnd))return;
   if(m.add(8).readU32()===0x100){const key=m.add(16).readU32();
    if([8,9,13,27,35,36,37,39,46].includes(key)||(keyState(0x11)&0x8000)!==0)m.add(8).writeU32(0);}
  }
 }));
}
function bootstrap(){
 const device=out();check(api('d3d12.dll','D3D12CreateDevice','int',['pointer','uint','pointer','pointer'])(N,0xb000,guid(ids.device),device),'Dummy device');
 const d=device.readPointer(),q=out(),desc=Memory.alloc(16);desc.writeByteArray(new Array(16).fill(0));
 let command=N,f=N,window=N,sc=N;
 try{
  check(call(d,8,'int',['pointer','pointer','pointer'],[desc,guid('0ec870a6-5d7e-4c22-8cfc-5baae07616ed'),q]),'Dummy queue');command=q.readPointer();
  const factoryOut=out();check(api('dxgi.dll','CreateDXGIFactory1','int',['pointer','pointer'])(guid(ids.factory),factoryOut),'Dummy factory');f=factoryOut.readPointer();
  window=api('user32.dll','CreateWindowExW','pointer',['uint','pointer','pointer','uint','int','int','int','int','pointer','pointer','pointer','pointer'])(
    0,Memory.allocUtf16String('STATIC'),Memory.allocUtf16String(''),0,0,0,8,8,N,N,N,N);
  if(window.isNull())throw Error('Cannot create hidden bootstrap window');
  const sdesc=Memory.alloc(72);sdesc.writeByteArray(new Array(72).fill(0));
  sdesc.writeU32(8);sdesc.add(4).writeU32(8);sdesc.add(16).writeU32(87);sdesc.add(28).writeU32(1);
  sdesc.add(36).writeU32(0x20);sdesc.add(40).writeU32(2);sdesc.add(48).writePointer(window);
  sdesc.add(56).writeU32(1);sdesc.add(60).writeU32(4);
  const sout=out();check(call(f,10,'int',['pointer','pointer','pointer'],[command,sdesc,sout]),'Dummy swapchain');sc=sout.readPointer();
  const present=sc.readPointer().add(8*8).readPointer(),resize=sc.readPointer().add(13*8).readPointer();
  const execute=command.readPointer().add(10*8).readPointer();
  hooks.push(Interceptor.attach(execute,{onEnter(args){
   if(closed||drawing||!queue.isNull()||args[1].toUInt32()===0)return;
   try{const list=args[2].readPointer();if(call(list,8,'uint',[],[])===0){queue=args[0];call(queue,1,'uint',[],[]);own(queue);}}
   catch(e){error=String(e);}
  }}));
  hooks.push(Interceptor.attach(present,{onEnter(args){
   if(closed||drawing||error)return;drawing=true;
   try{paint(args[0]);}catch(e){error=String(e);}finally{drawing=false;}
  }}));
  hooks.push(Interceptor.attach(resize,{onEnter(args){
   if(!swap.isNull()&&args[0].equals(swap)){releaseTargets();width=0;height=0;}
  }}));
 }finally{
  drop(sc);if(!window.isNull())api('user32.dll','DestroyWindow','int',['pointer'])(window);
  drop(f);drop(command);drop(d);
 }
 installInput();Interceptor.flush();
 globalThis._panelOwner={};Script.bindWeak(globalThis._panelOwner,()=>{try{shutdown();}catch(_){}});
}
rpc.exports={
 install(window){hwnd=ptr(window);bootstrap();},
 setToggle(value){
  if(!Number.isInteger(value)||!([9,35,36,45,46,192].includes(value)||(value>=48&&value<=90)||(value>=112&&value<=123)))throw Error('Invalid panel toggle');
  panelKey=value;panelAccess.rearm=true;panelAccess.held=true;return value;
 },
 model(value){
  fontLocale=value.locale==='en'?'en':'zh-CN';
  if(value.items.length>128)throw Error('Too many panel items');
  for(const i of value.items.filter(i=>i.kind==='field')){
   let f=fields.get(i.id);
   if(!f){f={edit:new PanelText(i.text,i.limit),layout:N,offset:0};fields.set(i.id,f);}
   if(i.revision>f.edit.revision){f.edit.set(i.text);f.edit.revision=i.revision;}
  }
  scene={bounds:value.bounds,regions:value.regions||[value.bounds],scale:value.scale||1,items:value.items.map(i=>({...i,rectangle:rect(i.x,i.y,i.w,i.h),
    roundedRectangle:rounded(i.x,i.y,i.w,i.h,i.radius||0),
    outlineRectangle:rounded(i.x+.5*(value.scale||1),i.y+.5*(value.scale||1),i.w-(value.scale||1),i.h-(value.scale||1),Math.max(0,(i.radius||0)-.5*(value.scale||1))),
    selectionEdge:rect(i.x+2*(value.scale||1),i.y+8*(value.scale||1),3*(value.scale||1),i.h-16*(value.scale||1)),
    gripBars:[rect(i.x+6*(value.scale||1),i.y+12*(value.scale||1),2*(value.scale||1),16*(value.scale||1)),rect(i.x+12*(value.scale||1),i.y+12*(value.scale||1),2*(value.scale||1),16*(value.scale||1))],
    textRectangle:rect(...panelTextBounds(i,value.scale||1)),
    string:Memory.allocUtf16String(i.text||'')}))};
  listUI.setModel(value.lists||[],scene.scale);
  if(!listUI.active)releaseListCapture();
  if(!scene.items.some(i=>i.kind==='field'&&i.id===focus&&i.enabled!==false))focus=null;
 },
 status(){updateAccess();return {width,height,frames:frames>0,queue:!queue.isNull(),error,focus,chars,mouseActive:panelAccess.active};},
 recordingLoad(document,policy,prefix,needsReplay){
  if(recorder&&['recording','completing'].includes(recorder.mode))throw Error('请先停止录制并等待 P 完成。');
  recorder=new PanelRecorder(document,policy,prefix);recorder.needsReplay=needsReplay;recorder.setPaused(recordPaused);prepareRecordGuards(policy);
  return recorder.status();
 },
 recordingPolicy(policy){
  if(!recorder)return;
  if(['recording','completing'].includes(recorder.mode)&&(recorder.policy.digest!==policy.digest||policy.errors.length)){
   recorder.needsReplay=true;recorder.stop('游戏键位／冲突状态变化，录制已停止。');
  }
  recorder.policy=policy;prepareRecordGuards(policy);
 },
 recordingStart(){
  if(!recorder)throw Error('没有活动工程。');
  if(!foregroundWindow().equals(hwnd))throw Error('请保持游戏在前台，再开始录制。');
  if(!recordBindingsValid())throw Error('键位快照已变化，请重试。');
  recorder.start();
  recorder.held.clear();
  seedingKeys=true;try{for(let vk=8;vk<256;vk++)if(asyncKey(vk)&0x8000)recorder.held.add(vk);}finally{seedingKeys=false;}
  releaseAccess();panelAccess.rearm=true;
  return recorder.status();
 },
 leavePanel(){
  if(!foregroundWindow().equals(hwnd))throw Error('游戏已失焦，未开始播放。');
  releaseAccess();panelAccess.rearm=true;return true;
 },
 recordingStop(reason){if(recorder)recorder.stop(reason||'录制已结束。');return recorder?recorder.status():null;},
 recordingPaused(value){recordPaused=!!value;if(recorder)recorder.setPaused(recordPaused);return recordPaused;},
 recordingSolveResult(ok,error){if(recorder)recorder.solveResult(ok,error);return recorder?recorder.status():null;},
 recordingStatus(){return recorder?{...recorder.status(),panelActive:panelAccess.active}:null;},
 recordingSnapshot(){return recorder?{document:recorder.document,state:recorder.status()}:null;},
 recordingMode(mode,needsReplay){
  if(!recorder)return;
  if(!['idle','playing','preparing'].includes(mode))throw Error('Invalid recorder mode');
  recorder.mode=mode;recorder.needsReplay=needsReplay;recorder.revision++;
 },
 recordingOwnTag(tag){
  if(!/^[0-9]{1,19}$/.test(tag))throw Error('Invalid input tag');
  ownInputTags.add(tag);
  ownRawTags.add(uint64(tag).and(uint64('4294967295')).toString());
  if(ownInputTags.size>256)ownInputTags.delete(ownInputTags.values().next().value);
  if(ownRawTags.size>256)ownRawTags.delete(ownRawTags.values().next().value);
 },
 recordingClear(){recorder=null;recordGuards=[];recordPaused=false;},
 close(){shutdown();return {closed:true};}
};

