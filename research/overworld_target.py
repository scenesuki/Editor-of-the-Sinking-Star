"""按当前构建的 ad980／333760 空间索引规则，只读选择大世界所在格入口。

不按距离兜底、不调用可能分配内存的原生查询；调用者核对构建及副本归属。
运行中快照可能被拒绝，执行时必须重新解析，不能持久化地址后直接写入。
"""
from dataclasses import dataclass
import math
import struct
from .completion_probe import read_completion_context
from solution_editor.game_builds import LEGACY


def grid_coordinate(value):
    if not math.isfinite(value) or abs(value)>2**23:
        raise ValueError('Invalid grid coordinate')
    # 原生先用单精度加 0.5，再 floor；不能用 Python round 的偶数舍入。
    f32=lambda x:struct.unpack('<f',struct.pack('<f',x))[0]
    return math.floor(f32(f32(value)+.5))


@dataclass(frozen=True)
class OverworldTarget:
    manager: int
    guy: int
    entry: int
    entity_id: int
    level_name: str
    cell: tuple


def read_overworld_target(read,module_base,*,build=LEGACY):
    samples={}
    def take(address,size):
        if not 0<address<address+size<2**47 or not 0<size<=160000:
            raise ValueError('Invalid target read range')
        data=bytes(read(address,size))
        if len(data)!=size:raise OSError('Incomplete target read')
        if (address,size) in samples and samples[address,size]!=data:
            raise ValueError('Target changed during capture')
        samples[address,size]=data
        return data
    def unpack(at,fmt):return struct.unpack(fmt,take(at,struct.calcsize(fmt)))
    def ptr(at):
        p,=unpack(at,'<Q')
        if not 0<p<2**47 or p%8:raise ValueError('Invalid target pointer')
        return p
    def array(at,max_count=20000):
        n,p=unpack(at,'<QQ')
        if not 0<=n<=max_count:raise ValueError('Invalid target array count')
        if not n:return []
        if not 0<p<2**47 or p%8:raise ValueError('Invalid target array')
        rows=list(unpack(p,'<'+'Q'*n))
        if len(set(rows))!=len(rows) or any(not 0<x<2**47 or x%8 for x in rows):
            raise ValueError('Ambiguous target array')
        return rows
    context=read_completion_context(take,module_base,build=build);manager=context.manager
    if context.special_level!=1:raise ValueError('P 仅支持大世界所在格关卡。')
    if context.transition>=2:raise ValueError('关卡正在切换，请稍后再试。')
    def eligible(at,type_rva,*,entry=False):
        if ptr(at+0xf0)!=manager:raise ValueError('Target belongs to another level')
        if ptr(at+0x108)!=module_base+type_rva:raise ValueError('Unexpected target type')
        if unpack(at+0x118,'<B')[0]:return False
        flags,=unpack(at+0x28,'<Q')
        if flags&0x20000000 or (entry and flags&0x200):return False
        if flags&0x1000000 and not context.misc_flags&4:return False
        if flags&0x2000000 and not flags&0x4000000:return False
        return True
    guys=[at for at in array(manager+0x920) if eligible(at,build.types['guy']) and unpack(at+0x5c,'<H')[0]&4]
    if len(guys)!=1:raise ValueError('需要唯一受控角色，无法确定 P 的目标。')
    guy=guys[0];xyz=unpack(guy,'<fff');grid=ptr(manager+0x50)
    width,height,count=unpack(grid,'<QQQ');origin=unpack(grid+0x1c,'<iii')
    if not 0<width<=100000 or not 0<height<=100000 or count!=width*height:
        raise ValueError('Invalid proximity grid')
    x,y,z=[grid_coordinate(v)-o for v,o in zip(xyz,origin)]
    if not 0<=x<width or not 0<=y<height:raise ValueError('角色不在有效网格内。')
    index=y*width+x;buckets=ptr(grid+0x30);matches=[]
    for at in array(buckets+index*40):
        if ptr(at+0x108)!=module_base+build.types['entry']:continue
        if not eligible(at,build.types['entry'],entry=True):continue
        if unpack(at+0x114,'<i')[0]!=z:continue
        enabled,=unpack(at+0x34c,'<f')
        if not math.isfinite(enabled) or enabled<=0:continue
        matches.append(at)
    if len(matches)!=1:raise ValueError('所在格没有唯一可用关卡入口。')
    entry=matches[0];n,p=unpack(entry+0x330,'<QQ')
    if not 0<n<=1024 or not p:raise ValueError('Invalid level name')
    name=take(p,n).decode('utf8')
    if '\0' in name:raise ValueError('Invalid level name')
    entity_id,=unpack(entry+0x100,'<I')
    for (address,size),expected in samples.items():
        actual=bytes(read(address,size))
        if len(actual)!=size:raise OSError('Incomplete target verification')
        if actual!=expected:raise ValueError('角色或入口在采样期间改变，请重试。')
    return OverworldTarget(manager,guy,entry,entity_id,name,(index,z))
