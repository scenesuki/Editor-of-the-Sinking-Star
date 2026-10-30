'use strict';
// 白色填充、深色轮廓的传统箭头，由游戏交换链绘制，不操作系统光标计数。
function arrowRows(){
 const layers=[{color:'cursorEdge',points:[[0,0],[0,22],[6,17],[10,26],[14,24],[10,16],[19,16]]},
  {color:'cursorFill',points:[[2,4],[2,18],[7,14],[11,23],[12,22],[8,14],[14,14]]}];
 const rows=[];
 for(const layer of layers)for(let y=0;y<26;y++){
  const scan=y+.5,xs=[],p=layer.points;
  for(let i=0;i<p.length;i++){
   const a=p[i],b=p[(i+1)%p.length];
   if((a[1]<=scan&&b[1]>scan)||(b[1]<=scan&&a[1]>scan))xs.push(a[0]+(scan-a[1])*(b[0]-a[0])/(b[1]-a[1]));
  }
  xs.sort((a,b)=>a-b);
  for(let i=0;i+1<xs.length;i+=2)rows.push({x:xs[i],y,w:xs[i+1]-xs[i],h:1,color:layer.color});
 }
 return rows;
}
if(typeof module!=='undefined')module.exports={arrowRows};
