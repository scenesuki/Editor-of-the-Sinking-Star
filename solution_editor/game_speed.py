"""按已核对时间数据流控制游戏倍率，并保留同进程恢复记录。"""
from contextlib import contextmanager
import json
from pathlib import Path
import struct
import threading


def speed_config(image,build,base):
    r=build.rvas
    def block(name,size):
        at=image.rva_to_offset(r[name]);data=image.data[at:at+size]
        if len(data)!=size:raise ValueError('Incomplete game time code')
        return data
    chain=block('speed_chain',78);init=block('speed_init',22)
    chunks={0:'f20f5905',8:'f20f5905',16:'f20f5ac0',20:'803d',26:'007415803d',
            35:'000f95c00a05',45:'74030f57c0',50:'f30f1105',58:'f30f5ac0',62:'f20f5805',70:'f20f1105'}
    if any(chain[at:at+len(bytes.fromhex(h))]!=bytes.fromhex(h) for at,h in chunks.items()):
        raise ValueError('Unsupported game time dataflow')
    if init[:3]!=bytes.fromhex('0f2805') or init[7:10]!=bytes.fromhex('0f2905') or init[14:18]!=bytes.fromhex('4c8da424'):
        raise ValueError('Unsupported game speed initialization')
    def rip(data,start,at,disp,length):return start+at+length+struct.unpack_from('<i',data,at+disp)[0]
    expected=[(chain,r['speed_chain'],0,4,8,r['speed_multiplier']),
              (chain,r['speed_chain'],8,4,8,r['speed_native']),
              (chain,r['speed_chain'],50,4,8,r['speed_delta']),
              (chain,r['speed_chain'],62,4,8,r['clock']),
              (chain,r['speed_chain'],70,4,8,r['clock']),
              (init,r['speed_init'],0,3,7,r['speed_defaults']),
              (init,r['speed_init'],7,3,7,r['speed_native'])]
    if any(rip(d,s,a,p,n)!=target for d,s,a,p,n,target in expected):
        raise ValueError('Game speed targets changed')
    defaults=image.rva_to_offset(r['speed_defaults'])
    if struct.unpack_from('<dd',image.data,defaults)!=(1.,1.) or r['speed_multiplier']!=r['speed_native']+8:
        raise ValueError('Game speed defaults changed')
    return dict(base=hex(base),multiplier=hex(base+r['speed_multiplier']),native=hex(base+r['speed_native']),
                guards=[dict(address=hex(base+r[name]),hex=data.hex()) for name,data in [('speed_chain',chain),('speed_init',init)]])


class GameSpeed:
    def __init__(self,pid,creation,build,image,base,*,journal_dir=None):
        import frida
        self.lock=threading.RLock();self.depth=0;self.closed=False;self.selected=None
        self.identity=dict(format='ootss-game-speed',version=1,pid=pid,creation=str(creation),game_sha256=build.sha256)
        from .paths import paths
        directory=Path(journal_dir) if journal_dir is not None else paths().logs
        self.journal=directory/f'game-speed-{pid}-{creation}.json'
        config=speed_config(image,build,base)
        research=paths().assets
        source='\n'.join((research/name).read_text(encoding='utf-8') for name in ('panel_speed.js','game_speed.js'))
        self.session=frida.attach(pid)
        try:
            self.script=self.session.create_script(source);self.script.load();self.rpc=self.script.exports_sync
            self.last=self.rpc.install(config,None);self.original=self.last
            if self.journal.exists():
                if self.journal.stat().st_size>4096:raise ValueError('Invalid speed recovery record')
                row=json.loads(self.journal.read_text(encoding='utf-8'))
                if any(row.get(k)!=v for k,v in self.identity.items()):raise ValueError('Speed recovery identity differs')
                values=[row.get(k) for k in ('original','last','previous')]
                if not all(type(v) in (float,int) and 0<=v<=16 for v in values):raise ValueError('Invalid speed recovery values')
                if self.last not in values:raise ValueError('Speed recovery ownership differs; record retained')
                self.rpc.raw(row['original']);self.last=row['original'];self.original=self.last
                self.journal.unlink()
            self.selected=self.last
        except BaseException:
            self.session.detach();raise

    def _write(self,value):
        previous=self.last
        if value==previous:
            if self.rpc.read()!=previous:raise ValueError('Game speed ownership changed')
            return
        self.journal.parent.mkdir(parents=True,exist_ok=True)
        temporary=self.journal.with_suffix('.tmp')
        temporary.write_text(json.dumps(dict(self.identity,original=self.original,last=value,previous=previous)),encoding='utf-8')
        temporary.replace(self.journal)  # 先保全恢复信息，才写游戏内存。
        try:self.rpc.raw(value);self.last=value
        except BaseException:
            try:self.last=self.rpc.read()
            except Exception:pass
            raise

    def read(self):
        with self.lock:
            if self.closed:raise ValueError('Game speed controller is closed')
            value=self.rpc.read()
            if value!=self.last:raise ValueError('Game speed changed outside editor; no memory overwritten')
            return value

    def set(self,value):
        if type(value) not in (int,float) or value not in (0,.25,1,4):raise ValueError('Unsupported speed preset')
        with self.lock:
            if self.closed or self.depth:raise ValueError('存档任务期间不能修改游戏速度。')
            self.read();self._write(value);self.selected=value

    @contextmanager
    def running(self):
        with self.lock:
            if not self.depth:
                self.read();self._write(1.)
            self.depth+=1
        try:yield
        finally:
            with self.lock:
                self.depth-=1
                if not self.depth:self._write(self.selected)

    def close(self):
        with self.lock:
            if self.closed:return
            if self.depth:raise ValueError('游戏存档任务尚未完成。')
            if self.session.is_detached:
                # 进程已结束，恢复材料保留；不把旧倍率套到后续新进程。
                self.closed=True;return
            self.read();self._write(self.original)
            if self.journal.exists():self.journal.unlink()
            self.session.detach();self.closed=True
