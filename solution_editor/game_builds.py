"""按完整 EXE 指纹选择已核对的地址表；运行时不扫描或猜测未知构建。"""
from dataclasses import dataclass
import hashlib
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class GameBuild:
    sha256: str
    label: str
    rvas: Mapping[str,int]
    keymap_pools: tuple[int,...]
    worker_stack_offset: int
    types: Mapping[str,int]
    observer_guards: tuple[int,...]

    def code_config(self,image,base,names):
        result={'context':hex(base+self.rvas['context'])}
        for name in names:
            rva=self.rvas[name];at=image.rva_to_offset(rva)
            result[name]=hex(base+rva);result[name+'_code']=image.data[at:at+32].hex()
        return result

    def save_trace_points(self,image,base):
        result=[]
        for name,options in [('worker_next',dict(complete_item=True)),
                             ('worker_dequeued',dict(stack_offset=self.worker_stack_offset,track_item=True))]:
            rva=self.rvas[name];at=image.rva_to_offset(rva)
            result.append(dict(tag=name,address=hex(base+rva),expected_code=image.data[at:at+16].hex(),**options))
        return result


LEGACY=GameBuild(
    '0ae10a513dae25286fe93d0db4fa8a2df9a473bc07e1734e12bc1ad30166db1c','2026-10-24 / 0ae10a51',
    MappingProxyType(dict(context=0x805288,mode=0x802a28,manager=0xb69600,clock=0x804020,
        save_root=0xb6a438,campaign=0xb69558,save_queue=0xb696e0,transition=0xb6a818,
        frame=0x25d7c0,load=0xd0510,save=0x244010,menu=0x199cf0,
        worker_next=0x175c78,worker_dequeued=0x175cfc,
        progress=0xf4130,entry=0xd92f0,tower=0x35e2a0,world=0x2e1030,
        speed_multiplier=0x802028,speed_native=0x802020,speed_delta=0x804018,
        speed_chain=0x262430,speed_init=0x3558bc,speed_defaults=0x769b70)),
    (0x10d3a80,0x10d3af0),0x128,
    MappingProxyType(dict(settings=0x68b398,state=0x689710,guy=0x6a7710,entry=0x692548)),
    (0x26247e,0x30d200))

UPDATED=GameBuild(
    'd802098b7cb85eadfc733b88d1554042fad950c572e916febea3f669a474a549','2026-10-30 / d802098b',
    MappingProxyType(dict(context=0x8042a0,mode=0x801a28,manager=0xb68618,clock=0x803078,
        save_root=0xb69440,campaign=0xb68468,save_queue=0xb687b0,transition=0xb69818,
        frame=0x25dcc0,load=0xb10b0,save=0x2474a0,menu=0x1a2590,
        worker_next=0x16f55a,worker_dequeued=0x16f5de,
        progress=0xf2aa0,entry=0xd8e20,tower=0x3923b0,world=0x2e0360,
        speed_multiplier=0x801028,speed_native=0x801020,speed_delta=0x803070,
        speed_chain=0x262590,speed_init=0x30eb35,speed_defaults=0x768a80)),
    (0x10d2a80,0x10d2af0),0x1f0,
    MappingProxyType(dict(settings=0x687bb8,state=0x685f30,guy=0x6a5ce0,entry=0x690578)),
    (0x2625de,0x3423a0))

_BUILDS={build.sha256:build for build in (LEGACY,UPDATED)}


def build_for_sha(sha256):
    try:return _BUILDS[sha256]
    except (KeyError,TypeError):raise ValueError('Unsupported game executable: '+str(sha256)) from None


def select_build(data):
    return build_for_sha(hashlib.sha256(data).hexdigest())


def compatible_saved_build(recorded,current):
    # 新版载入函数及存档反射字段已核对；保留工程原始身份，交由原生读档处理旧文件。
    # 不允许旧游戏读取新版生成的工程／检查点，也不放行其他任意构建。
    return recorded==current or (current==UPDATED.sha256 and recorded==LEGACY.sha256)
