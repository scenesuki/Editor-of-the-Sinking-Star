"""当前构建原生 Keymap 池的有界只读快照，不以磁盘键位文件冒充实际绑定。"""
from dataclasses import dataclass
import hashlib
import json
import struct
from .game_builds import LEGACY


KEYMAP_POOLS = LEGACY.keymap_pools
ACTION_SYMBOLS = dict(Forward='U', Backward='D', Left='L', Right='R', Activate='X', TakeOrDrop='V',
    ForwardAlt='U', BackwardAlt='D', LeftAlt='L', RightAlt='R',
    SelectWarrior='1', SelectThief='2', SelectWizard='3', SelectPriestess='4',
    SelectBard='5', SelectDruid='6', SelectSailor='7', SelectGemsman='8', SelectTrader='9')
SPECIAL = {8:8, 9:9, 13:13, 27:27, 32:32, 127:46, 128:38, 129:40, 130:37, 131:39,
           139:18, 140:17, 141:16}


def virtual_key(native):
    if 48 <= native <= 57 or 65 <= native <= 90: return native
    return SPECIAL.get(native)


def tool_keys(values):
    if not isinstance(values,dict) or set(values) != {'solve','correct','wait'}:
        raise ValueError('工具键配置不完整。')
    result={}
    for action,key in values.items():
        if not isinstance(key,str) or len(key)!=1 or not key.isascii() or not key.isalnum():
            raise ValueError('工具快捷键须为单个字母或数字。')
        result[action]=key.upper()
    return result


@dataclass
class BindingSnapshot:
    tables: list
    guards: list
    digest: str

    def rows(self):
        for table in self.tables:
            if table['name'] in ('KeyboardDefaults','GamepadDefaults','UserGamepad'): continue
            for row in table['rows']:
                yield table['name'],row

    def conflicts(self,values):
        from .release_profile import active_tools
        keys=active_tools(tool_keys(values));problems=[]
        for action,key in keys.items():
            for other,other_key in keys.items():
                if action<other and key==other_key:problems.append(f'{key} 被两个工具操作共用。')
            matches=sorted({row['action'] for _,row in self.rows() if row['key']==ord(key)})
            if matches:problems.append(f'{key} 与游戏绑定冲突：'+', '.join(matches))
        return problems

    def policy(self,*,panel_key=0xc0):
        recorded={};undo=set();unsupported=set();problems=[];primary={};time_controls=set()
        if any(virtual_key(row['key'])==panel_key or (panel_key==0xc0 and row['key'] in (96,126)) for _,row in self.rows()):
            problems.append('` / ~ 面板激活键与游戏绑定冲突，请先修改游戏绑定。')
        enabled={t['name'] for t in self.tables if t['enabled']}
        for section,row in self.rows():
            vk=virtual_key(row['key'])
            if vk is None:continue
            if row['action'] in ('HoldForFastTime','HoldForSlowTime'):time_controls.add(vk)
            if section not in ('','Gameplay','UserKeyboard'):
                if section in enabled:unsupported.add(vk)
                continue
            action=row['action'];symbol=ACTION_SYMBOLS.get(action)
            if action=='Undo' and not row['modifiers']:undo.add(vk)
            elif symbol and not row['modifiers']:
                if vk in recorded and recorded[vk]!=symbol:problems.append(f'按键 {vk} 对应多个录制动作。')
                recorded[vk]=symbol
                if section in ('','UserKeyboard') or symbol not in primary:primary[symbol]=vk
            else:unsupported.add(vk)
        unsupported.difference_update(recorded);unsupported.difference_update(undo)
        if undo.intersection(recorded):problems.append('撤销键与录制动作共用按键，请先修改游戏绑定。')
        if any(vk in (16,17,18,27) for vk in primary.values()):
            problems.append('录制动作绑定到修饰键或紧急停止键，当前不支持回放。')
        missing=sorted(set('UDLRXV123456789')-set(recorded.values()))
        if missing:problems.append('缺少可识别录制绑定：'+','.join(missing))
        if not undo:problems.append('缺少可识别撤销键。')
        return dict(record=recorded,undo=sorted(undo),unsupported=sorted(unsupported),errors=problems,
                    primary=primary,time_controls=sorted(time_controls),digest=self.digest,guards=self.guards)

    def game_keymap(self):
        from .keymap import GameKeymap
        names={38:'Up',40:'Down',37:'Left',39:'Right',32:'Space',16:'Shift',17:'Control',18:'Alt',
               9:'Tab',13:'Enter',27:'Escape',8:'Backspace',46:'Delete'}
        def name(vk):return chr(vk) if 48<=vk<=57 or 65<=vk<=90 else names[vk]
        fields=dict(U='up',D='down',L='left',R='right',X='activate',V='take')
        values={fields.get(symbol,'select_'+symbol):name(vk) for symbol,vk in self.policy()['primary'].items()}
        extra=dict(CharacterSwitch='switch_character',FriendlyDragon='dragon',Restart='restart',Undo='undo',
                   HoldForFastTime='fast',HoldForSlowTime='slow',SelectTrader='select_9')
        for section,row in self.rows():
            vk=virtual_key(row['key'])
            if section in ('','Gameplay','UserKeyboard') and not row['modifiers'] and vk is not None and row['action'] in extra:
                values[extra[row['action']]]=name(vk)
        return GameKeymap(**values)


