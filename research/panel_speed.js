'use strict';
// 只管理已验证的基础倍率，不修改原生快慢键倍率、游戏时钟或输入间隔。
class OwnedSpeed {
 constructor(io,original=null){
  this.io=io;this.last=this.read();this.original=original===null?this.last:original;
  if(!OwnedSpeed.valid(this.original))throw Error('Invalid original game speed');
 }
 static valid(v){return typeof v==='number'&&Number.isFinite(v)&&v>=0&&v<=16;}
 read(){const v=this.io.read();if(!OwnedSpeed.valid(v))throw Error('Invalid game speed');return v;}
 raw(value){
  if(!OwnedSpeed.valid(value))throw Error('Invalid game speed');
  const before=this.read();if(before!==this.last)throw Error('Game speed ownership changed; no memory overwritten');
  if(value===before)return value;
  this.last=value;
  try{this.io.write(value);if(this.read()!==value)throw Error('Game speed write verification failed');}
  catch(error){try{if(this.read()===before)this.last=before;}catch(_){}throw error;}
  return value;
 }
 set(value){if(![0,.25,1,4].includes(value))throw Error('Unsupported speed preset');return this.raw(value);}
 restore(){return this.raw(this.original);}
}
if(typeof module!=='undefined')module.exports={OwnedSpeed};
