from pathlib import Path
from PyInstaller.utils.hooks import collect_all,copy_metadata
root=Path(SPECPATH)
datas=[(str(root/'static'),'static'),(str(root/'assets'),'assets')]
binaries=[];hiddenimports=[]
for package in ('sherpa_onnx','pyJianYingDraft','pymediainfo','imageio_ffmpeg','uiautomation'):
    d,b,h=collect_all(package)
    # FFmpeg is downloaded by the end user from upstream with hash verification.
    # Do not redistribute this GPL executable inside the MIT application bundle.
    d=[v for v in d if not (Path(v[0]).suffix.lower()=='.exe' and 'ffmpeg' in Path(v[0]).name.lower())]
    b=[v for v in b if not (Path(v[0]).suffix.lower()=='.exe' and 'ffmpeg' in Path(v[0]).name.lower())]
    datas+=d;binaries+=b;hiddenimports+=h
for package in ('sherpa-onnx','pyJianYingDraft','pymediainfo','imageio-ffmpeg','httpx'):
    datas+=copy_metadata(package)
a=Analysis([str(root/'desktop.py')],pathex=[str(root)],binaries=binaries,datas=datas,hiddenimports=hiddenimports,
    hookspath=[],hooksconfig={},runtime_hooks=[],excludes=['pytest','pip','setuptools','PyInstaller'],noarchive=False)
# Hooks can re-add the upstream executable; enforce the public bundle policy after analysis.
a.datas=[v for v in a.datas if not ('ffmpeg' in Path(v[0]).name.lower() and Path(v[0]).suffix.lower()=='.exe')]
a.binaries=[v for v in a.binaries if not ('ffmpeg' in Path(v[0]).name.lower() and Path(v[0]).suffix.lower()=='.exe')]
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='口播快剪',debug=False,bootloader_ignore_signals=False,
    strip=False,upx=False,console=False,disable_windowed_traceback=False,
    icon=str(root/'assets/logo.ico'),contents_directory='runtime')
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='口播快剪便携版')
