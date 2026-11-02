"""Build the independent native window without Electron or a browser runtime."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import os
import shutil
import subprocess
import sys
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
LITE = ROOT / 'lite'


def build():
    release, work = LITE / 'release', LITE / '.build'
    release.mkdir(exist_ok=True); work.mkdir(exist_ok=True)
    name = 'Clash配置助手'
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir',
               '--windowed', '--name', name, '--distpath', str(release),
               '--workpath', str(work / 'pyinstaller'), '--specpath', str(work),
               '--paths', str(ROOT), '--paths', str(ROOT / 'src')]
    if sys.platform == 'darwin':
        command += ['--osx-bundle-identifier', 'com.lom2729.clashkitlite', '--icon', str(LITE / 'assets/icon.icns')]
    elif sys.platform == 'win32':
        command += ['--icon', str(LITE / 'assets/icon.ico')]
    for source in sorted((ROOT / 'src').iterdir()):
        if source.suffix == '.py':
            command += ['--hidden-import', source.stem]
        elif source.suffix in ('.json', '.list', '.txt', '.ps1'):
            command += ['--add-data', str(source) + os.pathsep + '.']
    command += ['--add-data', str(LITE / 'legal') + os.pathsep + 'legal',
                '--add-data', str(LITE / 'NOTICE.md') + os.pathsep + '.']
    command += ['--hidden-import', 'yaml', '--hidden-import', 'lite.smoke',
                '--hidden-import', 'desktop.backend', str(LITE / 'app.py')]
    subprocess.run(command, cwd=ROOT, check=True)
    if sys.platform == 'darwin':
        bundle = release / (name + '.app')
        executable = bundle / 'Contents/MacOS' / name
        target = 'mac-arm64' if platform.machine() == 'arm64' else 'mac-x64'
    else:
        bundle = release / name
        executable = bundle / (name + '.exe') if sys.platform == 'win32' else bundle / name
        target = 'win-x64' if sys.platform == 'win32' else 'linux-x64'
    receipt = work / ('smoke-' + uuid.uuid4().hex + '.json')
    subprocess.run([str(executable), '--self-test', '--result', str(receipt)],
                   check=True, capture_output=True, timeout=90)
    smoke = json.loads(receipt.read_text(encoding='utf-8'))
    assert smoke['ok'] and smoke['chain_preserved'] and not smoke['proxy_or_system_changes']
    (release / 'smoke-result.json').write_bytes(receipt.read_bytes())
    version = (LITE / 'VERSION').read_text().strip()
    archive = release / f'Clash-Config-Lite-{version}-{target}.zip'
    if sys.platform == 'darwin':
        subprocess.run(['/usr/bin/ditto', '-c', '-k', '--sequesterRsrc', '--keepParent',
                        str(bundle), str(archive)], check=True)
    else:
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for file in sorted(bundle.rglob('*')):
                if file.is_file():
                    z.write(file, file.relative_to(release))
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
    files = [p for p in bundle.rglob('*') if p.is_file() and not p.is_symlink()]
    info = {'version': version, 'target': target, 'archive': archive.name,
            'archive_bytes': archive.stat().st_size,
            'uncompressed_bytes': sum(p.stat().st_size for p in files),
            'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
            'frozen_smoke_exit': 0, 'native_window': True,
            'electron_included': False, 'customer_python_required': False}
    (release / f'build-info-{target}.json').write_text(json.dumps(info, indent=2) + '\n')
    print(json.dumps(info))


if __name__ == '__main__':
    build()
