"""Build an owned standalone backend and copy the allowlisted portable kit."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import zipfile
ROOT=Path(__file__).resolve().parents[1]
DESKTOP=ROOT/'desktop'

def build():
    work=DESKTOP/'.build';work.mkdir(exist_ok=True)
    args=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--name','claude-check-backend',
          '--distpath',str(DESKTOP/'backend-dist'),'--workpath',str(work/'pyinstaller'),'--specpath',str(work),
          '--paths',str(ROOT/'src')]
    for source in sorted((ROOT/'src').iterdir()):
        if source.suffix in ('.py','.json','.list','.ps1','.txt'):
            args += ['--add-data',str(source)+os.pathsep+'.']
        if source.suffix=='.py': args += ['--hidden-import',source.stem]
    args += ['--hidden-import','yaml',str(DESKTOP/'backend.py')]
    subprocess.run(args,check=True,cwd=ROOT)
    subprocess.run([sys.executable,str(ROOT/'tools/build.py')],check=True,cwd=ROOT)
    kit=DESKTOP/'kit'
    if kit.exists():
        if kit.is_symlink() or not (kit/'PACKAGE-INFO.json').is_file(): raise RuntimeError('Refusing unknown kit directory')
        shutil.rmtree(kit)
    with zipfile.ZipFile(ROOT/'dist/Claude-Setup-Kit.zip') as archive:
        for name in archive.namelist():
            relative=Path(name).relative_to('Claude-Setup-Kit')
            if '..' in relative.parts or relative.is_absolute(): raise RuntimeError('Invalid bundle path')
            target=kit/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(archive.read(name))

if __name__=='__main__':build()
