"""
游戏世界 - 地图、资源生成与管理
"""

import random
from typing import List, Tuple, Optional, Dict
from .api import TileInfo, RESOURCE_GRASS, RESOURCE_STONE, RESOURCE_WOOD, Ground, Entities


TILE_GRASS = "grass"

# 地图尺寸: 正方形，初始 5，最大 20
INITIAL_MAP_SIZE = 5
MAX_MAP_SIZE = 20

# 实体从种植到成熟所需 ticks，期间机器人可离开
ENTITY_MATURE_TICKS = 1000
# Tree 在 Sandyland 上生长更慢（2 倍时间）
TREE_MATURE_TICKS_GRASSLAND = 1000
TREE_MATURE_TICKS_SANDYLAND = 2000


def _random_tile(ground: str = None) -> Dict:
    """生成一个随机格子，仅草地/沙地，不生成实体"""
    if ground is None:
        ground = Ground.Grassland
    return {
        "type": TILE_GRASS,
        "ground": ground,
        "entity": None,
    }


class World:
    """游戏世界 - 正方形地图"""
    
    def __init__(self, width: int = None, height: int = None, size: int = None):
        if size is not None:
            s = min(max(size, INITIAL_MAP_SIZE), MAX_MAP_SIZE)
            self.width = self.height = s
        elif width is not None and height is not None:
            self.width = width
            self.height = height
        else:
            self.width = self.height = INITIAL_MAP_SIZE
        # 地图: grid[y][x] = {"type": str, "resource": str|None, "amount": int}
        self.grid: List[List[Dict]] = []
        self._generate_map()
    
    def _generate_map(self) -> None:
        """生成随机地图"""
        self.grid = []
        for y in range(self.height):
            row = [_random_tile() for _ in range(self.width)]
            self.grid.append(row)
    
    def expand_to(self, target_size: int) -> None:
        """扩展地图到目标边长（右下方向添加行列），保持正方形"""
        target = min(max(target_size, self.width, self.height), MAX_MAP_SIZE)
        if target <= self.width and target <= self.height:
            return
        # 添加列（右侧）
        while self.width < target:
            for row in self.grid:
                row.append(_random_tile())
            self.width += 1
        # 添加行（底部）
        while self.height < target:
            self.grid.append([_random_tile() for _ in range(self.width)])
            self.height += 1
    
    def get_tile(self, x: int, y: int) -> Optional[Dict]:
        """获取指定格子的信息。坐标系：左下角(0,0)，x向右增加，y向上增加"""
        if 0 <= x < self.width and 0 <= y < self.height:
            row = self.height - 1 - y  # y=0 对应底部行
            return self.grid[row][x]
        return None
    
    def get_nearby_tiles(self, center_x: int, center_y: int, radius: int = 2) -> List[TileInfo]:
        """获取指定位置周围的格子信息"""
        tiles = []
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                x, y = center_x + dx, center_y + dy
                t = self.get_tile(x, y)
                if t:
                    tiles.append(TileInfo(
                        x=x, y=y,
                        tile_type=t.get("type", TILE_GRASS),
                        ground=t.get("ground", Ground.Grassland),
                        entity=t.get("entity"),
                        resource_amount=0,
                    ))
        return tiles
    
    def get_current_tile_info(self, x: int, y: int) -> Optional[TileInfo]:
        """获取玩家所在格子的信息"""
        t = self.get_tile(x, y)
        if not t:
            return None
        return TileInfo(
            x=x, y=y,
            tile_type=t.get("type", TILE_GRASS),
            ground=t.get("ground", Ground.Grassland),
            entity=t.get("entity"),
            resource_amount=0,
        )
    
    def collect(self, x: int, y: int, amount: float, current_tick: int = 0) -> Dict[str, int]:
        """从指定格子采集实体，每次仅采集 1 个"""
        t = self.get_tile(x, y)
        if not t:
            return {}
        if not self.is_entity_mature(x, y, current_tick):
            return {}
        entity = t.get("entity")
        amt = t.get("entity_amount", 1)
        if amt <= 0:
            return {}
        if entity == Entities.Grass:
            t["entity_amount"] = amt - 1
            if t["entity_amount"] <= 0:
                t["entity"] = None
                t.pop("entity_planted_at_tick", None)
                t.pop("entity_amount", None)
            return {RESOURCE_GRASS: 1}
        if entity == Entities.Stone:
            t["entity_amount"] = amt - 1
            if t["entity_amount"] <= 0:
                t["entity"] = None
                t.pop("entity_planted_at_tick", None)
                t.pop("entity_amount", None)
            return {RESOURCE_STONE: 1}
        if entity == Entities.Bush:
            t["entity_amount"] = amt - 1
            if t["entity_amount"] <= 0:
                t["entity"] = None
                t.pop("entity_planted_at_tick", None)
                t.pop("entity_amount", None)
            return {RESOURCE_WOOD: 1}
        if entity == Entities.Tree:
            t["entity_amount"] = amt - 1
            if t["entity_amount"] <= 0:
                t["entity"] = None
                t.pop("entity_planted_at_tick", None)
                t.pop("entity_amount", None)
            return {RESOURCE_WOOD: 1}
        return {}
    
    def start_plant(self, x: int, y: int, entity_type: str, tick: int) -> bool:
        """开始种植：在格子添加生长中实体，记录 planted_at_tick"""
        t = self.get_tile(x, y)
        if not t or t.get("entity"):
            return False
        g = t.get("ground", Ground.Grassland)
        if entity_type == Entities.Grass and g != Ground.Grassland:
            return False
        if entity_type == Entities.Stone and g != Ground.Sandyland:
            return False
        if entity_type == Entities.Bush and g != Ground.Grassland:
            return False
        if entity_type == Entities.Tree and g not in (Ground.Grassland, Ground.Sandyland):
            return False
        if entity_type not in (Entities.Grass, Entities.Stone, Entities.Bush, Entities.Tree):
            return False
        t["entity"] = entity_type
        t["entity_planted_at_tick"] = tick
        t["entity_amount"] = 10  # 成熟后可采 10 个
        return True
    
    def get_entity_amount(self, x: int, y: int, current_tick: int) -> int:
        """获取格子实体剩余可采集数量"""
        t = self.get_tile(x, y)
        if not t or not t.get("entity"):
            return 0
        if not self.is_entity_mature(x, y, current_tick):
            return 0
        return max(0, t.get("entity_amount", 1))  # 旧存档无 entity_amount 视为 1
    
    def _get_entity_mature_ticks(self, t: Dict) -> int:
        """获取实体成熟所需 ticks，Tree 在 Sandyland 上更慢"""
        entity = t.get("entity")
        ground = t.get("ground", Ground.Grassland)
        if entity == Entities.Tree and ground == Ground.Sandyland:
            return TREE_MATURE_TICKS_SANDYLAND
        if entity == Entities.Tree:
            return TREE_MATURE_TICKS_GRASSLAND
        return ENTITY_MATURE_TICKS

    def is_entity_mature(self, x: int, y: int, current_tick: int) -> bool:
        """实体是否已成熟可采集"""
        t = self.get_tile(x, y)
        if not t or not t.get("entity"):
            return False
        planted_at = t.get("entity_planted_at_tick")
        if planted_at is None or planted_at == 0:
            return True
        ticks = self._get_entity_mature_ticks(t)
        return current_tick - planted_at >= ticks
    
    def get_entity_growth_progress(self, x: int, y: int, current_tick: int) -> float:
        """实体生长进度 0~1，1 表示成熟"""
        t = self.get_tile(x, y)
        if not t or not t.get("entity"):
            return 0.0
        planted_at = t.get("entity_planted_at_tick")
        if planted_at is None or planted_at == 0:
            return 1.0
        ticks = self._get_entity_mature_ticks(t)
        return min(1.0, (current_tick - planted_at) / ticks)
    
    def till(self, x: int, y: int) -> bool:
        """在指定格子耕地，Grassland <-> Sandyland 互相转化，并移除该格实体"""
        t = self.get_tile(x, y)
        if not t:
            return False
        t["entity"] = None
        t.pop("entity_planted_at_tick", None)
        t.pop("entity_amount", None)  # 地形转化时实体自动被移除
        g = t.get("ground", Ground.Grassland)
        t["ground"] = Ground.Sandyland if g == Ground.Grassland else Ground.Grassland
        return True
    
    def respawn_resources(self) -> None:
        """预留，不再自动生成实体"""
        pass
    
    def to_dict(self) -> Dict:
        """序列化为字典 (用于存档)"""
        return {
            "width": self.width,
            "height": self.height,
            "grid": [
                [
                    {
                        "type": t.get("type", TILE_GRASS),
                        "ground": t.get("ground", Ground.Grassland),
                        "entity": t.get("entity"),
                        "entity_planted_at_tick": t.get("entity_planted_at_tick"),
                        "entity_amount": t.get("entity_amount"),
                    }
                    for t in row
                ]
                for row in self.grid
            ],
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "World":
        """从字典创建世界 (用于读档)，旧存档的 forest/mine 转为 grass"""
        w = cls.__new__(cls)
        w.width = data["width"]
        w.height = data["height"]
        grid = data["grid"]
        for row in grid:
            for t in row:
                if t.get("type") in ("forest", "mine"):
                    t["type"] = TILE_GRASS
                    t.pop("resource", None)
                    t.pop("amount", None)
                    t.pop("max_amount", None)
        w.grid = grid
        return w
