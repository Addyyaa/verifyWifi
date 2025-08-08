# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['简单启动.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('src/pyserver', 'src/pyserver'),  # 包含Python服务器文件
        ('src/assets', 'src/assets'),      # 包含图标等资源
    ],
    hiddenimports=[
        'flask',
        'flask_cors', 
        'psutil',
        'pystray',
        'win32api','win32con','win32gui',
        'src.pyserver.auth_api',
        'src.pyserver.wifi_proxy'
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
    a.binaries,
    a.datas,
    [],
    name='wifiVerify',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # 改为False，避免显示控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['src\\assets\\wifiVerify.ico'],
)
