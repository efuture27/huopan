# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_submodules

hiddenimports = ['jose', 'jose.jwt', 'passlib', 'passlib.handlers.bcrypt', 'bcrypt', 'multipart', 'email', 'email.mime', 'email.mime.text']
hiddenimports += collect_submodules('uvicorn')
hiddenimports += collect_submodules('sqlalchemy')
hiddenimports += collect_submodules('openpyxl')
hiddenimports += collect_submodules('PIL')
# 回退模式的控制窗口
hiddenimports += ['tkinter', 'tkinter.ttk', 'tkinter.messagebox', 'tkinter.filedialog']

# ---- 桌面端应用窗口：pywebview（Edge WebView2）+ 托盘 pystray + pythonnet(.NET) ----
datas = []
binaries = []
for _pkg in ('webview', 'pystray', 'pythonnet', 'clr_loader'):
    try:
        _d, _b, _h = collect_all(_pkg)
        datas += _d
        binaries += _b
    except Exception:
        pass

hiddenimports += [
    'webview',
    'webview.menu',
    'webview.dom',
    'webview.http',
    'webview.platforms.winforms',
    'webview.platforms.edgechromium',
    'webview.platforms.win32',
    'pystray',
    'pystray._win32',
    'clr',
    'pythonnet',
    'clr_loader',
]

a = Analysis(
    ['launcher.py'],
    pathex=['E:/WorkBuddyData/WorkBuddy/2026-08-23-11-00-35/ai-huopan-demo/backend'],
    binaries=binaries,
    datas=datas + [
        ('E:/WorkBuddyData/WorkBuddy/2026-08-23-11-00-35/ai-huopan-demo/frontend', 'frontend'),
        ('E:/WorkBuddyData/WorkBuddy/2026-08-23-11-00-35/ai-huopan-demo/backend/app_icon.ico', '.'),
    ],
    hiddenimports=hiddenimports,
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
    name='货盘助手',
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
    icon='E:/WorkBuddyData/WorkBuddy/2026-08-23-11-00-35/ai-huopan-demo/backend/app_icon.ico',
    version='E:/WorkBuddyData/WorkBuddy/2026-08-23-11-00-35/ai-huopan-demo/backend/version_info.txt',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='货盘助手',
)
