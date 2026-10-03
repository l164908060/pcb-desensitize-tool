# -*- mode: python ; coding: utf-8 -*-
# GUI 版打包配置：Tkinter 原生窗口，无控制台，双击直接运行


a = Analysis(
    ['C:/Users/Administrator/Desktop/新建文件夹 (2)/pcb_gui.py'],
    pathex=['C:/Users/Administrator/Desktop/新建文件夹 (2)'],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='PCB脱敏回填工具',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
