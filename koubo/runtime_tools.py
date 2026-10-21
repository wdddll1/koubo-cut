"""Acquire FFmpeg directly from its upstream wheel, not from our GitHub binary.

The public distribution contains no FFmpeg executable. The exact upstream
wheel is hash-verified before its executable is extracted on first media use.
"""
import hashlib
import io
import os
import sys
import threading
import urllib.request
import zipfile
from pathlib import Path

WHEEL_URL = 'https://files.pythonhosted.org/packages/2c/c6/fa760e12a2483469e2bf5058c5faff664acf66cadb4df2ad6205b016a73d/imageio_ffmpeg-0.6.0-py3-none-win_amd64.whl'
WHEEL_SHA256 = '02fa47c83703c37df6bfe4896aab339013f62bf02c5ebf2dce6da56af04ffc0a'
_directory = None
_lock = threading.Lock()


def configure(data_directory):
    global _directory
    _directory = Path(data_directory)/'tools'


def ffmpeg_path():
    import imageio_ffmpeg
    if not getattr(sys,'frozen',False) or _directory is None:
        return imageio_ffmpeg.get_ffmpeg_exe()
    target = _directory/'ffmpeg.exe'
    with _lock:
        if target.is_file():return str(target)
        _directory.mkdir(parents=True,exist_ok=True)
        try:
            with urllib.request.urlopen(WHEEL_URL,timeout=90) as response:
                raw = response.read(40*1024*1024)
            if hashlib.sha256(raw).hexdigest()!=WHEEL_SHA256:
                raise ValueError('FFmpeg upstream download checksum mismatch. No executable was installed.')
            with zipfile.ZipFile(io.BytesIO(raw)) as wheel:
                name = next(n for n in wheel.namelist() if n.startswith('imageio_ffmpeg/binaries/ffmpeg-') and n.endswith('.exe'))
                partial=target.with_suffix('.exe.part');partial.write_bytes(wheel.read(name));os.replace(partial,target)
                license_name=next(n for n in wheel.namelist() if n.endswith('/LICENSE') and '.dist-info/' in n)
                (_directory/'imageio-ffmpeg-LICENSE.txt').write_bytes(wheel.read(license_name))
            (_directory/'FFMPEG-SOURCE.txt').write_text('Downloaded directly from imageio-ffmpeg 0.6.0 upstream PyPI wheel.\n'
                'This FFmpeg 7.1 essentials build is GPLv3+, separate from the MIT Koubo Cut application.\n'
                'Build provider / source and build scripts: https://www.gyan.dev/ffmpeg/builds/\n'
                'Upstream wrapper and build tooling: https://github.com/imageio/imageio-ffmpeg/tree/v0.6.0\n'
                'FFmpeg source: https://ffmpeg.org/releases/ffmpeg-7.1.tar.xz\n'
                'Do not redistribute this downloaded executable without meeting its license obligations.\n',encoding='utf-8')
        except OSError as error:
            raise ValueError('FFmpeg first-use download failed. Connect to the internet and retry, or place your own licensed ffmpeg.exe in data/tools/.') from error
    return str(target)
