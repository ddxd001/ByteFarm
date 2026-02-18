"""
玩家 - 机器人单位、背包、树状升级
"""

from typing import Dict, Any
from .api import RESOURCE_GRASS, RESOURCE_STONE
from .upgrade_tree import UpgradeTree


class Player:
    """机器人单位"""
    
    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y
        self.inventory: Dict[str, int] = {RESOURCE_GRASS: 10, RESOURCE_STONE: 10}
        self.upgrade_tree = UpgradeTree()
        
        # 采集冷却 (帧数)
        self._collect_cooldown = 0
    
    @property
    def move_speed(self) -> float:
        """移动速度 = 基础 1.0 + 已购升级加成"""
        s = 1.0
        for nid in self.upgrade_tree.purchased:
            node = self.upgrade_tree.get_node(nid)
            if node and node.effect_type == "move_speed":
                s += node.effect_value
        return s
    
    @property
    def collect_speed(self) -> float:
        """采集速度 = 基础 1.0 + 已购升级加成"""
        s = 1.0
        for nid in self.upgrade_tree.purchased:
            node = self.upgrade_tree.get_node(nid)
            if node and node.effect_type == "collect_speed":
                s += node.effect_value
        return s
    
    def purchase_upgrade(self, node_id: str) -> bool:
        """购买升级节点"""
        return self.upgrade_tree.purchase(node_id, self.inventory)
    
    def add_resources(self, resources: Dict[str, int]) -> None:
        """添加资源到背包"""
        for res, amount in resources.items():
            self.inventory[res] = self.inventory.get(res, 0) + amount
    
    def update_cooldown(self) -> None:
        """更新采集冷却"""
        if self._collect_cooldown > 0:
            self._collect_cooldown -= 1
    
    def can_collect(self) -> bool:
        """是否可以进行采集"""
        return self._collect_cooldown <= 0
    
    def start_collect_cooldown(self) -> None:
        """开始采集冷却"""
        self._collect_cooldown = max(1, int(20 / self.collect_speed))
    
    def to_dict(self) -> Dict:
        """序列化为字典 (用于存档)"""
        return {
            "x": self.x,
            "y": self.y,
            "inventory": dict(self.inventory),
            "upgrade_tree": self.upgrade_tree.to_dict(),
            "_collect_cooldown": self._collect_cooldown,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Player":
        """从字典创建玩家 (用于读档)，兼容旧版存档"""
        p = cls(data["x"], data["y"])
        inv = data.get("inventory", {})
        # 旧存档 wood/ore 转为 grass/stone
        p.inventory = {
            RESOURCE_GRASS: inv.get(RESOURCE_GRASS, inv.get("wood", 10)),
            RESOURCE_STONE: inv.get(RESOURCE_STONE, inv.get("ore", 10)),
        }
        if "upgrade_tree" in data:
            p.upgrade_tree = UpgradeTree.from_dict(data["upgrade_tree"])
        else:
            # 旧版存档：根据等级恢复已购节点
            move_lv = data.get("_move_upgrade_level", 0)
            collect_lv = data.get("_collect_upgrade_level", 0)
            ids = ["base"]
            if collect_lv >= 1: ids.append("collect_1")
            if collect_lv >= 2: ids.append("collect_2")
            if collect_lv >= 3: ids.append("collect_3")
            if move_lv >= 1: ids.append("move_1")
            if move_lv >= 2: ids.append("move_2")
            p.upgrade_tree = UpgradeTree.from_dict({"purchased": ids})
        p._collect_cooldown = data.get("_collect_cooldown", 0)
        return p
