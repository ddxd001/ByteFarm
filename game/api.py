"""
游戏 API - 内部使用
玩家程序通过注入的 move/collect/measure/till 等直接调用，无需 import 本模块
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Any


class Ground:
    """地面类型，通过 till() 互相转化"""
    Grassland = "grassland"
    Sandyland = "sandyland"


class Entities:
    """实体类型，Grass/Bush 存于 grassland，Stone 存于 sandyland，Tree 两种地形皆可"""
    Grass = "grass"
    Stone = "stone"
    Bush = "bush"
    Tree = "tree"


RESOURCE_GRASS = "grass"
RESOURCE_STONE = "stone"
RESOURCE_WOOD = "wood"
East = "east"
West = "west"
North = "north"
South = "south"


@dataclass
class TileInfo:
    """地图格子信息"""
    x: int
    y: int
    tile_type: str  # "grass"
    ground: str  # Ground.Grassland | Ground.Sandyland
    entity: Optional[str] = None  # Entities.Grass | Stone | Bush | Tree
    resource_amount: int = 0  # 兼容旧存档，现仅采集实体


