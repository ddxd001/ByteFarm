# -*- mode: python ; coding: utf-8 -*-
"""
ByteFarm PyInstaller 配置 - 优化编译 macOS .app
"""

import sys

block_cipher = None

# 打包数据：assets 目录、默认玩家模板
datas = [
    ("assets", "assets"),
    ("player_strategy.py", "."),
]

# 隐藏导入（动态 import）
hiddenimports = [
    "pygame",
    "pygame.display",
    "pygame.font",
    "pygame.draw",
    "pygame.image",
    "pygame.time",
    "pygame.event",
    "pygame.key",
    "pygame.mouse",
    "pygame.transform",
    "pygame.rect",
    "pygame.surface",
    "pygame.Surface",
    "script_runner",
    "player_runtime",
]

# 排除不需要的模块，减小体积（保留 stdlib 常用模块避免缺失）
excludes = [
    "tkinter",
    "matplotlib",
    "numpy",
    "pandas",
    "PIL",
    "scipy",
    "IPython",
    "jupyter",
    "notebook",
    "pytest",
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ByteFarm",
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,  # 去除符号表，减小体积
    upx=True,    # UPX 压缩（若已安装）
    console=False,  # 无控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=True,
    upx=True,
    upx_exclude=[],
    name="ByteFarm",
)

# macOS .app 包
app = BUNDLE(
    coll,
    name="ByteFarm.app",
    icon="assets/ByteFarm_icon.png",  # PNG 可由 PyInstaller+Pillow 转为 .app 图标
    bundle_identifier="com.bytedev.bytefarm",
    info_plist={
        "CFBundleName": "ByteFarm",
        "CFBundleDisplayName": "ByteFarm",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "ByteFarm - 用 Python 控制你的角色",
    },
)
