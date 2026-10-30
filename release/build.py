"""构建便携预览版与自有源码 ZIP；明确白名单，不收集开发资料。"""
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from release.manual_content import render,HASHES
from solution_editor.paths import workspace_root
WORKSPACE=workspace_root(ROOT)

VERSION='0.1.0-preview'
NAME='SinkingStarEditor-'+VERSION


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def inside(path):
    path=path.resolve()
    if WORKSPACE not in path.parents:raise ValueError('Build output is outside workspace')
    return path


def package_zip(folder,destination):
    with zipfile.ZipFile(destination,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in sorted(folder.rglob('*')):
            if path.is_symlink():raise ValueError('Symlink in release payload')
            if path.is_file():z.write(path,folder.name+'/'+path.relative_to(folder).as_posix())


def main():
    build=inside(ROOT/'.build'/('build-'+uuid.uuid4().hex[:12]));build.mkdir(parents=True)
    output=inside(WORKSPACE/'deliverables'/(VERSION+'-'+datetime.now().strftime('%Y%m%d-%H%M%S')))
    output.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ);env['PYTHONPATH']=os.pathsep.join(str(p) for p in (ROOT,ROOT/'.deps',ROOT/'.build-deps'))
    env['PYINSTALLER_CONFIG_DIR']=str(ROOT/'.build/pyinstaller-cache')
    env['PYTHONDONTWRITEBYTECODE']='1';env['PYTHONNOUSERSITE']='1'
    command=[sys.executable,'-B','-m','PyInstaller',str(ROOT/'release/portable.spec'),'--workpath',str(build/'work'),'--distpath',str(build/'dist')]
    log=build/'build.log'
    with log.open('w',encoding='utf-8') as f:subprocess.run(command,cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
    bundle=build/'dist'/NAME
    render(bundle)
    shutil.copytree(ROOT/'release/licenses',bundle/'licenses')
    shutil.copyfile(ROOT/'LICENSE',bundle/'licenses/LICENSE.md')
    shutil.copyfile(ROOT/'release/THIRD_PARTY_NOTICES.md',bundle/'licenses/THIRD_PARTY_NOTICES.md')
    (bundle/'portable.json').write_text('{"format":"sinking-star-editor-portable","version":1}\n',encoding='utf-8')
    import tkinter
    info=dict(name='Sinking Star Editor',version=VERSION,channel='preview',windows='10/11 x64',
              python=sys.version.split()[0],frida='17.24.3',pyinstaller='6.22.3',tcl=tkinter.Tcl().eval('info patchlevel'),
              supported_game_sha256=HASHES,solve_enabled=False,project_migration=False,
              validation_scope='Local packaging, file safety and UI/tool checks. No second-PC or comprehensive game-effect acceptance.')
    (bundle/'metadata').mkdir()
    (bundle/'metadata/BUILD.json').write_text(json.dumps(info,indent=2)+'\n',encoding='utf-8')
    allowed={'SinkingStarEditor.exe','SaveBackup.exe','SSEKeyWorker.exe','_internal','README.md','README.en.md',
             'docs','licenses','portable.json','metadata'}
    if set(p.name for p in bundle.iterdir())!=allowed:raise ValueError('Unexpected or missing binary payload')
    if (bundle/'data').exists():raise ValueError('Release must not contain personal data')
    rows=[dict(path=p.relative_to(bundle).as_posix(),bytes=p.stat().st_size,sha256=digest(p)) for p in sorted(bundle.rglob('*')) if p.is_file()]
    (bundle/'metadata/MANIFEST.sha256').write_text(''.join(r['sha256']+'  '+r['path']+'\n' for r in rows),encoding='utf-8')
    binary=output/(NAME+'-win-x64.zip');package_zip(bundle,binary)
    source=build/(NAME+'-source');source.mkdir()
    files=[]
    for directory in ('solution_editor','research'):
        files += [p for p in (ROOT/directory).iterdir() if p.is_file() and p.suffix in ('.py','.js')]
    files += list((ROOT/'locales').glob('*.json'))
    files += [p for p in (ROOT/'release').rglob('*') if p.is_file() and p.suffix in ('.py','.spec','.json','.txt','.md') and '__pycache__' not in p.parts]
    files += [ROOT/'assets/order-of-the-sinking-star-store.jpg']
    files += [ROOT/'LICENSE',ROOT/'requirements.txt']
    files += list((ROOT/'tests').glob('test_release*.py'))+list((ROOT/'tests').glob('test_backup*.py'))
    for path in files:
        target=source/path.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    shutil.copyfile(ROOT/'release/release_profile.json',source/'release_profile.json')
    shutil.copyfile(bundle/'portable.json',source/'portable.json')
    render(source,source=True)
    shutil.copytree(ROOT/'release/licenses',source/'licenses')
    shutil.copyfile(ROOT/'LICENSE',source/'licenses/LICENSE.md')
    shutil.copyfile(ROOT/'release/THIRD_PARTY_NOTICES.md',source/'licenses/THIRD_PARTY_NOTICES.md')
    (source/'metadata').mkdir()
    source_rows=[dict(path=p.relative_to(source).as_posix(),bytes=p.stat().st_size,sha256=digest(p)) for p in sorted(source.rglob('*')) if p.is_file()]
    (source/'metadata/SOURCE-MANIFEST.json').write_text(json.dumps(source_rows,indent=2)+'\n',encoding='utf-8')
    source_zip=output/(NAME+'-source.zip');package_zip(source,source_zip)
    sums=output/'SHA256SUMS.txt';sums.write_text(''.join(digest(p)+'  '+p.name+'\n' for p in (binary,source_zip)),encoding='utf-8')
    receipt=dict(output=str(output),bundle=str(bundle),build_log=str(log),binary=str(binary),source=str(source_zip),checksums=str(sums))
    (ROOT/'.build/latest-release.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(receipt),flush=True)


if __name__=='__main__':main()
