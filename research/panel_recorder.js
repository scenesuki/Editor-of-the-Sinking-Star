'use strict';
// 纯录制事件模型。同步决定 Z 是否透传，不依赖 Python 的轮询响应。
class PanelRecorder {
 constructor(document,policy,idPrefix){
  this.document=JSON.parse(JSON.stringify(document));this.policy=policy;
  this.prefix=idPrefix;this.serial=0;this.held=new Set();this.blocked=new Set();
  this.allowedUndo=new Set();this.packets=new Map();
  this.mode='idle';this.pending=false;this.needsReplay=this.document.steps.length>0;this.paused=false;
  this.reason='';this.revision=0;this.documentRevision=0;
 }
 readyAtTail(){this.needsReplay=false;this.revision++;}
 start(){
  if(this.policy.errors.length)throw Error(this.policy.errors.join('\n'));
  this.needsReplay=false;
  this.mode='recording';this.pending=false;this.reason='正在录制；全部短按，不要长按。';this.revision++;
 }
 stop(reason='录制已结束。'){
  if(this.pending)reason+=' 未使用的等待标记已丢弃。';
  this.pending=false;this.mode='idle';this.reason=reason;this.revision++;
 }
 focusLost(){
  this.held.clear();this.blocked.clear();this.allowedUndo.clear();this.packets.clear();
  if(['recording','playing','preparing','completing'].includes(this.mode)){
   this.needsReplay=true;this.stop('游戏失焦，录制／重放已停止。');}
 }
 nextId(){return this.prefix+(++this.serial).toString(16).padStart(16,'0');}
 changed(){this.documentRevision++;this.revision++;}
 packet(vk,down,source,stamp,context={}){
  // RAWINPUT 与传统消息共享硬件时间；同一消息不重复改写时间轴或撤销决策。
  const id=`${vk}:${down}:${stamp}`,previous=this.packets.get(id);
  if(previous&&!previous.sources.has(source)){
   previous.sources.add(source);return previous.consume;
  }
  const consume=this.key(vk,down,context);
  this.packets.set(id,{sources:new Set([source]),consume});
  if(this.packets.size>64)this.packets.delete(this.packets.keys().next().value);
  return consume;
 }
 blocksPolling(vk){
  if(['playing','preparing','completing'].includes(this.mode)&&(this.policy.time_controls||[]).includes(vk))return true;
  if(this.paused&&this.gameKey(vk))return true;
  if(this.mode==='completing')return vk!==27;
  if(this.blocked.has(vk))return true;
  if(this.mode!=='recording')return false;
  if(this.toolValues().some(k=>k.charCodeAt(0)===vk))return true;
  if(!this.policy.undo.includes(vk)||this.allowedUndo.has(vk))return false;
  let last;for(let i=this.document.steps.length-1;i>=0;i--)if(this.document.steps[i].symbol!=='_'){last=this.document.steps[i];break;}
  return !last||!'UDLRXV123456789'.includes(last.symbol);
 }
 gameKey(vk){return !!this.policy.record[vk]||this.policy.undo.includes(vk)||this.policy.unsupported.includes(vk)||this.toolValues().some(k=>k.charCodeAt(0)===vk);}
 toolValues(){return Object.entries(this.document.tool_keys).filter(([name])=>name!=='solve'||this.policy.solve_enabled!==false).map(([,value])=>value);}
 setPaused(value){
  this.paused=!!value;
  // 持键跨越暂停／恢复也须先松开，避免漏记或重复操作。
  for(const vk of this.held)if(this.gameKey(vk))this.blocked.add(vk);
  this.revision++;
 }
 removeLast(){
  for(let i=this.document.steps.length-1;i>=0;i--){
   const step=this.document.steps[i];if(step.symbol==='_')continue;
   if(step.symbol==='P'){
    this.stop('暂不支持撤销或跨越 P；请手动删除该步并从起点重放。');return false;
   }
   if(!'UDLRXV123456789'.includes(step.symbol)){
    this.stop('旧脚本末尾包含录制撤销尚不支持的动作，请手动编辑并重放。');return false;
   }
   this.document.steps.splice(i,1);
   for(const later of this.document.steps.slice(i))if(later.symbol==='_')later.review=true;
   this.changed();return true;
  }
  return false;
 }
 key(vk,down,context={}){
  if(!down){this.held.delete(vk);this.allowedUndo.delete(vk);const consumed=this.blocked.has(vk);this.blocked.delete(vk);return consumed;}
  const keys=this.document.tool_keys;
  const isTool=this.toolValues().some(k=>k.charCodeAt(0)===vk),isUndo=this.policy.undo.includes(vk);
  if(this.held.has(vk))return this.blocked.has(vk)||(this.mode==='recording'&&isUndo);
  this.held.add(vk);
  if(this.mode==='completing'){
   if(vk===27){this.needsReplay=true;this.stop('已请求停止 P；现场可能已变，请从起点重放。');}
   this.blocked.add(vk);return true;
  }
  if(this.mode==='playing'&&!context.ui&&(this.policy.time_controls||[]).includes(vk)){
   this.blocked.add(vk);return true;
  }
  if(context.ui||context.own||this.mode==='playing')return false;
  if(this.paused&&this.gameKey(vk)){this.blocked.add(vk);return true;}
  if(this.mode==='preparing'&&(context.valid===false||this.policy.record[vk]||isUndo||isTool||this.policy.unsupported.includes(vk))){
   this.needsReplay=true;this.stop('重放准备期间有玩家操作，已取消自动重放。');
   if([16,17,18,91,92].includes(vk))return false;
   this.blocked.add(vk);return true;
  }
  if(this.mode!=='recording'){
   if(this.policy.record[vk]||isUndo||this.policy.unsupported.includes(vk))this.needsReplay=true;
   return false;
  }
  const consume=()=>{this.blocked.add(vk);return true;};
  if(context.valid===false){this.needsReplay=true;this.stop('游戏键位已变化，录制停止，请检查新绑定。');return isTool||isUndo?consume():false;}
  if(context.modifiers){this.needsReplay=true;this.stop('组合键不属于短按录制范围，录制已停止。');return isTool||isUndo?consume():false;}
  if(this.policy.solve_enabled!==false&&vk===keys.solve.charCodeAt(0)){
   if(this.document.steps.length+(this.pending?2:1)>65536){this.stop('操作数量达到上限。');return consume();}
   this.mode='completing';this.reason='正在完成所在格关卡，请稍候。';this.revision++;return consume();
  }
  if(vk===keys.wait.charCodeAt(0)){this.pending=true;this.revision++;return consume();}
  if(vk===keys.correct.charCodeAt(0)){
   if(this.pending){this.pending=false;this.revision++;}else this.removeLast();return consume();
  }
  if(isUndo){if(this.removeLast()){this.allowedUndo.add(vk);return false;}return consume();}
  const symbol=this.policy.record[vk];
  if(symbol){
   if(this.document.steps.length+(this.pending?2:1)>65536){
    this.needsReplay=true;this.stop('操作数量达到上限，录制停止。');return false;
   }
   if(this.pending)this.document.steps.push({id:this.nextId(),symbol:'_',wait_ms:this.document.extra_wait_ms,review:true});
   this.document.steps.push({id:this.nextId(),symbol});this.pending=false;this.changed();return false;
  }
  if(this.policy.unsupported.includes(vk)){
   this.needsReplay=true;this.stop('使用了尚未支持的游戏动作，未记入脚本，现场可能已变。');
  }
  return false;
 }
 solveResult(ok,error=''){
  if(this.mode!=='completing'){this.needsReplay=true;this.stop('P 已停止等待，现场可能已变，请从起点重放。');return;}
  if(!ok){this.needsReplay=true;this.stop('P 未完成：'+error);return;}
  if(this.pending)this.document.steps.push({id:this.nextId(),symbol:'_',wait_ms:this.document.extra_wait_ms,review:true});
  this.document.steps.push({id:this.nextId(),symbol:'P'});this.pending=false;this.changed();
  this.mode='recording';this.reason='P 已执行并记录；实际效果由你判断。';
 }
 status(){return {mode:this.mode,pending:this.pending,needsReplay:this.needsReplay,paused:this.paused,reason:this.reason,
  revision:this.revision,documentRevision:this.documentRevision,count:this.document.steps.length};}
}
if(typeof module!=='undefined')module.exports={PanelRecorder};
