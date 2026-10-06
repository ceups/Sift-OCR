# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path


a = Analysis(
    ['sift.py'],
    pathex=[],
    binaries=[],
    datas=[('math-models', 'math-models')],
    hiddenimports=['pystray._win32'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
# Tesseract is a separate process, with its own adjacent DLLs. Keep those
# binaries as data instead of scanning/copying them again into Python's DLL
# directory. This also avoids pulling unrelated DLLs from the build PC's PATH.
runtime = Path(SPECPATH) / 'ocr-runtime'
for path in runtime.rglob('*'):
    if not path.is_file():
        continue
    relative = path.relative_to(runtime)
    if ((path.parent == runtime and (path.suffix.lower() == '.dll' or path.name == 'tesseract.exe'))
            or relative.parts[0] == 'doc'
            or relative.as_posix() in ('tessdata/eng.traineddata', 'tessdata/spa.traineddata', 'tessdata/symbols.traineddata')
            or relative.parts[:2] == ('tessdata', 'configs')):
        a.datas.append((str(Path('ocr-runtime') / relative), str(path), 'DATA'))
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Sift',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/sift.ico'],
)
