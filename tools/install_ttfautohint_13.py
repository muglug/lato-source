#!/usr/bin/env python3
"""Install the pinned macOS engine used by released Lato 2.015.

On other platforms, build ttfautohint 1.3 and set TTFAUTOHINT_13 to its path.
The executable is cached locally, not included in the desktop font package.
"""
import argparse
import hashlib
import io
from pathlib import Path
import platform
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / '.cache/ttfautohint-1.3/ttfautohint'
URL = 'https://downloads.sourceforge.net/project/freetype/ttfautohint/1.3/ttfautohint-1.3-tty-osx.tar.gz'
ARCHIVE_SHA256 = '6b3a74fd8abb6444b4679a8e30fe4c46d09b301fa901ac61639d3af9d2219583'
BINARY_SHA256 = '8af04deecba9212d4582685ac4e3ab8ff4a3f5fc0e11df21d41be62dd765a109'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, help='Use an already downloaded release archive')
    args = parser.parse_args()
    if platform.system() != 'Darwin':
        parser.error('This archive is for macOS; provide a native 1.3 engine with TTFAUTOHINT_13 instead.')
    data = args.archive.read_bytes() if args.archive else urllib.request.urlopen(URL, timeout=60).read()
    if hashlib.sha256(data).hexdigest() != ARCHIVE_SHA256:
        raise ValueError('Release archive checksum mismatch')
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        binary = archive.extractfile('ttfautohint').read()
    if hashlib.sha256(binary).hexdigest() != BINARY_SHA256:
        raise ValueError('Executable checksum mismatch')
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    temporary = DESTINATION.with_suffix('.tmp')
    temporary.write_bytes(binary)
    temporary.chmod(0o755)
    temporary.replace(DESTINATION)
    print(DESTINATION)


if __name__ == '__main__':
    main()