def read_bindings(read,pools):
    samples=[];tables=[]
    def take(address,size,*,stride=0):
        if not size:return b''
        if not 0<address<2**64-size or not 0<size<=512*1024:raise ValueError('Invalid keymap read')
        raw=bytes(read(address,size))
        if len(raw)!=size:raise OSError('Incomplete keymap read')
        data=bytearray(raw)
        if stride:
            for offset in range(5,size,stride):data[offset]=0  # 实时 toggled_on 不属于绑定配置。
        samples.append((address,size,bytes(data),stride))
        return bytes(data)
    def text(n,pointer):
        if not 0<=n<=4096:raise ValueError('Invalid keymap string')
        value=take(pointer,n).decode('utf-8')
        if '\0' in value:raise ValueError('Invalid keymap text')
        return value
    def array(header,offset,stride):
        count,data,capacity=struct.unpack_from('<QQQ',header,offset)
        if not 0<=count<=capacity<=8192:raise ValueError('Invalid keymap array')
        return count,take(data,count*stride,stride=40 if stride==40 else 0)
    for root in pools:
        pool=take(root,112);expected=struct.unpack_from('<Q',pool)[0]
        count,blocks,capacity=struct.unpack_from('<QQQ',pool,24)
        if not 0<count<=capacity<=32 or expected>count*16:raise ValueError('Invalid keymap pool')
        pointers=take(blocks,count*8);occupied=0
        for block in struct.unpack('<'+'Q'*count,pointers):
            flags=take(block,16)
            if any(flag not in (0,1) for flag in flags):raise ValueError('Invalid keymap occupancy')
            for index,flag in enumerate(flags):
                if not flag:continue
                occupied+=1;address=block+16+index*120;header=take(address,120)
                name=text(*struct.unpack_from('<QQ',header,96))
                proc_count,procs=array(header,0,32)
                names=[text(*struct.unpack_from('<QQ',procs,i*32)) for i in range(proc_count)]
                row_count,mappings=array(header,40,40);rows=[]
                for i in range(row_count):
                    key,modifiers=struct.unpack_from('<I4xI',mappings,i*40)
                    n,pointer,proc=struct.unpack_from('<QQi',mappings,i*40+16)
                    if proc==-1:action=':'+text(n,pointer)
                    elif 0<=proc<len(names):action=names[proc]
                    else:raise ValueError('Invalid keymap procedure index')
                    rows.append(dict(key=key,modifiers=modifiers,action=action))
                tables.append(dict(name=name,enabled=bool(header[112]),rows=rows))
        if occupied!=expected:raise ValueError('Keymap pool changed')
    for address,size,expected,stride in samples:
        actual=bytearray(read(address,size))
        if stride:
            for offset in range(5,size,stride):actual[offset]=0
        if bytes(actual)!=expected:raise ValueError('Keymap changed during capture')
    guards=[dict(address=hex(a),bytes=b.hex(),stride=stride) for a,_,b,stride in samples]
    digest=hashlib.sha256(json.dumps(guards,sort_keys=True).encode()).hexdigest()
    return BindingSnapshot(tables,guards,digest)
