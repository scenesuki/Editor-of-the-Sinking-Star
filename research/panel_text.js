'use strict';
// 与 Windows 消息、渲染分离；按 Unicode 码点编辑，避免拆开代理对。
class PanelText {
 constructor(text='',limit=64){this.limit=limit;this.set(text);this.revision=0;}
 set(text){this.points=Array.from(String(text)).slice(0,this.limit);this.caret=this.points.length;this.anchor=this.caret;}
 get text(){return this.points.join('');}
 get range(){return [Math.min(this.caret,this.anchor),Math.max(this.caret,this.anchor)];}
 get selected(){const [a,b]=this.range;return this.points.slice(a,b).join('');}
 insert(value){
  const [a,b]=this.range,room=this.limit-this.points.length+b-a;
  const points=Array.from(String(value).replace(/[\x00-\x1f\x7f]/g,'')).slice(0,room);
  this.points.splice(a,b-a,...points);this.caret=this.anchor=a+points.length;this.revision++;
 }
 move(to,select=false){this.caret=Math.max(0,Math.min(this.points.length,to));if(!select)this.anchor=this.caret;}
 key(key,shift=false,ctrl=false){
  if(ctrl&&key.toLowerCase()==='a'){this.anchor=0;this.caret=this.points.length;return;}
  const [a,b]=this.range;
  if(key==='Home')this.move(0,shift);
  else if(key==='End')this.move(this.points.length,shift);
  else if(key==='Left')this.move(!shift&&a!==b?a:this.caret-1,shift);
  else if(key==='Right')this.move(!shift&&a!==b?b:this.caret+1,shift);
  else if(key==='Backspace'||key==='Delete'){
   if(a===b){if(key==='Backspace')this.anchor=Math.max(0,this.caret-1);else this.anchor=Math.min(this.points.length,this.caret+1);}
   this.insert('');
  }
 }
}
function panelTextBounds(item,scale){
 if(item.kind==='button')return [item.x+10*scale,item.y,item.w-20*scale,item.h];
 return [item.x+((item.kind==='button'||item.kind==='field')?10*scale:0),
         item.y+(item.kind==='button'?6:3)*scale,item.w-12*scale,item.h-6*scale];
}
if(typeof module!=='undefined')module.exports={PanelText,panelTextBounds};
