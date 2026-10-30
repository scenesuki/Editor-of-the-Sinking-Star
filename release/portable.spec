# Shared dependencies, three entry executables; no personal data as build input.
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules,copy_metadata

root=Path(SPECPATH).parent
assets=[(str(p),'research') for p in (root/'research').glob('*.js')]
assets += [(str(p),'locales') for p in (root/'locales').glob('*.json')]+[(str(root/'release/release_profile.json'),'.')]
assets += copy_metadata('frida')
a=Analysis([str(root/'release/entry.py')],pathex=[str(root),str(root/'.deps')],
    binaries=[],datas=assets,hiddenimports=collect_submodules('solution_editor')+collect_submodules('research')+['frida','frida._frida'],
    hookspath=[],runtime_hooks=[],excludes=['pytest','unittest.mock','IPython','matplotlib','numpy'],noarchive=False)
pyz=PYZ(a.pure)
editor=EXE(pyz,a.scripts,[],exclude_binaries=True,name='SinkingStarEditor',console=False,upx=False)
backup=EXE(pyz,a.scripts,[],exclude_binaries=True,name='SaveBackup',console=False,upx=False)
worker=EXE(pyz,a.scripts,[],exclude_binaries=True,name='SSEKeyWorker',console=True,upx=False)
bundle=COLLECT(editor,backup,worker,a.binaries,a.datas,strip=False,upx=False,name='SinkingStarEditor-0.1.0-preview')
