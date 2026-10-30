'use strict';
// 组合已定位的进度记录与原生刷新流程；失败后不伪装回滚已发生的游戏更新。
function completeOverworld(api){
 let changed=false;
 try{
  api.validate();
  changed=true; // 查找过程也可能创建进度记录；失败不能承诺现场未变。
  const record=api.progress(),flags=api.readFlags(record);
  if(flags&1)return {ok:true,changed:false,alreadyComplete:true};
  changed=true; // 写入异常也按可能已改变处理，禁止自动重试。
  api.writeFlags(record,flags|1);
  api.refreshEntry();api.recount();api.refreshWorld();
  return {ok:true,changed:true,alreadyComplete:false};
 }catch(error){return {ok:false,changed,error:String(error)};}
}
if(typeof module!=='undefined')module.exports={completeOverworld};
