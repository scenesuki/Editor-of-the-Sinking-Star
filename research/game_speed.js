'use strict';
let speed=null,config=null;
function verified(checkWritable=false){
 const module=Process.getModuleByName('sinking_star.exe');
 if(!module.base.equals(ptr(config.base)))throw Error('Game module changed');
 for(const guard of config.guards){
  const bytes=new Uint8Array(ptr(guard.address).readByteArray(guard.hex.length/2));
  const observed=Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');
  if(observed!==guard.hex)throw Error('Game time code changed');
 }
 const at=ptr(config.multiplier);
 // Windows 上此查询会遍历进程内存区域，不能放在 20Hz 状态轮询中。
 // 安装与每次实际写入仍重新核验；只读也继续校验模块和代码。
 if(checkWritable){
  const range=Process.findRangeByAddress(at);
  if(!range||!range.protection.includes('w')||range.protection.includes('x')||at.add(8).compare(range.base.add(range.size))>0)
   throw Error('Game speed is not writable module data');
 }
 return at;
}
rpc.exports={
 install(value,original){
  if(speed)throw Error('Speed controller already installed');config=value;
  verified(true);
  speed=new OwnedSpeed({read:()=>verified().readDouble(),write:v=>verified(true).writeDouble(v)},original);
  return speed.read();
 },
 read(){return speed.read();},
 set(value){return speed.set(value);},
 restore(){return speed.restore();},
 raw(value){return speed.raw(value);}
};
