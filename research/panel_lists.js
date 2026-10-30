'use strict';
// 无系统依赖的列表交互。只有松开有效拖动才发布一次排序请求。
class PanelLists {
 constructor(emit){this.emit=emit;this.lists=[];this.scale=1;this.gesture=null;this.remainders=new Map();}
 get active(){return this.gesture!==null;}
 setModel(lists,scale=1){
  this.lists=lists.map(l=>({...l,rows:l.rows||[]}));this.scale=scale;
  if(this.gesture){const l=this.lists.find(l=>l.id===this.gesture.list);
   if(!l||(this.gesture.kind==='drag'&&(l.version!==this.gesture.version||!l.editable)))this.cancel();}
 }
 inside(x,y,b){return x>=b[0]&&y>=b[1]&&x<b[0]+b[2]&&y<b[1]+b[3];}
 limit(l){return Math.max(0,l.count-l.visible);}
 thumb(l){const [x,y,w,h]=l.bar;const size=Math.min(h,Math.max(24*this.scale,h*l.visible/Math.max(1,l.count)));
  return [x,y+(h-size)*(l.offset/Math.max(1,this.limit(l))),w,size];}
 offset(l,value){
  const at=Math.max(0,Math.min(this.limit(l),Math.round(value)));
  l.offset=at;this.emit({action:'scroll_list',list:l.id,offset:at});
 }
 wheel(x,y,delta){
  const l=this.lists.find(l=>this.inside(x,y,l.bounds)||this.inside(x,y,l.bar));if(!l)return false;
  if(!delta||!this.limit(l))return true;
  const pending=(this.remainders.get(l.id)||0)+delta;
  const steps=Math.trunc(pending/120);this.remainders.set(l.id,pending-steps*120);
  if(steps)this.offset(l,l.offset-steps*3);return true;
 }
 down(x,y){
  this.cancel();
  for(const l of this.lists){
   if(this.limit(l)&&this.inside(x,y,l.bar)){
    const thumb=this.thumb(l),onThumb=this.inside(x,y,thumb);
    this.gesture={kind:'scroll',list:l.id,version:l.version,grab:onThumb?y-thumb[1]:thumb[3]/2};
    if(!onThumb)this.move(x,y);return true;
   }
   if(!l.editable)continue;
   const row=l.rows.find(r=>this.inside(x,y,r.handle));
   if(row){this.gesture={kind:'drag',list:l.id,version:l.version,id:row.id,x,y,
      pointer:[x,y],started:false,index:row.index,lastScroll:null};return true;}
  }
  return false;
 }
 move(x,y){
  const g=this.gesture;if(!g)return false;
  const l=this.lists.find(l=>l.id===g.list);if(!l){this.cancel();return true;}
  if(g.kind==='scroll'){
   const thumb=this.thumb(l),distance=l.bar[3]-thumb[3];
   this.offset(l,distance<=0?0:(y-l.bar[1]-g.grab)/distance*this.limit(l));return true;
  }
  if(!this.inside(x,y,l.bounds)){this.cancel();return true;}
  g.pointer=[x,y];
  if(Math.hypot(x-g.x,y-g.y)>=4*this.scale)g.started=true;
  g.index=Math.max(0,Math.min(l.count,l.offset+Math.floor((y-l.bounds[1])/l.rowHeight+.5)));
  return true;
 }
 tick(now){
  const g=this.gesture;if(!g||g.kind!=='drag'||!g.started)return;
  const l=this.lists.find(l=>l.id===g.list);if(!l)return;
  const y=g.pointer[1],edge=Math.min(24*this.scale,l.bounds[3]/3);
  const direction=y<l.bounds[1]+edge?-1:y>l.bounds[1]+l.bounds[3]-edge?1:0;
  if(direction&&(g.lastScroll===null||now-g.lastScroll>=90)){
   const next=Math.max(0,Math.min(this.limit(l),l.offset+direction));
   if(next!==l.offset){this.offset(l,next);this.move(...g.pointer);}
   g.lastScroll=now;
  }
 }
 up(x,y){
  const g=this.gesture;if(!g)return false;
  this.move(x,y);
  if(this.gesture&&g.kind==='drag'&&g.started)
   this.emit({action:'move_step',id:g.id,index:g.index,version:g.version});
  this.cancel();return true;
 }
 indicator(){
  const g=this.gesture;if(!g||g.kind!=='drag'||!g.started)return null;
  const l=this.lists.find(l=>l.id===g.list);if(!l)return null;
  return [l.bounds[0],l.bounds[1]+Math.min(l.bounds[3]-2*this.scale,Math.max(0,(g.index-l.offset)*l.rowHeight)),l.bounds[2],2*this.scale];
 }
 cancel(){this.gesture=null;}
}
// GetCapture / ReleaseCapture 是线程相关接口；RPC 线程只排队，窗口消息线程实际释放。
class PanelCapture {
 constructor(api){this.api=api;this.holding=false;this.pending=false;}
 begin(){
  if(!this.api.onThread())return false;
  this.api.grab();this.holding=this.api.captured();this.pending=false;return this.holding;
 }
 end(){
  if(!this.holding){this.pending=false;return true;}
  this.pending=true;if(!this.api.onThread())return false;
  if(this.api.captured())this.api.release();
  if(this.api.captured())return false;
  this.lost();return true;
 }
 lost(){this.holding=false;this.pending=false;}
}
if(typeof module!=='undefined')module.exports={PanelLists,PanelCapture};
