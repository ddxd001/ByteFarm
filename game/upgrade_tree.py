"""
升级树 - 树状升级结构定义
机器人通过消耗资源升级采集速度等属性，以树状结构展示进度
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from .api import RESOURCE_GRASS, RESOURCE_STONE


@dataclass
class UpgradeNode:
    """升级节点"""
    id: str
    name: str
    cost: Dict[str, int]
    effect_type: str  # "collect_speed", "move_speed"
    effect_value: float
    prerequisites: List[str]  # 父节点 id 列表


# 升级树定义: 根在顶部，子节点在下
# 结构: 基础 -> 采集I~IX/移速I~IX/地图 -> 最高 10 倍速
# 地图: map_1..map_15 链式，每次升级边长+1，初始5最大20
_COLLECT_COSTS = [
    (3, 2), (5, 4), (8, 6), (12, 9), (18, 14), (25, 20), (35, 28), (48, 38), (65, 50),
]
_MOVE_COSTS = [
    (2, 3), (4, 5), (7, 8), (11, 12), (17, 18), (24, 25), (33, 35), (45, 48), (60, 65),
]
UPGRADE_TREE_DEF = [
    UpgradeNode("base", "基础", {}, "", 0, []),
] + [
    UpgradeNode(
        f"collect_{i}",
        f"采集 {['I','II','III','IV','V','VI','VII','VIII','IX'][i-1]}",
        {RESOURCE_GRASS: _COLLECT_COSTS[i-1][0], RESOURCE_STONE: _COLLECT_COSTS[i-1][1]},
        "collect_speed", 1.0,
        [f"collect_{i-1}" if i > 1 else "base"]
    )
    for i in range(1, 10)
] + [
    UpgradeNode(
        f"move_{i}",
        f"移速 {['I','II','III','IV','V','VI','VII','VIII','IX'][i-1]}",
        {RESOURCE_GRASS: _MOVE_COSTS[i-1][0], RESOURCE_STONE: _MOVE_COSTS[i-1][1]},
        "move_speed", 1.0,
        [f"move_{i-1}" if i > 1 else "base"]
    )
    for i in range(1, 10)
] + [
    UpgradeNode(f"map_{i}", f"地图+{i}", {RESOURCE_GRASS: 1 + i, RESOURCE_STONE: 1 + i}, "map_size", 1.0,
                [f"map_{i-1}" if i > 1 else "base"])
    for i in range(1, 16)
]


class UpgradeTree:
    """升级树管理"""
    
    def __init__(self):
        self.nodes = {n.id: n for n in UPGRADE_TREE_DEF}
        self.purchased: set = {"base"}
        self._children: Dict[str, List[str]] = {}
        for n in UPGRADE_TREE_DEF:
            for p in n.prerequisites:
                self._children.setdefault(p, []).append(n.id)
    
    def can_purchase(self, node_id: str, inventory: Dict[str, int]) -> bool:
        """是否可购买（前置已解锁且资源足够）"""
        if node_id in self.purchased:
            return False
        node = self.nodes.get(node_id)
        if not node:
            return False
        for p in node.prerequisites:
            if p not in self.purchased:
                return False
        for res, amount in node.cost.items():
            if inventory.get(res, 0) < amount:
                return False
        return True
    
    def purchase(self, node_id: str, inventory: Dict[str, int]) -> bool:
        """购买升级节点，成功返回 True"""
        if not self.can_purchase(node_id, inventory):
            return False
        node = self.nodes[node_id]
        for res, amount in node.cost.items():
            inventory[res] = inventory.get(res, 0) - amount
        self.purchased.add(node_id)
        return True
    
    def get_node(self, node_id: str) -> Optional[UpgradeNode]:
        return self.nodes.get(node_id)
    
    def get_children(self, node_id: str) -> List[str]:
        return self._children.get(node_id, [])
    
    def get_map_size(self) -> int:
        """当前地图边长 = 5 + 已购地图升级数，最大 20"""
        count = sum(1 for nid in self.purchased if nid.startswith("map_"))
        return min(5 + count, 20)
    
    # 升级分支：每个方向折叠为一条链，显示等级+下次成本
    UPGRADE_CHAINS = {
        "collect": [f"collect_{i}" for i in range(1, 10)],
        "move": [f"move_{i}" for i in range(1, 10)],
        "map": [f"map_{i}" for i in range(1, 16)],
    }
    CHAIN_NAMES = {"collect": "采集", "move": "移速", "map": "地图"}
    
    def get_branch_level(self, branch: str) -> int:
        """分支当前等级（0=未升级）"""
        chain = self.UPGRADE_CHAINS.get(branch, [])
        for i, nid in enumerate(chain):
            if nid not in self.purchased:
                return i
        return len(chain)
    
    def get_next_node(self, branch: str) -> Optional[str]:
        """下一级节点 id，已满则 None"""
        chain = self.UPGRADE_CHAINS.get(branch, [])
        for nid in chain:
            if nid not in self.purchased:
                return nid
        return None
    
    def get_next_cost(self, branch: str) -> Dict[str, int]:
        """下一级所需材料"""
        nid = self.get_next_node(branch)
        if not nid:
            return {}
        node = self.get_node(nid)
        return node.cost if node else {}
    
    def get_branch_display_value(self, branch: str) -> str:
        """用于显示的数值（如地图边长）"""
        if branch == "map":
            return f"{self.get_map_size()}×{self.get_map_size()}"
        return str(self.get_branch_level(branch))
    
    def to_dict(self) -> Dict:
        return {"purchased": list(self.purchased)}
    
    @classmethod
    def from_dict(cls, data: Dict) -> "UpgradeTree":
        t = cls()
        t.purchased = set(data.get("purchased", ["base"]))
        return t


# 新 UI 不再使用 NODE_LAYOUT，改用紧凑卡片
