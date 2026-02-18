# ByteFarm 素材目录

游戏会优先使用本目录下的图片；若不存在则使用内置程序绘制。

- **ByteFarm_icon.png** — 应用图标（用于打包 .app / DMG），可替换为自定义 512×512 或更大 PNG。

## 目录结构

```
assets/
├── ByteFarm_icon.png  # 应用图标（可选）
├── tiles/          # 地形瓦片（与格子尺寸一致时会缩放）
│   ├── grass.png   # 草地（或 grass_0.png, grass_1.png 等变体）
│   └── sand.png    # 沙地（或 sandyland.png）
├── character/      # 角色
│   └── robot.png   # 机器人（正面，正方形为宜）
└── resources/      # 地图上的资源
    ├── grass.png   # 草资源图标
    └── stone.png   # 石头资源图标
```

## 免费可商用素材推荐（CC0 / 无需署名）

### 地形瓦片
- **OpenGameArt - 16x16 tileset (water, grass, sand)**  
  https://opengameart.org/content/16x16-tileset-water-grass-and-sand  
  下载 `voda_pesok_trava_revision_2.png`，裁剪出草地/沙地放入 `tiles/` 并命名为 `grass.png`、`sand.png`。

- **Free CC0 Top Down Tileset (itch.io)**  
  https://rgsdev.itch.io/free-cc0-top-down-tileset-template-pixel-art  
  16x16，多种地形，可选取草地/沙地帧。

- **Kenney - 各类 Top-down 与 Tile 包**  
  https://kenney.nl/assets/tag:tile  
  https://kenney.nl/assets/tag:top-down  
  选一个包下载，将草地、沙地等 PNG 放入 `tiles/`。

### 机器人/角色
- **Kenney - Robot Pack**  
  https://kenney.nl/assets/robot-pack  
  50 个机器人 PNG，选一个正面或俯视的放入 `character/robot.png`。

### 资源图标（草/石头）
- **Kenney - Game Icons**  
  https://kenney.nl/assets/game-icons  
  含多种小图标，可挑与草、石头相近的放入 `resources/`。

- **OpenGameArt - Game Icons**  
  https://opengameart.org/content/game-icons  
  按需挑选并命名 `grass.png`、`stone.png`。

## 使用说明

- 图片格式：PNG（建议带透明通道）。
- 尺寸：任意，游戏会按当前「格子大小」自动缩放。
- 不放置任何文件也可正常运行，将使用程序生成的画风。
