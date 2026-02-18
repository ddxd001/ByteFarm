#!/bin/bash
#
# 创建 GitHub Release 并上传 ByteFarm.dmg
# 用法: ./release_to_github.sh [版本号]
#

set -e
cd "$(dirname "$0")"

VERSION="${1:-v1.0.0}"
DMG="release/ByteFarm.dmg"

if [[ ! -f "$DMG" ]]; then
    echo "错误: 未找到 $DMG，请先运行 python build.py 构建"
    exit 1
fi

echo "创建 Release: $VERSION"
echo "上传: $DMG"
echo ""
# 若未登录，先执行: gh auth login
# 或在环境中设置: export GH_TOKEN=你的个人访问令牌
echo "若未登录，先执行: gh auth login"
echo ""

gh release create "$VERSION" "$DMG" \
    --title "ByteFarm $VERSION" \
    --notes "## 下载安装

- **ByteFarm.dmg** — macOS 安装镜像，双击挂载后将 ByteFarm.app 拖到「应用程序」即可。

## 本版本
- Bush、Tree 实体与 Wood 资源
- macOS 独立应用打包"

echo ""
echo "完成: https://github.com/ddxd001/ByteFarm/releases"
