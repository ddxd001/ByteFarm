# 发布文件

运行 `./build_dmg.sh` 或 `python build.py` 成功后，本目录会出现：

- **ByteFarm.dmg** — macOS 安装镜像，双击挂载后把 ByteFarm.app 拖到「应用程序」
- **ByteFarm.app** — 应用程序包

若目录为空，在项目根目录执行（确保在 conda base 环境）：

```bash
python build.py
```

会自动安装依赖并构建。或手动：`pip install -r requirements-build.txt` 后运行。
