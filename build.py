#!/usr/bin/env python3
"""
ByteFarm 构建脚本 - 生成 macOS .app 与 .dmg
用法: python build.py  （确保使用正确的 python，如 conda base 下直接运行）
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

def run(cmd, check=True):
    print("  $", " ".join(str(c) for c in cmd))
    r = subprocess.run(cmd)
    if check and r.returncode != 0:
        sys.exit(r.returncode)
    return r.returncode

def main():
    print("=== ByteFarm 构建 ===\n")
    print("Python:", sys.executable)

    # 1. 检查并安装依赖
    try:
        import pygame
        import PyInstaller
        print("依赖已就绪: pygame, PyInstaller\n")
    except ImportError as e:
        print("正在安装依赖...")
        run([sys.executable, "-m", "pip", "install", "-r", "requirements-build.txt"])
        try:
            import pygame
            import PyInstaller
        except ImportError:
            print("\n依赖安装失败，请手动执行:")
            print("  pip install -r requirements-build.txt")
            sys.exit(1)

    # 2. 清理并构建
    print("=== PyInstaller 打包 ===")
    for d in ("build", "dist"):
        p = ROOT / d
        if p.exists():
            shutil.rmtree(p)
    (ROOT / "dist").mkdir(exist_ok=True)

    run([
        sys.executable, "-m", "PyInstaller", "ByteFarm.spec",
        "--clean", "--noconfirm",
    ])

    app_path = ROOT / "dist" / "ByteFarm.app"
    if not app_path.exists():
        print("构建失败: 未找到 ByteFarm.app")
        sys.exit(1)

    # 3. 创建 DMG
    print("\n=== 创建 DMG ===")
    dmg_path = ROOT / "ByteFarm.dmg"
    if dmg_path.exists():
        dmg_path.unlink()

    if shutil.which("create-dmg"):
        run([
            "create-dmg", "--volname", "ByteFarm",
            "--window-pos", "200", "120", "--window-size", "600", "400",
            "--icon-size", "100", "--icon", "ByteFarm.app", "150", "180",
            "--hide-extension", "ByteFarm.app", "--app-drop-link", "450", "180",
            "--no-internet-enable", str(dmg_path), str(ROOT / "dist"),
        ])
    else:
        run(["hdiutil", "create", "-volname", "ByteFarm", "-srcfolder", "dist",
            "-ov", "-format", "UDZO", str(dmg_path)])

    # 4. 复制到 release
    release_dir = ROOT / "release"
    release_dir.mkdir(exist_ok=True)
    shutil.copy(dmg_path, release_dir / "ByteFarm.dmg")
    if (release_dir / "ByteFarm.app").exists():
        shutil.rmtree(release_dir / "ByteFarm.app")
    shutil.copytree(app_path, release_dir / "ByteFarm.app")

    print("\n=== 完成 ===")
    print("  文件位置: release/")
    print("    -", release_dir / "ByteFarm.dmg")
    print("    -", release_dir / "ByteFarm.app")

if __name__ == "__main__":
    main()
