'use strict';
// 失焦后必须松开激活键，避免重新切回游戏时意外取得界面输入。
class PanelAccess {
 constructor(){this.active=false;this.rearm=false;this.held=false;}
 update(held,foreground){
  if(!held)this.rearm=false;
  if(!foreground&&held)this.rearm=true;
  const pressed=held&&!this.held;this.held=!!held;
  const active=!foreground?false:pressed&&!this.rearm?!this.active:this.active;
  if(active===this.active)return null;
  this.active=active;return active?'enter':'leave';
 }
}
if(typeof module!=='undefined')module.exports={PanelAccess};
