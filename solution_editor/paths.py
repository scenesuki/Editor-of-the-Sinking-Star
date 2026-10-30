"""只读资源与用户可写目录分别定位；开发资料不自动迁移。"""
from dataclasses import dataclass
from pathlib import Path
import sys
import tempfile


def workspace_root(source):
    """识别本地 dev/ 布局；发行源码和便携程序仍可独立放置。"""
    source=Path(source)
    return source.parent if source.name=='dev' and (source.parent/'AGENTS.md').is_file() else source


@dataclass(frozen=True)
class Paths:
    app:Path
    resources:Path
    portable:bool
    workspace:Path|None=None

    @property
    def data(self):return self.app/'data' if self.portable else (self.workspace/'data' if self.workspace is not None else self.app)
    @property
    def projects(self):return self.data/'projects'
    @property
    def config(self):return self.data/'config' if self.portable else self.data/'records/config'
    @property
    def logs(self):return self.data/'logs' if self.portable else self.data/'records/runtime'
    @property
    def assets(self):return self.resources/'research'
    @property
    def backups(self):return self.data/'save-backups'

    def prepare(self):
        try:
            for p in (self.data,self.projects,self.config,self.logs):p.mkdir(parents=True,exist_ok=True)
            with tempfile.TemporaryFile(dir=self.data) as f:f.write(b'writable');f.flush()
        except OSError as error:
            raise PermissionError('程序目录不可写，请将整套程序移到可写文件夹后启动。 / Move the whole application to a writable folder.') from error


def paths():
    source=Path(__file__).resolve().parents[1]
    frozen=bool(getattr(sys,'frozen',False))
    app=Path(sys.executable).resolve().parent if frozen else source
    resources=Path(getattr(sys,'_MEIPASS',source))
    workspace=workspace_root(source)
    return Paths(app,resources,frozen or (app/'portable.json').exists(),workspace if workspace!=source else None)
