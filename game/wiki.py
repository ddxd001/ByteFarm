"""
游戏百科 - 游戏简介、函数、实体、土地等说明
"""

import sys

_MOD = "Cmd" if sys.platform == "darwin" else "Ctrl"

# 百科内容（每行尽量短，便于自动换行）
WIKI_LINES = [
    "【游戏简介】",
    "用 Python 写 run() 控制机器人。",
    "F2执行 F3停止。资源可升级。",
    "",
    "【移动】",
    "move(East/West/North/South)",
    "坐标系：左下(0,0) x右 y上",
    "",
    "【地形】",
    "get_ground() → Grassland 或 Sandyland",
    "till() 草地↔沙地 转化",
    "",
    "【种植】",
    "plant(Entities.Grass) 草地种草",
    "plant(Entities.Stone) 沙地种石",
    "播种后可离开，约1秒成熟。",
    "成熟前 collect 无效。每次10个。",
    "",
    "【实体】",
    "Entities.Grass 草",
    "Entities.Stone 石头",
    "",
    "【采集】",
    "collect() 采1个",
    "can_collect() 是否可采",
    "measure() 剩余数量",
    "",
    "【其他】",
    "get_position() get_map_size()",
    "get_nearby() upgrade()",
    "get_purchasable() print()",
    "",
    f"【升级】{_MOD}+U 打开",
    "",
    f"【编辑器】{_MOD}+E 打开",
    f"{_MOD}+Z 撤销",
    f"{_MOD}+C 复制  {_MOD}+X 剪切",
    f"{_MOD}+V 粘贴  {_MOD}+A 全选",
    "拖标题栏移动 拖右下角调整大小",
]
