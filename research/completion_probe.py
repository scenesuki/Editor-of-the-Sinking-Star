"""已核对构建的完成流程前置只读快照；不等于调用授权或游戏效果验证。

调用者须先核对进程、EXE SHA256 和当前工程副本归属，传入对应构建地址表。
相对字段经原生对象读取、类型分发表和 Jai 字段表核对。禁止在这里调用缺对象
时会创建 Level_State 的原生 getter。最终执行仍须在游戏线程重新检查，不能
用本快照跨线程或跨读档后直接调用完成过程。
"""
from dataclasses import dataclass
import struct
from solution_editor.game_builds import LEGACY


@dataclass(frozen=True)
class CompletionContext:
    manager: int
    settings: int
    level_state: int
    special_level: int
    misc_flags: int
    transition: int


def read_completion_context(read, module_base, *, build=LEGACY):
    if type(module_base) is not int or not 0<module_base<2**47:
        raise ValueError('Invalid verified module base')
    samples={}

    def take(address,fmt):
        size=struct.calcsize(fmt)
        if not 0<address<address+size<2**47:raise ValueError('Invalid game address')
        data=bytes(read(address,size))
        if len(data)!=size:raise OSError('Incomplete completion context read')
        if (address,size) in samples and samples[address,size]!=data:
            raise ValueError('Completion context changed')
        samples[address,size]=data
        return struct.unpack(fmt,data)

    def pointer(address):
        value,=take(address,'<Q')
        if not 0<value<2**47 or value%8:raise ValueError('Invalid game object pointer')
        return value

    manager=pointer(module_base+build.rvas['context']+0x90)

    def single(offset,type_rva):
        count,array=take(manager+offset,'<QQ')
        if count!=1:raise ValueError('Expected exactly one current level object')
        if not 0<array<2**47 or array%8:raise ValueError('Invalid object array')
        obj=pointer(array)
        if pointer(obj+0xf0)!=manager:raise ValueError('Object belongs to another level')
        if pointer(obj+0x108)!=module_base+type_rva:raise ValueError('Unexpected level object type')
        return obj

    settings=single(0xdd0,build.types['settings'])
    state=single(0xa38,build.types['state'])
    special,=take(settings+0x42d,'<B')
    flags,=take(state+0x348,'<I')
    transition,=take(module_base+build.rvas['transition'],'<B')
    for (address,size),data in samples.items():
        check=bytes(read(address,size))
        if len(check)!=size:raise OSError('Incomplete completion context verification')
        if check!=data:raise ValueError('Completion context changed during capture')
    return CompletionContext(manager,settings,state,special,flags,transition)
