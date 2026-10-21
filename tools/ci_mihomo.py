"""CI-only opt-in real-core test; not shipped in customer bundles.

Downloads the pinned upstream release, checks a pinned publisher SHA-256, and
runs tests that bind loopback only. No installation or system proxy changes.
"""
import gzip
import hashlib
import io
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

ASSETS = {
    ('Darwin', 'arm64'): ('mihomo-darwin-arm64-v1.19.32.gz', '3312a6780652c622890fd4357c6a853bbf865464fd047ac7b7f52dab8de18652'),
    ('Darwin', 'x86_64'): ('mihomo-darwin-amd64-v1.19.32.gz', 'b7de9fc46af2ca985ecfb302a6362170e04ff2023dee1e82addc54133e669bc9'),
    ('Linux', 'x86_64'): ('mihomo-linux-amd64-v1.19.32.gz', '8451100836c9eda194331c2babfad490b2faf30cebc1a04b0e76fd8ac2d35d10'),
    ('Windows', 'amd64'): ('mihomo-windows-amd64-v1.19.32.zip', '1ac84e795b5b915446e20139677fb6cc013a0778e876e8d4c96f994750b4c4a3'),
}


def main():
    name, digest = ASSETS[(platform.system(), platform.machine().lower())]
    url = 'https://github.com/MetaCubeX/mihomo/releases/download/v1.19.32/' + name
    with urllib.request.urlopen(url, timeout=120) as response:
        data = response.read(80 * 1024 * 1024)
    if hashlib.sha256(data).hexdigest() != digest:
        raise RuntimeError('Upstream release digest mismatch')
    with tempfile.TemporaryDirectory(prefix='ai-loopback-ci-') as directory:
        binary = Path(directory) / ('mihomo.exe' if name.endswith('.zip') else 'mihomo')
        if name.endswith('.zip'):
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                exe = [entry for entry in archive.namelist() if entry.endswith('.exe')]
                if len(exe) != 1:
                    raise RuntimeError('Unexpected upstream archive')
                binary.write_bytes(archive.read(exe[0]))
        else:
            binary.write_bytes(gzip.decompress(data))
        binary.chmod(0o700)
        subprocess.run([str(binary), '-v'], check=True, timeout=10)
        # The expanded per-target UDP/failure checks need a bounded larger budget.
        for pattern, timeout in (('test*loopback.py', 180), ('test_connection_reuse.py', 45)):
            result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests',
                                     '-p', pattern, '-v'],
                                    cwd=Path(__file__).resolve().parents[1],
                                    env=dict(os.environ, MIHOMO_BINARY=str(binary)), timeout=timeout)
            if result.returncode:
                return result.returncode
        return 0


if __name__ == '__main__':
    sys.exit(main())
