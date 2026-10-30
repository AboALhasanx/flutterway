# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['gui\\onboarding_app.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('gui/onboarding', 'onboarding'),
        ('assets', 'assets')
    ],
    hiddenimports=[
        'gui.android_sdk',
        'gui.companion_service',
        'gui.paths',
        'gui.vscode_integration',
        'psutil',
        'webview',
        'clr',
        'winreg'
    ],
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
    [],
    exclude_binaries=True,
    name='FlutterWayNative',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='FlutterWayNative',
)
