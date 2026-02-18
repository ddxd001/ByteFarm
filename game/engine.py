"""
游戏引擎 - 主循环、渲染、逻辑更新、存档
"""

import math
import random
import sys
import pygame
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List

from .api import (
    RESOURCE_GRASS, RESOURCE_STONE, Ground, Entities,
    East, West, North, South,
)
from .world import World, TILE_GRASS, INITIAL_MAP_SIZE
from .player import Player
from .save_manager import (
    list_saves, load_game, save_game, delete_save, get_save_folder, get_scratch_folder, get_main_path,
    get_default_main_template, list_py_files, load_all_scripts, save_all_scripts,
    load_config, save_config,
)
from .upgrade_tree import UpgradeTree
from .editor import CodeEditor, EditorPanel
from .terminal import TerminalBuffer, TerminalPanel
from .wiki import WIKI_LINES


# 时间系统：1000 ticks/秒，等级1 采集/移动 各需 500 ticks
TICKS_PER_SECOND = 1000
BASE_MOVE_TICKS = 500
BASE_COLLECT_TICKS = 500
BASE_TILL_TICKS = 200
BASE_PLANT_TICKS = 100   # 播种耗时，成熟需 1000 ticks（可离开）

# macOS 使用 Command，其他平台使用 Ctrl
_MOD_KEY = pygame.KMOD_META if sys.platform == "darwin" else pygame.KMOD_CTRL
_MOD_LABEL = "Cmd" if sys.platform == "darwin" else "Ctrl"

# 颜色
COLORS = {
    "background": (30, 30, 35),
    "grass": (76, 153, 0),
    "player": (255, 200, 50),
    "player_outline": (255, 255, 255),
    "resource_grass": (120, 200, 60),   # 与草地区分
    "resource_stone": (90, 90, 100),    # 与沙地区分
    "sandyland": (210, 180, 140),
    "ui_bg": (50, 50, 55),
    "ui_text": (220, 220, 220),
}


class GameEngine:
    """游戏引擎"""
    
    def __init__(self, width: int = 1024, height: int = 768, tile_size: int = 40):
        pygame.init()
        pygame.key.set_repeat(400, 35)  # 长按重复：400ms 后每 35ms 触发一次
        config = load_config()
        self.fullscreen = config.get("fullscreen", True)
        self.tile_size = tile_size
        self._apply_display_mode(width, height)
        pygame.display.set_caption("ByteFarm - 用 Python 控制你的角色")
        
        self.clock = pygame.time.Clock()
        self.font = self._get_chinese_font(24)
        self.font_large = self._get_chinese_font(36)
        self.font_title = self._get_chinese_font(48)
        
        self.world = World(size=INITIAL_MAP_SIZE)
        self.player = Player(
            self.world.width // 2,
            self.world.height // 2,
        )
        
        self.tick = 0  # 游戏 tick（1 tick = 1ms，1000 tick/s）
        self.current_save_slot: Optional[int] = None
        self._pending_op: Optional[tuple] = None
        self._op_start_tick: int = 0
        self._last_respawn_tick: int = 0
        self.is_running = False
        self.editor = CodeEditor(self.font, line_height=26)
        self.editor_panel = EditorPanel(self.width, self.height)
        self.editor_files: Dict[str, str] = {"main.py": get_default_main_template()}
        self.editor_current_file: str = "main.py"
        self.editor.set_text(self.editor_files["main.py"])
        self.editor_rename_file: Optional[str] = None  # 正在重命名的文件名
        self.editor_rename_input: str = ""  # 重命名输入（不含 .py 后缀）
        self._last_tab_click: Optional[Tuple[float, str]] = None  # (时间戳, 文件名) 用于双击检测
        self.show_editor = True
        self.terminal_buffer = TerminalBuffer()
        self.terminal_panel = TerminalPanel(self.font, self.width, self.height)
        self.terminal_panel.set_buffer(self.terminal_buffer)
        self.show_terminal = True
        self.show_wiki = False
        self._wiki_scroll = 0
        self._runtime = None  # PlayerRuntime
        self._plant_particles: List[Dict] = []
    
    def _apply_display_mode(self, width: int = 1024, height: int = 768) -> None:
        """应用显示模式。全屏=独占全屏，窗口=可调节大小"""
        pygame.display.quit()
        pygame.display.init()
        if self.fullscreen:
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.screen = pygame.display.set_mode((width, height), pygame.RESIZABLE)
        self.width = self.screen.get_width()
        self.height = self.screen.get_height()
        pygame.display.set_caption("ByteFarm - 用 Python 控制你的角色")
        if hasattr(self, "editor_panel"):
            self.editor_panel.clamp_to_screen(self.width, self.height)
        if hasattr(self, "terminal_panel"):
            self.terminal_panel.clamp_to_screen(self.width, self.height)
    
    @staticmethod
    def _get_chinese_font(size: int):
        """获取支持中文的字体，优先使用系统字体文件路径"""
        from pathlib import Path
        font_paths = [
            # macOS 系统中文字体
            "/System/Library/Fonts/Hiragino Sans GB.ttc",
            "/System/Library/Fonts/STHeiti Medium.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/System/Library/Fonts/Supplemental/Songti.ttc",
            # Windows
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simhei.ttf",
            # Linux
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        ]
        for path in font_paths:
            if Path(path).exists():
                try:
                    return pygame.font.Font(path, size)
                except Exception:
                    pass
        # 回退: SysFont
        try:
            return pygame.font.SysFont("PingFang SC,Microsoft YaHei,SimHei,WenQuanYi Micro Hei", size)
        except Exception:
            return pygame.font.Font(None, size)
    
    def start_execution(self) -> bool:
        """启动玩家程序（顺序执行，每帧处理一个操作）"""
        self.stop_execution()
        self._sync_editor_to_files()
        if self.current_save_slot:
            self.save_to_slot(self.current_save_slot)
        # 将所有文件写入目录，确保 main.py 可 import 其他模块
        if self.current_save_slot:
            folder = get_save_folder(self.current_save_slot)
        else:
            folder = get_scratch_folder()
        folder.mkdir(parents=True, exist_ok=True)
        for fname, content in self.editor_files.items():
            if fname.endswith(".py"):
                (folder / fname).write_text(content, encoding="utf-8")
        script_dir = str(folder)
        try:
            from script_runner import load_player_script
            from player_runtime import PlayerRuntime
            mod = load_player_script(script_dir)
            if not mod:
                return False
            rt = PlayerRuntime()
            rt.set_measure_fn(lambda: self._measure_at_player())
            rt.set_upgrade_fn(self._do_upgrade)
            rt.set_get_purchasable_fn(lambda: self._get_purchasable_ids())
            rt.set_get_position_fn(lambda: (self.player.x, self.player.y))
            rt.set_get_nearby_fn(lambda: self._get_nearby_tuples())
            rt.set_get_map_size_fn(lambda: (self.world.width, self.world.height))
            rt.set_get_ground_fn(lambda: self._get_ground_at_player())
            rt.set_output_buffer(self.terminal_buffer)
            self.terminal_buffer.append_line(">>> 程序启动")
            rt.start(mod)
            self._runtime = rt
            self.is_running = True
            return True
        except Exception as e:
            import traceback
            self.terminal_buffer.append_line("")
            self.terminal_buffer.write(traceback.format_exc())
        return False
    
    def _do_upgrade(self, node_id: str) -> bool:
        """执行升级，成功后若为地图扩建则扩展世界"""
        ok = self.player.purchase_upgrade(node_id)
        if ok and node_id.startswith("map_"):
            target = self.player.upgrade_tree.get_map_size()
            self.world.expand_to(target)
        return ok
    
    def _measure_at_player(self) -> int:
        """可采集量：返回成熟实体剩余数量，每次 collect 采 1"""
        return self.world.get_entity_amount(self.player.x, self.player.y, self.tick)
    
    def _get_purchasable_ids(self) -> List[str]:
        ids = []
        for nid in self.player.upgrade_tree.nodes:
            if nid != "base" and self.player.upgrade_tree.can_purchase(nid, self.player.inventory):
                ids.append(nid)
        return ids
    
    def _get_nearby_tuples(self) -> List[tuple]:
        """返回 (x, y, resource_amount) 列表"""
        tiles = self.world.get_nearby_tiles(self.player.x, self.player.y, radius=2)
        return [(t.x, t.y, t.resource_amount) for t in tiles if t.resource_amount > 0]
    
    def _get_ground_at_player(self) -> str:
        """返回玩家所在格子的地面类型"""
        t = self.world.get_tile(self.player.x, self.player.y)
        if t:
            return t.get("ground", Ground.Grassland)
        return Ground.Grassland
    
    def stop_execution(self) -> None:
        """停止玩家程序"""
        self._pending_op = None
        if self._runtime:
            self._runtime.stop()
            self._runtime = None
        self.is_running = False
    
    def get_save_data(self) -> Dict[str, Any]:
        """获取当前游戏状态 (用于存档)"""
        p = self.editor_panel
        t = self.terminal_panel
        return {
            "version": 1,
            "coord_y_up": True,  # 坐标系：左下角(0,0)，y向上
            "frame": self.tick,  # 兼容旧存档字段名
            "player": self.player.to_dict(),
            "world": self.world.to_dict(),
            "panels": {
                "editor": {"x": p.x, "y": p.y, "w": p.w, "h": p.h, "minimized": p.minimized},
                "terminal": {"x": t.x, "y": t.y, "w": t.w, "h": t.h, "minimized": t.minimized},
            },
        }
    
    def load_save_data(self, data: Dict[str, Any]) -> bool:
        """从存档数据加载游戏"""
        try:
            if not isinstance(data.get("world"), dict) or not isinstance(data.get("player"), dict):
                print("加载存档失败: 缺少 world 或 player 数据")
                return False
            self.world = World.from_dict(data["world"])
            self.player = Player.from_dict(data["player"])
            # 旧存档 (version 1) 使用 y 向下坐标系，需转换为 y 向上
            if data.get("version", 1) == 1 and "coord_y_up" not in data:
                self.player.y = self.world.height - 1 - self.player.y
            self.tick = data.get("frame", data.get("tick", 0))
            self._last_respawn_tick = self.tick  # 避免加载后立即 respawn
            self.world.expand_to(self.player.upgrade_tree.get_map_size())
            # 恢复编辑器、终端面板位置
            panels = data.get("panels", {})
            if panels:
                ep = panels.get("editor", {})
                if ep:
                    self.editor_panel.x = ep.get("x", self.editor_panel.x)
                    self.editor_panel.y = ep.get("y", self.editor_panel.y)
                    self.editor_panel.w = max(EditorPanel.MIN_W, ep.get("w", self.editor_panel.w))
                    self.editor_panel.h = max(EditorPanel.MIN_H, ep.get("h", self.editor_panel.h))
                    self.editor_panel.minimized = ep.get("minimized", False)
                tp = panels.get("terminal", {})
                if tp:
                    self.terminal_panel.x = tp.get("x", self.terminal_panel.x)
                    self.terminal_panel.y = tp.get("y", self.terminal_panel.y)
                    self.terminal_panel.w = max(TerminalPanel.MIN_W, tp.get("w", self.terminal_panel.w))
                    self.terminal_panel.h = max(TerminalPanel.MIN_H, tp.get("h", self.terminal_panel.h))
                    self.terminal_panel.minimized = tp.get("minimized", False)
                self.editor_panel.clamp_to_screen(self.width, self.height)
                self.terminal_panel.clamp_to_screen(self.width, self.height)
            return True
        except (KeyError, TypeError, IndexError) as e:
            print(f"加载存档失败: {e}")
            return False
    
    def save_to_slot(self, slot_id: int, name: Optional[str] = None) -> bool:
        """保存到指定槽位（state.json + 所有 .py 文件）"""
        self._sync_editor_to_files()
        data = self.get_save_data()
        main_content = self.editor_files.get("main.py", "")
        extra = {k: v for k, v in self.editor_files.items() if k != "main.py"}
        if save_game(data, slot_id, main_content, name, extra_scripts=extra):
            self.current_save_slot = slot_id
            return True
        return False
    
    def _get_current_script_content(self) -> str:
        """获取当前脚本内容（用于保存到 main.py）"""
        return self.editor.get_text()
    
    def _sync_editor_to_files(self) -> None:
        """将当前编辑器的内容同步到 editor_files"""
        self.editor_files[self.editor_current_file] = self.editor.get_text()

    def _is_editor_modifying_key(self, event: pygame.event.Event) -> bool:
        """判断按键是否会修改编辑器内容（运行中编辑时需先停止程序）"""
        if event.type != pygame.KEYDOWN:
            return False
        mods = pygame.key.get_mods()
        mod_key = pygame.KMOD_META if sys.platform == "darwin" else pygame.KMOD_CTRL
        ctrl = mods & mod_key
        shift = mods & pygame.KMOD_SHIFT
        if event.unicode and event.unicode.isprintable():
            return True
        if event.key in (pygame.K_BACKSPACE, pygame.K_DELETE, pygame.K_RETURN):
            return True
        if event.key == pygame.K_TAB:
            return True
        if ctrl and event.key in (pygame.K_x, pygame.K_v, pygame.K_z):
            return True
        return False
    
    def _switch_editor_file(self, filename: str) -> None:
        """切换编辑的文件"""
        if filename == self.editor_current_file:
            return
        self._sync_editor_to_files()
        self.editor_current_file = filename
        self.editor.set_text(self.editor_files.get(filename, ""))
    
    def _create_new_editor_file(self) -> str:
        """创建新的 Python 文件，返回文件名"""
        existing = set(self.editor_files.keys())
        for i in range(1, 100):
            name = f"new_{i}.py"
            if name not in existing:
                self.editor_files[name] = ""
                self._switch_editor_file(name)
                return name
        return ""
    
    def _delete_editor_file(self, filename: str) -> bool:
        """删除文件，main.py 不可删除。返回是否成功"""
        if filename == "main.py":
            return False
        if filename not in self.editor_files:
            return False
        self._finish_rename_editor_file(apply=False)
        self.editor_files.pop(filename)
        if self.editor_current_file == filename:
            self._switch_editor_file("main.py")
        return True
    
    def _start_rename_editor_file(self, filename: str) -> None:
        """进入重命名模式"""
        self.editor_rename_file = filename
        base = filename[:-3] if filename.endswith(".py") else filename
        self.editor_rename_input = base
    
    def _finish_rename_editor_file(self, apply: bool) -> None:
        """结束重命名模式，apply=True 时应用新名字"""
        old_name = self.editor_rename_file
        self.editor_rename_file = None
        if not apply or not old_name:
            return
        new_base = self.editor_rename_input.strip()
        if not new_base:
            return
        new_name = new_base if new_base.endswith(".py") else new_base + ".py"
        if new_name == old_name:
            return
        # 校验：文件名仅允许字母数字下划线短横线
        base = new_name[:-3] if new_name.endswith(".py") else new_name
        if not base or not all(c.isalnum() or c in "_.-" for c in base):
            return
        if new_name in self.editor_files:
            return
        content = self.editor_files.pop(old_name)
        self.editor_files[new_name] = content
        if self.editor_current_file == old_name:
            self.editor_current_file = new_name
    
    def _handle_rename_key(self, event: pygame.event.Event) -> bool:
        """处理重命名模式的键盘输入，返回 True 表示已消费"""
        if not self.editor_rename_file:
            return False
        if event.key == pygame.K_RETURN:
            self._finish_rename_editor_file(apply=True)
            return True
        if event.key == pygame.K_ESCAPE:
            self._finish_rename_editor_file(apply=False)
            return True
        if event.key == pygame.K_BACKSPACE:
            self.editor_rename_input = self.editor_rename_input[:-1]
            return True
        if event.key == pygame.K_DELETE:
            # 简化：无光标，Delete 同 Backspace
            self.editor_rename_input = self.editor_rename_input[:-1]
            return True
        if event.unicode and event.unicode.isprintable() and "/\\:*?\"<>|" not in event.unicode:
            self.editor_rename_input += event.unicode
            return True
        return True  # 其他键在重命名模式下也消费
    
    def load_from_slot(self, slot_id: int) -> bool:
        """从指定槽位加载（state.json + 所有 .py 文件到编辑器）"""
        data = load_game(slot_id)
        if data and self.load_save_data(data):
            self.current_save_slot = slot_id
            self.editor_files = load_all_scripts(slot_id)
            if not self.editor_files:
                self.editor_files = {"main.py": get_default_main_template()}
            self.editor_current_file = "main.py"
            self.editor.set_text(self.editor_files.get("main.py", ""))
            self.stop_execution()
            return True
        return False

    def start_new_game(self, slot_id: int) -> None:
        """开始新游戏：重置世界、玩家、编辑器等为初始状态"""
        self.stop_execution()
        self.world = World(size=INITIAL_MAP_SIZE)
        self.player = Player(
            self.world.width // 2,
            self.world.height // 2,
        )
        self.tick = 0
        self._pending_op = None
        self._last_respawn_tick = 0
        default_main = get_default_main_template()
        self.editor_files = {"main.py": default_main}
        self.editor_current_file = "main.py"
        self.editor.set_text(default_main)
        self.editor_rename_file = None
        self.terminal_buffer.clear()
        self.current_save_slot = slot_id
        folder = get_save_folder(slot_id)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "main.py").write_text(default_main, encoding="utf-8")
    
    def _op_duration_ticks(self, op: tuple) -> int:
        """操作所需 tick 数：移动/采集 500/base_speed，耕地 200"""
        if op[0] == "move":
            return max(1, int(BASE_MOVE_TICKS / self.player.move_speed))
        if op[0] == "collect":
            return max(1, int(BASE_COLLECT_TICKS / self.player.collect_speed))
        if op[0] == "till":
            return BASE_TILL_TICKS
        if op[0] == "plant":
            return BASE_PLANT_TICKS
        return 0
    
    def _apply_op(self, op: tuple) -> None:
        """应用并完成一个操作"""
        if op[0] == "move" and len(op) >= 2:
            d = op[1]
            dx, dy = 0, 0
            if d == East: dx = 1
            elif d == West: dx = -1
            elif d == North: dy = 1   # 坐标系 y 向上增加
            elif d == South: dy = -1
            new_x = self.player.x + dx
            new_y = self.player.y + dy
            if self.world.get_tile(new_x, new_y) is not None:
                self.player.x = new_x
                self.player.y = new_y
        elif op[0] == "collect":
            resources = self.world.collect(self.player.x, self.player.y, 1, self.tick)
            if resources:
                self.player.add_resources(resources)
        elif op[0] == "till":
            self.world.till(self.player.x, self.player.y)
        elif op[0] == "plant" and len(op) >= 2:
            pass  # 实体已在 start_plant 时添加，成熟由时间决定
        self._runtime.op_done()
    
    def _process_runtime_op(self) -> None:
        """按 tick 处理玩家操作：每操作耗时 500/速度 ticks"""
        if not self._runtime:
            return
        # run() 自然结束后，runtime 的 is_running 会变为 False，同步到引擎
        if not self._runtime.is_running():
            self.is_running = False
            return
        if not self.is_running:
            return
        if self._pending_op is not None:
            dur = self._op_duration_ticks(self._pending_op)
            if self.tick - self._op_start_tick >= dur:
                self._apply_op(self._pending_op)
                self._pending_op = None
            return
        op = self._runtime.poll_op()
        if op is None:
            return
        if op[0] == "_stop":
            return
        if op[0] == "plant" and len(op) >= 2:
            if self.world.start_plant(self.player.x, self.player.y, op[1], self.tick):
                self._spawn_plant_particles(self.player.x, self.player.y, op[1])
        self._pending_op = op
        self._op_start_tick = self.tick
    
    def _render_tiles(self, camera_x: int, camera_y: int) -> None:
        """渲染地图格子"""
        ts = self.tile_size
        for y in range(self.world.height):
            for x in range(self.world.width):
                tile = self.world.get_tile(x, y)
                if not tile:
                    continue
                
                px = x * ts - camera_x
                py = (self.world.height - 1 - y) * ts - camera_y  # y 向上增加
                
                # 只渲染视野内的
                if px < -ts or py < -ts or px > self.width + ts or py > self.height + ts:
                    continue
                
                ground = tile.get("ground", Ground.Grassland)
                if ground == Ground.Sandyland:
                    color = COLORS["sandyland"]
                else:
                    color = COLORS["grass"]
                
                rect = pygame.Rect(px, py, ts - 1, ts - 1)
                pygame.draw.rect(self.screen, color, rect)
                
                center = (px + ts // 2, py + ts // 2)
                entity = tile.get("entity")
                if entity:
                    progress = self.world.get_entity_growth_progress(x, y, self.tick)
                    ent_color = COLORS["resource_grass"] if entity == Entities.Grass else COLORS["resource_stone"]
                    # 从小到大：半径 1~5，与地面颜色区分
                    radius = max(1, int(1 + progress * 4))
                    pygame.draw.circle(self.screen, ent_color, center, radius)
    
    def _render_player(self, camera_x: int, camera_y: int) -> None:
        """渲染玩家；采集时显示顺时针旋转变色弧（12点起，一圈=采集完成）"""
        ts = self.tile_size
        px = self.player.x * ts - camera_x + ts // 2
        py = (self.world.height - 1 - self.player.y) * ts - camera_y + ts // 2
        r = ts // 2 - 4
        # 使用半透明绘制机器人
        d = (r + 2) * 2 + 4
        surf = pygame.Surface((d, d), pygame.SRCALPHA)
        center = (d // 2, d // 2)
        surf.fill((0, 0, 0, 0))
        pygame.draw.circle(surf, (*COLORS["player_outline"], 180), center, r + 2)
        pygame.draw.circle(surf, (*COLORS["player"], 180), center, r)
        self.screen.blit(surf, (px - d // 2, py - d // 2))
        # 采集中/种植中：机器人的圆上叠加顺时针旋转弧（12点起，一圈=完成）
        is_collecting = self._pending_op and self._pending_op[0] == "collect"
        is_planting = self._pending_op and self._pending_op[0] == "plant"
        if is_collecting or is_planting:
            dur = self._op_duration_ticks(self._pending_op)
            progress = min(1.0, (self.tick - self._op_start_tick) / max(1, dur))
            tile = self.world.get_tile(self.player.x, self.player.y)
            entity = tile.get("entity") if tile else None
            if is_planting and len(self._pending_op) >= 2:
                entity = self._pending_op[1]
            if entity == Entities.Grass:
                arc_color = COLORS["resource_grass"]
            else:
                arc_color = COLORS["resource_stone"]
            rect = pygame.Rect(px - r, py - r, r * 2, r * 2)
            # pygame 弧线：0=3点，-pi/2=12点；顺时针即角度递减
            start = -math.pi / 2  # 12 点
            sweep = progress * 2 * math.pi
            end = start - sweep  # 顺时针
            if progress > 0.001:
                pygame.draw.arc(self.screen, arc_color, rect, end, start, max(3, r // 3))

    def _spawn_plant_particles(self, tx: int, ty: int, entity_type: str) -> None:
        """种植成功时在格子周围生成粒子效果"""
        color = COLORS["resource_grass"] if entity_type == Entities.Grass else COLORS["resource_stone"]
        cx, cy = tx + 0.5, ty + 0.5
        for _ in range(14):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(0.03, 0.08)
            self._plant_particles.append({
                "x": cx, "y": cy,
                "vx": math.cos(angle) * speed, "vy": math.sin(angle) * speed,
                "life": 0, "max_life": 35,
                "color": color, "size": random.randint(2, 4),
            })

    def _update_plant_particles(self) -> None:
        """更新粒子状态"""
        keep = []
        for p in self._plant_particles:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["life"] += 1
            if p["life"] < p["max_life"]:
                keep.append(p)
        self._plant_particles = keep

    def _render_plant_particles(self, camera_x: int, camera_y: int) -> None:
        """渲染种植粒子"""
        ts = self.tile_size
        h = self.world.height
        for p in self._plant_particles:
            t = p["life"] / p["max_life"]
            alpha = int(255 * (1 - t))
            sx = int(p["x"] * ts - camera_x)
            sy = int((h - 1 - p["y"]) * ts - camera_y + ts // 2)
            size = max(1, p["size"] - int(t * 2))
            if size > 0 and 0 <= alpha <= 255:
                surf = pygame.Surface((size * 2 + 2, size * 2 + 2), pygame.SRCALPHA)
                pygame.draw.circle(surf, (*p["color"], alpha), (size + 1, size + 1), size)
                self.screen.blit(surf, (sx - size - 1, sy - size - 1))
    
    def _render_ui(self) -> None:
        """渲染 UI"""
        # 左下角: 背包和属性
        ui_y = self.height - 100
        pygame.draw.rect(self.screen, COLORS["ui_bg"], (10, ui_y - 10, 300, 90))
        
        run_status = "运行中" if self.is_running else "已停止"
        save_hint = f" [F5]保存 [F9]读档" + (f" 槽位{self.current_save_slot}" if self.current_save_slot else "")
        texts = [
            f"草: {self.player.inventory.get(RESOURCE_GRASS, 0)}  石头: {self.player.inventory.get(RESOURCE_STONE, 0)}",
            f"移动: {self.player.move_speed:.1f}  采集: {self.player.collect_speed:.1f}",
            f"程序: {run_status}  [Esc]菜单 [F1]百科 [{_MOD_LABEL}+E]编辑器 [{_MOD_LABEL}+T]终端 [F2]执行 [F3]停止 [{_MOD_LABEL}+U]升级树{save_hint}",
        ]
        for i, text in enumerate(texts):
            surf = self.font.render(text, True, COLORS["ui_text"])
            self.screen.blit(surf, (20, ui_y + i * 22))
        
        if self.is_running:
            surf = self.font.render("程序执行中 - 机器人由你的代码控制", True, (150, 255, 150))
        else:
            surf = self.font.render("程序已停止 - 在编辑器中编写代码后按 F2 执行", True, (255, 200, 100))
        self.screen.blit(surf, (20, ui_y - 25))
    
    def _get_upgrade_panel_rect(self) -> Tuple[int, int, int, int]:
        """返回升级面板 (px, py, w, h)"""
        panel_w, panel_h = 440, 200
        px = (self.width - panel_w) // 2
        py = (self.height - panel_h) // 2
        return px, py, panel_w, panel_h
    
    def _get_upgrade_card_rect(self, branch_index: int) -> pygame.Rect:
        """返回某个分支卡片的矩形"""
        px, py, pw, ph = self._get_upgrade_panel_rect()
        margin = 16
        card_w = (pw - 4 * margin) // 3
        card_h = ph - 100
        x = px + margin + branch_index * (card_w + margin)
        y = py + 75
        return pygame.Rect(x, y, card_w, card_h)
    
    def _handle_upgrade_panel_click(self, mx: int, my: int) -> bool:
        """处理升级面板内的点击，返回是否处理"""
        px, py, pw, ph = self._get_upgrade_panel_rect()
        if not (px <= mx < px + pw and py <= my < py + ph):
            return False
        for i, branch in enumerate(["collect", "move", "map"]):
            rect = self._get_upgrade_card_rect(i)
            if rect.collidepoint(mx, my):
                nid = self.player.upgrade_tree.get_next_node(branch)
                if nid and self._do_upgrade(nid):
                    return True
        return True  # 点在面板内即算处理
    
    def _render_upgrade_tree_panel(self) -> None:
        """渲染紧凑升级卡片：采集/移速/地图 三列，点击升级"""
        px, py, panel_w, panel_h = self._get_upgrade_panel_rect()
        
        # 背景
        surf = pygame.Surface((panel_w, panel_h))
        surf.set_alpha(248)
        surf.fill((28, 32, 40))
        self.screen.blit(surf, (px, py))
        pygame.draw.rect(self.screen, (70, 80, 95), (px, py, panel_w, panel_h), 2)
        pygame.draw.rect(self.screen, (90, 100, 120), (px, py, panel_w, panel_h), 1)
        
        # 标题
        title = self.font_large.render("升级", True, (255, 230, 140))
        self.screen.blit(title, (px + (panel_w - title.get_width()) // 2, py + 12))
        hint = self.font.render("按 U 关闭  |  点击卡片升级", True, (150, 155, 165))
        self.screen.blit(hint, (px + (panel_w - hint.get_width()) // 2, py + 48))
        
        ut = self.player.upgrade_tree
        margin = 16
        card_w = (panel_w - 4 * margin) // 3
        card_h = panel_h - 100
        
        for i, branch in enumerate(["collect", "move", "map"]):
            rx = px + margin + i * (card_w + margin)
            ry = py + 75
            rect = pygame.Rect(rx, ry, card_w, card_h)
            
            next_node = ut.get_next_node(branch)
            can_buy = next_node and ut.can_purchase(next_node, self.player.inventory)
            level = ut.get_branch_level(branch)
            max_level = len(ut.UPGRADE_CHAINS[branch])
            is_maxed = level >= max_level
            
            # 卡片背景
            bg = (45, 52, 62) if not can_buy and not is_maxed else (50, 58, 70)
            if can_buy:
                bg = (55, 65, 50)
            pygame.draw.rect(self.screen, bg, rect)
            border_c = (90, 200, 110) if can_buy else (70, 75, 85)
            pygame.draw.rect(self.screen, border_c, rect, 2)
            
            # 分支名
            name = ut.CHAIN_NAMES[branch]
            name_t = self.font.render(name, True, (220, 225, 235))
            self.screen.blit(name_t, (rx + (card_w - name_t.get_width()) // 2, ry + 12))
            
            # 等级/数值
            if branch == "map":
                val_txt = f"{ut.get_map_size()}×{ut.get_map_size()}"
            else:
                val_txt = f"等级 {level}"
            val_t = self.font.render(val_txt, True, (255, 245, 180))
            self.screen.blit(val_t, (rx + (card_w - val_t.get_width()) // 2, ry + 40))
            
            # 下次所需
            cost = ut.get_next_cost(branch)
            if cost:
                cost_txt = "下次: " + " ".join(f"{v}{'草' if k == 'grass' else '石'}" for k, v in cost.items())
                cost_color = (120, 220, 120) if can_buy else (120, 120, 130)
                ct = self.font.render(cost_txt, True, cost_color)
                self.screen.blit(ct, (rx + (card_w - ct.get_width()) // 2, ry + card_h - 28))
            else:
                max_t = self.font.render("已满", True, (130, 140, 150))
                self.screen.blit(max_t, (rx + (card_w - max_t.get_width()) // 2, ry + card_h - 28))
    
    def _render_editor_panel(self) -> None:
        """渲染可拖动、可调整大小、可最小化的编辑器面板"""
        p = self.editor_panel
        p.clamp_to_screen(self.width, self.height)
        
        r = p.rect()
        # 面板背景
        pygame.draw.rect(self.screen, (28, 30, 36), r)
        pygame.draw.rect(self.screen, (70, 75, 90), r, 2)
        
        # 标题栏
        tr = p.title_rect()
        pygame.draw.rect(self.screen, (45, 48, 55), tr)
        pygame.draw.line(self.screen, (60, 65, 80), (r.x, r.y + tr.h), (r.x + r.w, r.y + tr.h))
        title = self.font.render("编辑器", True, (220, 225, 235))
        self.screen.blit(title, (r.x + 10, r.y + 4))
        
        if p.minimized:
            # 最小化时只显示展开按钮
            exp_rect = pygame.Rect(r.x + r.w - 50, r.y + 6, 40, 20)
            pygame.draw.rect(self.screen, (70, 90, 120), exp_rect)
            exp_txt = self.font.render("展开", True, (255, 255, 255))
            self.screen.blit(exp_txt, (exp_rect.x + (exp_rect.w - exp_txt.get_width()) // 2, exp_rect.y + 2))
            return
        
        # 最小化按钮
        min_rect = pygame.Rect(r.x + r.w - 50, r.y + 6, 40, 20)
        pygame.draw.rect(self.screen, (60, 70, 90), min_rect)
        min_txt = self.font.render("-", True, (255, 255, 255))
        self.screen.blit(min_txt, (min_rect.x + (min_rect.w - min_txt.get_width()) // 2, min_rect.y + 2))
        
        # 标签栏 + 编辑区域
        content = p.content_rect()
        tab_h = 26
        btn_h = 32
        tab_bar_rect = pygame.Rect(content.x, content.y, content.w, tab_h)
        code_rect = pygame.Rect(content.x, content.y + tab_h, content.w, content.h - tab_h - btn_h - 12)
        
        # 渲染标签栏
        tab_x = content.x + 4
        tab_pad = 8
        close_btn_w = 18  # 删除按钮宽度（仅非 main.py 显示）
        for fname in self.editor_files:
            is_renaming = fname == self.editor_rename_file
            display_name = (self.editor_rename_input + "|") if is_renaming else fname
            tw = max(60, self.font.size(display_name)[0] + tab_pad * 2)
            can_delete = fname != "main.py"
            if can_delete:
                tw += close_btn_w
            tab_rect = pygame.Rect(tab_x, content.y, tw, tab_h - 2)
            is_current = fname == self.editor_current_file
            color = (55, 60, 72) if is_current else (40, 43, 50)
            pygame.draw.rect(self.screen, color, tab_rect)
            if is_current:
                pygame.draw.line(self.screen, (70, 75, 90), (tab_rect.x, tab_rect.bottom), (tab_rect.right, tab_rect.bottom), 2)
            if is_renaming:
                # 重命名输入框（带光标闪烁）
                pygame.draw.rect(self.screen, (35, 38, 45), pygame.Rect(tab_x + 2, content.y + 2, tw - (close_btn_w if can_delete else 0) - 4, tab_h - 6))
                blink = (pygame.time.get_ticks() // 500) % 2
                input_text = self.editor_rename_input + ("|" if blink else "")
                t_color = (220, 225, 235)
                self.screen.blit(self.font.render(input_text, True, t_color), (tab_x + tab_pad, content.y + 4))
            else:
                t_color = (220, 225, 235) if is_current else (150, 155, 165)
                self.screen.blit(self.font.render(fname, True, t_color), (tab_x + tab_pad, content.y + 4))
                if can_delete:
                    close_rect = pygame.Rect(tab_rect.right - close_btn_w - 2, content.y + 4, close_btn_w, tab_h - 10)
                    close_color = (180, 100, 100) if close_rect.collidepoint(pygame.mouse.get_pos()) else (120, 125, 135)
                    close_txt = self.font.render("×", True, close_color)
                    self.screen.blit(close_txt, (close_rect.x + (close_rect.w - close_txt.get_width()) // 2, close_rect.y - 1))
            tab_x += tw + 2
        # "+" 按钮
        plus_size = tab_h - 6
        plus_rect = pygame.Rect(tab_x, content.y + 3, plus_size, plus_size)
        pygame.draw.rect(self.screen, (50, 90, 60), plus_rect)
        plus_txt = self.font.render("+", True, (255, 255, 255))
        self.screen.blit(plus_txt, (plus_rect.x + (plus_rect.w - plus_txt.get_width()) // 2, plus_rect.y))
        editor_colors = {"bg": (25, 28, 32), "border": (55, 60, 70), "text": (220, 220, 220)}
        visible_lines = max(1, (code_rect.h - 8 - self.editor.SCROLLBAR_W) // self.editor.line_height)
        self.editor.set_project_files(self.editor_files, self.editor_current_file)
        self.editor.render(self.screen, code_rect, editor_colors, visible_lines, highlight=True)
        
        btn_y = content.y + content.h - btn_h - 4
        btn1 = pygame.Rect(content.x + 10, btn_y, 100, btn_h - 4)
        btn2 = pygame.Rect(content.x + 120, btn_y, 100, btn_h - 4)
        pygame.draw.rect(self.screen, (50, 130, 70), btn1)
        pygame.draw.rect(self.screen, (130, 50, 50), btn2)
        t1 = self.font.render("开始执行", True, (255, 255, 255))
        t2 = self.font.render("停止执行", True, (255, 255, 255))
        self.screen.blit(t1, (btn1.x + (btn1.w - t1.get_width()) // 2, btn1.y + 6))
        self.screen.blit(t2, (btn2.x + (btn2.w - t2.get_width()) // 2, btn2.y + 6))
        
        # 调整大小手柄
        hr = p.resize_handle_rect()
        pygame.draw.polygon(self.screen, (90, 95, 105), [
            (hr.x + 4, hr.y + hr.h - 4), (hr.x + hr.w - 4, hr.y + 4),
            (hr.x + hr.w - 4, hr.y + hr.h - 4)
        ])
    
    def _terminal_handle_events(self, event: pygame.event.Event) -> bool:
        """处理终端面板事件，返回 True 表示已消费"""
        if not self.show_terminal:
            return False
        p = self.terminal_panel
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if p.handle_mousedown(event.pos, self.width, self.height):
                return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if p.is_dragging():
                p.handle_mouseup()
                p.clamp_to_screen(self.width, self.height)
                return True
        if event.type == pygame.MOUSEMOTION:
            if p.is_dragging():
                p.handle_mousemotion(event.pos)
                p.clamp_to_screen(self.width, self.height)
                return True
        if event.type == pygame.MOUSEWHEEL and not p.minimized:
            if p.rect().collidepoint(pygame.mouse.get_pos()):
                p.scroll(event.y)
                return True
        return False
    
    def _editor_handle_events(self, event: pygame.event.Event) -> bool:
        """处理编辑器相关事件（点击、滚轮、拖拽），返回 True 表示已消费"""
        if not self.show_editor:
            return False
        p = self.editor_panel
        
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if p.handle_mousedown(event.pos, self.width, self.height):
                if not p.is_dragging() and not p.minimized:
                    content = p.content_rect()
                    tab_h, btn_h = 26, 32
                    btn_y = content.y + content.h - btn_h - 4
                    btn1 = pygame.Rect(content.x + 10, btn_y, 100, btn_h - 4)
                    btn2 = pygame.Rect(content.x + 120, btn_y, 100, btn_h - 4)
                    code_rect = pygame.Rect(content.x, content.y + tab_h, content.w, content.h - tab_h - btn_h - 12)
                    # 标签栏点击
                    tab_x = content.x + 4
                    tab_pad, plus_size, close_btn_w = 8, tab_h - 6, 18
                    for fname in self.editor_files:
                        display_name = (self.editor_rename_input + "|") if fname == self.editor_rename_file else fname
                        tw = max(60, self.font.size(display_name)[0] + tab_pad * 2)
                        can_delete = fname != "main.py"
                        if can_delete:
                            tw += close_btn_w
                        tab_rect = pygame.Rect(tab_x, content.y, tw, tab_h - 2)
                        if tab_rect.collidepoint(event.pos):
                            if can_delete:
                                close_rect = pygame.Rect(tab_rect.right - close_btn_w - 2, content.y + 4, close_btn_w, tab_h - 10)
                                if close_rect.collidepoint(event.pos):
                                    self._finish_rename_editor_file(apply=False)
                                    self._delete_editor_file(fname)
                                    return True
                            if self.editor_rename_file and fname != self.editor_rename_file:
                                self._finish_rename_editor_file(apply=False)
                            now = pygame.time.get_ticks()
                            if self._last_tab_click and self._last_tab_click[1] == fname and (now - self._last_tab_click[0]) < 400:
                                self._start_rename_editor_file(fname)
                                self._last_tab_click = None
                            else:
                                self._last_tab_click = (now, fname)
                                self._switch_editor_file(fname)
                            return True
                        tab_x += tw + 2
                    plus_rect = pygame.Rect(tab_x, content.y + 3, plus_size, plus_size)
                    if plus_rect.collidepoint(event.pos):
                        self._finish_rename_editor_file(apply=False)
                        self._create_new_editor_file()
                        return True
                    if btn1.collidepoint(event.pos):
                        self._finish_rename_editor_file(apply=False)
                        self.start_execution()
                    elif btn2.collidepoint(event.pos):
                        self._finish_rename_editor_file(apply=False)
                        self.stop_execution()
                    elif code_rect.collidepoint(event.pos):
                        self._finish_rename_editor_file(apply=False)
                        self.editor.handle_click(event.pos, code_rect)
                return True
        
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if p.is_dragging():
                p.handle_mouseup()
                return True
            return False
        
        if event.type == pygame.MOUSEMOTION:
            if p.is_dragging():
                p.handle_mousemotion(event.pos)
                return True
        
        if event.type == pygame.MOUSEWHEEL and not p.minimized:
            content = p.content_rect()
            tab_h, btn_h = 26, 32
            code_rect = pygame.Rect(content.x, content.y + tab_h, content.w, content.h - tab_h - btn_h - 12)
            if code_rect.collidepoint(pygame.mouse.get_pos()):
                vis_lines = max(1, (code_rect.h - 8 - self.editor.SCROLLBAR_W) // self.editor.line_height)
                vis_width = content.w - self.editor.LINE_NUM_WIDTH - self.editor.SCROLLBAR_W - 12
                self.editor.scroll(event.y, event.x, vis_lines, vis_width)
                return True
        
        return False
    
    def _get_game_menu_button_rects(self) -> Dict[str, pygame.Rect]:
        """游戏菜单按钮矩形"""
        panel_w, panel_h = 320, 488
        px = (self.width - panel_w) // 2
        py = (self.height - panel_h) // 2
        btn_w, btn_h = 220, 44
        bx = px + (panel_w - btn_w) // 2
        labels = ["保存游戏", "加载存档", "删除存档", "游戏设置", "游戏百科", "返回主菜单", "退出游戏"]
        rects = {}
        for i, label in enumerate(labels):
            rects[label] = pygame.Rect(bx, py + 90 + i * 48, btn_w, btn_h)
        rects["_panel"] = pygame.Rect(px, py, panel_w, panel_h)
        return rects
    
    def _handle_game_menu_click(self, mx: int, my: int) -> Optional[str]:
        """处理游戏菜单点击，返回 'save'|'load'|'settings'|'wiki'|'main_menu'|'quit' 或 None"""
        rects = self._get_game_menu_button_rects()
        if not rects["_panel"].collidepoint(mx, my):
            return None
        mapping = {
            "保存游戏": "save", "加载存档": "load", "删除存档": "delete",
            "游戏设置": "settings", "游戏百科": "wiki", "返回主菜单": "main_menu", "退出游戏": "quit"
        }
        for label, r in rects.items():
            if label.startswith("_"):
                continue
            if r.collidepoint(mx, my):
                return mapping.get(label)
        return None
    
    def _wrap_wiki_line(self, line: str, max_w: int) -> List[str]:
        """按像素宽度自动换行"""
        if not line or max_w <= 0:
            return [line] if line else [""]
        result = []
        while line:
            best = 0
            for i in range(1, len(line) + 1):
                if self.font.size(line[:i])[0] <= max_w:
                    best = i
                else:
                    break
            if best == 0:
                best = 1
            result.append(line[:best])
            line = line[best:].lstrip() if best < len(line) else ""
        return result
    
    def _get_wiki_display_lines(self, content_w: int) -> List[tuple]:
        """获取百科显示行 [(文本, 是否标题), ...]"""
        lines = []
        for raw in WIKI_LINES:
            is_title = raw.startswith("【")
            for part in self._wrap_wiki_line(raw, content_w):
                if part:
                    lines.append((part, is_title))
                else:
                    lines.append(("", False))
        return lines
    
    def _render_wiki_panel(self) -> None:
        """渲染百科面板"""
        pad, sb_w = 20, 14
        panel_w = min(480, self.width - 60)
        panel_h = min(450, self.height - 60)
        content_w = panel_w - pad * 2 - sb_w
        
        px = (self.width - panel_w) // 2
        py = (self.height - panel_h) // 2
        
        overlay = pygame.Surface((self.width, self.height))
        overlay.set_alpha(180)
        overlay.fill((15, 18, 22))
        self.screen.blit(overlay, (0, 0))
        
        pygame.draw.rect(self.screen, (32, 35, 42), (px, py, panel_w, panel_h))
        pygame.draw.rect(self.screen, (70, 80, 95), (px, py, panel_w, panel_h), 2)
        
        title = self.font.render("游戏百科  F1/Esc 关闭", True, (255, 230, 140))
        self.screen.blit(title, (px + (panel_w - title.get_width()) // 2, py + 12))
        
        content_y = py + 44
        content_h = panel_h - 52
        line_h = 20
        vis_lines = content_h // line_h
        
        display_lines = self._get_wiki_display_lines(content_w)
        max_scroll = max(0, len(display_lines) - vis_lines)
        self._wiki_scroll = max(0, min(self._wiki_scroll, max_scroll))
        
        for i in range(vis_lines):
            idx = self._wiki_scroll + i
            if idx >= len(display_lines):
                break
            text, is_title = display_lines[idx]
            color = (255, 230, 150) if is_title else (200, 210, 220)
            surf = self.font.render(text, True, color)
            self.screen.blit(surf, (px + pad, content_y + i * line_h))
        
        if len(display_lines) > vis_lines:
            sb_h = content_h
            thumb_h = max(20, int(sb_h * vis_lines / len(display_lines)))
            thumb_y = content_y + int((sb_h - thumb_h) * self._wiki_scroll / max(1, max_scroll))
            sb_x = px + panel_w - pad - sb_w
            pygame.draw.rect(self.screen, (50, 52, 58), (sb_x, content_y, sb_w, sb_h))
            pygame.draw.rect(self.screen, (90, 95, 105), (sb_x, thumb_y, sb_w, thumb_h))
    
    def _wiki_handle_events(self, event: pygame.event.Event) -> bool:
        """处理百科面板滚轮"""
        if not self.show_wiki:
            return False
        pad, sb_w = 20, 14
        panel_w = min(480, self.width - 60)
        panel_h = min(450, self.height - 60)
        content_h = panel_h - 52
        line_h = 20
        content_w = panel_w - pad * 2 - sb_w
        display_lines = self._get_wiki_display_lines(content_w)
        vis_lines = content_h // line_h
        max_scroll = max(0, len(display_lines) - vis_lines)
        px = (self.width - panel_w) // 2
        py = (self.height - panel_h) // 2
        if event.type == pygame.MOUSEWHEEL:
            if px <= pygame.mouse.get_pos()[0] <= px + panel_w and py <= pygame.mouse.get_pos()[1] <= py + panel_h:
                self._wiki_scroll = max(0, min(self._wiki_scroll - event.y, max_scroll))
                return True
        return False
    
    def _render_game_menu(self) -> None:
        """渲染游戏菜单（保存/加载/设置/退出）"""
        rects = self._get_game_menu_button_rects()
        panel = rects["_panel"]
        overlay = pygame.Surface((self.width, self.height))
        overlay.set_alpha(200)
        overlay.fill((15, 18, 22))
        self.screen.blit(overlay, (0, 0))
        pygame.draw.rect(self.screen, (35, 40, 48), panel)
        pygame.draw.rect(self.screen, (70, 80, 95), panel, 2)
        title = self.font_large.render("游戏菜单", True, (255, 230, 140))
        self.screen.blit(title, (panel.x + (panel.w - title.get_width()) // 2, panel.y + 25))
        hint = self.font.render("按 Esc 关闭", True, (130, 135, 140))
        self.screen.blit(hint, (panel.x + (panel.w - hint.get_width()) // 2, panel.y + 58))
        for label, r in rects.items():
            if label.startswith("_"):
                continue
            mx, my = pygame.mouse.get_pos()
            hover = r.collidepoint(mx, my)
            color = (60, 120, 80) if hover else (50, 55, 65)
            pygame.draw.rect(self.screen, color, r)
            pygame.draw.rect(self.screen, (90, 100, 115), r, 2)
            txt = self.font.render(label, True, (255, 255, 255))
            self.screen.blit(txt, (r.x + (r.w - txt.get_width()) // 2, r.y + (r.h - txt.get_height()) // 2 - 2))
    
    def _get_settings_button_rects(self) -> Dict:
        """设置面板按钮矩形"""
        panel_w, panel_h = 300, 300
        px = (self.width - panel_w) // 2
        py = (self.height - panel_h) // 2
        btn_w, btn_h = 90, 36
        main_w = 110
        gap = 12
        start_x = px + (panel_w - btn_w - gap - main_w) // 2
        back = pygame.Rect(start_x, py + panel_h - 50, btn_w, btn_h)
        main_menu_btn = pygame.Rect(start_x + btn_w + gap, py + panel_h - 50, main_w, btn_h)
        tile_opts = [(32, "小 (32)"), (40, "中 (40)"), (48, "大 (48)")]
        tw = 80
        tile_rects = []
        start_x = px + (panel_w - len(tile_opts) * (tw + 12)) // 2
        for i, (val, _) in enumerate(tile_opts):
            tile_rects.append((val, pygame.Rect(start_x + i * (tw + 12), py + 100, tw, 36)))
        # 全屏/窗口 两个选项
        fs_w = 100
        fs_x = px + (panel_w - fs_w * 2 - 20) // 2
        fullscreen_rect = pygame.Rect(fs_x, py + 155, fs_w, 36)
        windowed_rect = pygame.Rect(fs_x + fs_w + 20, py + 155, fs_w, 36)
        return {
            "back": back, "main_menu_btn": main_menu_btn, "tile_sizes": tile_rects,
            "fullscreen_btn": fullscreen_rect, "windowed_btn": windowed_rect,
            "_panel": pygame.Rect(px, py, panel_w, panel_h),
        }
    
    def _render_settings_panel(self) -> None:
        """渲染游戏设置面板"""
        rects = self._get_settings_button_rects()
        panel = rects["_panel"]
        overlay = pygame.Surface((self.width, self.height))
        overlay.set_alpha(200)
        overlay.fill((15, 18, 22))
        self.screen.blit(overlay, (0, 0))
        pygame.draw.rect(self.screen, (35, 40, 48), panel)
        pygame.draw.rect(self.screen, (70, 80, 95), panel, 2)
        title = self.font_large.render("游戏设置", True, (255, 230, 140))
        self.screen.blit(title, (panel.x + (panel.w - title.get_width()) // 2, panel.y + 20))
        lbl = self.font.render("格子大小:", True, (200, 205, 210))
        self.screen.blit(lbl, (panel.x + 20, panel.y + 65))
        for val, r in rects["tile_sizes"]:
            mx, my = pygame.mouse.get_pos()
            hover = r.collidepoint(mx, my)
            sel = self.tile_size == val
            color = (70, 90, 60) if sel else ((55, 65, 75) if hover else (45, 50, 58))
            pygame.draw.rect(self.screen, color, r)
            pygame.draw.rect(self.screen, (85, 95, 110), r, 2)
            txt = self.font.render("小" if val == 32 else "中" if val == 40 else "大", True, (220, 225, 230))
            self.screen.blit(txt, (r.x + (r.w - txt.get_width()) // 2, r.y + 8))
        # 显示模式
        lbl2 = self.font.render("显示模式:", True, (200, 205, 210))
        self.screen.blit(lbl2, (panel.x + 20, panel.y + 125))
        for key, r in [("fullscreen_btn", rects["fullscreen_btn"]), ("windowed_btn", rects["windowed_btn"])]:
            mx, my = pygame.mouse.get_pos()
            hover = r.collidepoint(mx, my)
            sel = (key == "fullscreen_btn" and self.fullscreen) or (key == "windowed_btn" and not self.fullscreen)
            color = (70, 90, 60) if sel else ((55, 65, 75) if hover else (45, 50, 58))
            pygame.draw.rect(self.screen, color, r)
            pygame.draw.rect(self.screen, (85, 95, 110), r, 2)
            txt = self.font.render("全屏" if key == "fullscreen_btn" else "窗口", True, (220, 225, 230))
            self.screen.blit(txt, (r.x + (r.w - txt.get_width()) // 2, r.y + 8))
        for key in ["back", "main_menu_btn"]:
            r = rects[key]
            mx, my = pygame.mouse.get_pos()
            hover = r.collidepoint(mx, my)
            color = (55, 75, 65) if hover else (55, 65, 75)
            pygame.draw.rect(self.screen, color, r)
            pygame.draw.rect(self.screen, (80, 90, 105), r, 2)
        bt = self.font.render("返回", True, (255, 255, 255))
        self.screen.blit(bt, (rects["back"].x + (rects["back"].w - bt.get_width()) // 2, rects["back"].y + 8))
        bt2 = self.font.render("返回主菜单", True, (255, 255, 255))
        self.screen.blit(bt2, (rects["main_menu_btn"].x + (rects["main_menu_btn"].w - bt2.get_width()) // 2, rects["main_menu_btn"].y + 8))
    
    def _editor_button_rects(self) -> Tuple[pygame.Rect, pygame.Rect]:
        """获取开始/停止按钮矩形"""
        p = self.editor_panel
        content = p.content_rect()
        btn_h = 32
        btn_y = content.y + content.h - btn_h - 4
        return (
            pygame.Rect(content.x + 10, btn_y, 100, btn_h - 4),
            pygame.Rect(content.x + 120, btn_y, 100, btn_h - 4),
        )
    
    def _render_grid(self, camera_x: int, camera_y: int) -> None:
        """渲染网格线 (可选，浅色)"""
        ts = self.tile_size
        for x in range(0, self.width + ts, ts):
            wx = (x + camera_x) % ts - camera_x % ts
            if 0 <= wx <= self.width:
                pygame.draw.line(self.screen, (60, 60, 65), (wx, 0), (wx, self.height))
        for y in range(0, self.height + ts, ts):
            wy = (y + camera_y) % ts - camera_y % ts
            if 0 <= wy <= self.height:
                pygame.draw.line(self.screen, (60, 60, 65), (0, wy), (self.width, wy))
    
    def _get_main_menu_button_rects(self) -> Dict[str, pygame.Rect]:
        """主页面底部按钮矩形"""
        w, h = self.width, self.height
        btn_w, btn_h = 130, 42
        gap = 20
        total = 3 * btn_w + 2 * gap
        start_x = (w - total) // 2
        by = h - 85
        return {
            "start": pygame.Rect(start_x, by, btn_w, btn_h),
            "delete": pygame.Rect(start_x + btn_w + gap, by, btn_w, btn_h),
            "settings": pygame.Rect(start_x + (btn_w + gap) * 2, by, btn_w, btn_h),
        }

    def _render_main_menu(
        self, selected: int, hover_slot: Optional[int] = None,
        mode: str = "main", delete_toast: int = 0
    ) -> List[Tuple[pygame.Rect, int]]:
        """渲染主页面。mode: main|delete_confirm|settings. 返回 [(rect, slot_id), ...]"""
        from .save_manager import MAX_SLOTS, list_saves
        w, h = self.width, self.height
        rects = []
        hover = hover_slot if hover_slot is not None else selected
        # 背景
        self.screen.fill((22, 24, 30))
        for i in range(0, h, 20):
            alpha = 8 + (i // 20) % 4 * 2
            s = pygame.Surface((w, 20))
            s.set_alpha(alpha)
            s.fill((35, 40, 50))
            self.screen.blit(s, (0, i))
        pygame.draw.rect(self.screen, (40, 45, 55), (0, 0, w, 4))
        # 标题
        title = self.font_title.render("ByteFarm", True, (255, 235, 120))
        title_rect = title.get_rect(centerx=w // 2, top=50)
        self.screen.blit(title, title_rect)
        tag = self.font.render("用 Python 编写程序，控制你的机器人", True, (150, 160, 180))
        self.screen.blit(tag, (w // 2 - tag.get_width() // 2, title_rect.bottom + 12))
        # 主面板
        panel_w, panel_h = 520, 340
        px = (w - panel_w) // 2
        py = 180
        pygame.draw.rect(self.screen, (32, 36, 44), (px, py, panel_w, panel_h))
        pygame.draw.rect(self.screen, (55, 62, 75), (px, py, panel_w, panel_h), 2)
        pygame.draw.rect(self.screen, (45, 50, 60), (px + 2, py + 2, panel_w - 4, 50))
        panel_title = self.font_large.render("选择存档位", True, (220, 230, 240))
        self.screen.blit(panel_title, (px + (panel_w - panel_title.get_width()) // 2, py + 10))
        hint = self.font.render("方向键/数字键选择 · 回车开始 · 点击按钮执行操作", True, (120, 130, 145))
        self.screen.blit(hint, (px + (panel_w - hint.get_width()) // 2, py + 55))
        # 存档位卡片
        saves = list_saves()
        card_w, card_h = 88, 72
        gap = 12
        start_x = px + (panel_w - (5 * card_w + 4 * gap)) // 2 + gap // 2
        start_y = py + 95
        for i in range(MAX_SLOTS):
            slot_id = i + 1
            col, row = i % 5, i // 5
            cx = start_x + col * (card_w + gap)
            cy = start_y + row * (card_h + gap)
            r = pygame.Rect(cx, cy, card_w, card_h)
            rects.append((r, slot_id))
            save_info = next((s for s in saves if s["slot_id"] == slot_id), None)
            is_highlight = hover == slot_id
            bg = (50, 65, 45) if is_highlight else ((42, 48, 58) if save_info else (38, 42, 50))
            pygame.draw.rect(self.screen, bg, r)
            border_c = (100, 200, 120) if is_highlight else ((70, 78, 95) if save_info else (55, 60, 72))
            pygame.draw.rect(self.screen, border_c, r, 2)
            num = self.font_large.render(str(slot_id), True, (200, 210, 225))
            self.screen.blit(num, (r.centerx - num.get_width() // 2, r.top + 8))
            if save_info:
                lbl = self.font.render(save_info["summary"], True, (140, 160, 170))
                lw = min(lbl.get_width(), card_w - 8)
                clip = lbl.subsurface((0, 0, lw, lbl.get_height())) if lbl.get_width() > lw else lbl
                self.screen.blit(clip, (r.centerx - clip.get_width() // 2, r.top + 38))
            else:
                new_t = self.font.render("新游戏", True, (100, 115, 130))
                self.screen.blit(new_t, (r.centerx - new_t.get_width() // 2, r.top + 38))
        # 底部按钮
        btn_rects = self._get_main_menu_button_rects()
        mx, my = pygame.mouse.get_pos()
        for key, r in btn_rects.items():
            hov = r.collidepoint(mx, my) and mode == "main"
            color = (55, 90, 65) if hov else (45, 52, 60)
            pygame.draw.rect(self.screen, color, r)
            pygame.draw.rect(self.screen, (85, 95, 110), r, 2)
        labels = {"start": "开始游戏", "delete": "删除存档", "settings": "游戏设置"}
        for key, r in btn_rects.items():
            txt = self.font.render(labels[key], True, (220, 230, 240))
            self.screen.blit(txt, (r.centerx - txt.get_width() // 2, r.centery - txt.get_height() // 2 - 2))
        if delete_toast > 0:
            toast = self.font.render("已删除", True, (100, 255, 100))
            self.screen.blit(toast, (w // 2 - toast.get_width() // 2, h - 130))
        esc_t = self.font.render("按 Esc 退出", True, (90, 100, 115))
        self.screen.blit(esc_t, (w // 2 - esc_t.get_width() // 2, h - 40))
        return rects

    def _get_delete_confirm_rects(self, selected: int) -> Tuple[pygame.Rect, pygame.Rect]:
        """获取删除确认弹窗的 (确定, 取消) 按钮矩形"""
        w, h = self.width, self.height
        pop_w, pop_h = 360, 160
        px = (w - pop_w) // 2
        py = (h - pop_h) // 2
        btn_w, btn_h = 90, 36
        ok_rect = pygame.Rect(px + (pop_w - btn_w * 2 - 20) // 2, py + pop_h - 50, btn_w, btn_h)
        cancel_rect = pygame.Rect(ok_rect.right + 20, ok_rect.top, btn_w, btn_h)
        return (ok_rect, cancel_rect)

    def _render_main_menu_delete_confirm(self, selected: int, slot_has_save: bool) -> None:
        """渲染删除确认弹窗"""
        w, h = self.width, self.height
        pop_w, pop_h = 360, 160
        px = (w - pop_w) // 2
        py = (h - pop_h) // 2
        overlay = pygame.Surface((w, h))
        overlay.set_alpha(180)
        overlay.fill((15, 18, 22))
        self.screen.blit(overlay, (0, 0))
        pygame.draw.rect(self.screen, (38, 42, 52), (px, py, pop_w, pop_h))
        pygame.draw.rect(self.screen, (70, 78, 95), (px, py, pop_w, pop_h), 2)
        msg = f"确定删除存档 {selected} 吗？" if slot_has_save else f"存档 {selected} 为空，无需删除"
        title = self.font_large.render(msg, True, (240, 240, 245))
        self.screen.blit(title, (px + (pop_w - title.get_width()) // 2, py + 35))
        warn = self.font.render("删除后无法恢复", True, (255, 150, 100))
        self.screen.blit(warn, (px + (pop_w - warn.get_width()) // 2, py + 80))
        ok_rect, cancel_rect = self._get_delete_confirm_rects(selected)
        for r in [ok_rect, cancel_rect]:
            pygame.draw.rect(self.screen, (50, 55, 65), r)
            pygame.draw.rect(self.screen, (80, 90, 105), r, 2)
        ok_txt = self.font.render("确定删除", True, (255, 100, 100) if slot_has_save else (150, 150, 150))
        self.screen.blit(ok_txt, (ok_rect.centerx - ok_txt.get_width() // 2, ok_rect.centery - ok_txt.get_height() // 2 - 1))
        cancel_txt = self.font.render("取消", True, (255, 255, 255))
        self.screen.blit(cancel_txt, (cancel_rect.centerx - cancel_txt.get_width() // 2, cancel_rect.centery - cancel_txt.get_height() // 2 - 1))

    def run_menu(self) -> Optional[Tuple[int, bool]]:
        """
        主菜单 - 选择存档、删除存档、游戏设置
        返回: (slot_id, has_save) 选定槽位及是否有存档, -1=退出
        """
        from .save_manager import MAX_SLOTS, list_saves, delete_save, load_config, save_config
        selected = 1
        mode = "main"  # main | delete_confirm | settings
        delete_toast = 0
        running = True
        while running:
            saves = list_saves()
            has_save = any(s["slot_id"] == selected for s in saves)

            if mode == "settings":
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        return -1
                    elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        mode = "main"
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        rects = self._get_settings_button_rects()
                        mx, my = event.pos
                        if rects["back"].collidepoint(mx, my) or rects["main_menu_btn"].collidepoint(mx, my):
                            mode = "main"
                        elif rects["fullscreen_btn"].collidepoint(mx, my) and not self.fullscreen:
                            self.fullscreen = True
                            self._apply_display_mode(1024, 768)
                            save_config(load_config() | {"fullscreen": True})
                        elif rects["windowed_btn"].collidepoint(mx, my) and self.fullscreen:
                            self.fullscreen = False
                            self._apply_display_mode(1024, 768)
                            save_config(load_config() | {"fullscreen": False})
                        for i, (ts_val, r) in enumerate(rects["tile_sizes"]):
                            if r.collidepoint(mx, my):
                                self.tile_size = ts_val
                                save_config(load_config() | {"tile_size": ts_val})
                                break
                    elif event.type == pygame.VIDEORESIZE:
                        self.width = event.w
                        self.height = event.h
                        self.screen = pygame.display.set_mode((self.width, self.height), pygame.RESIZABLE)
                if mode == "settings" and running:
                    self._render_main_menu(selected)
                    self._render_settings_panel()
                    pygame.display.flip()
                    self.clock.tick(30)
                continue

            if mode == "delete_confirm":
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        return -1
                    elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        mode = "main"
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        ok_rect, cancel_rect = self._get_delete_confirm_rects(selected)
                        mx, my = event.pos
                        if cancel_rect.collidepoint(mx, my):
                            mode = "main"
                        elif ok_rect.collidepoint(mx, my):
                            if has_save and delete_save(selected):
                                delete_toast = 90
                            mode = "main"
                if mode == "delete_confirm":
                    self._render_main_menu(selected, None, "main", 0)
                    self._render_main_menu_delete_confirm(selected, has_save)
                    pygame.display.flip()
                    self.clock.tick(30)
                continue

            # mode == "main"
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return -1
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return -1
                    elif event.key == pygame.K_UP:
                        selected = selected - 5 if selected > 5 else selected + 5
                    elif event.key == pygame.K_DOWN:
                        selected = selected + 5 if selected <= 5 else selected - 5
                    elif event.key == pygame.K_LEFT:
                        selected = max(1, selected - 1)
                    elif event.key == pygame.K_RIGHT:
                        selected = min(MAX_SLOTS, selected + 1)
                    elif event.key == pygame.K_RETURN or event.key == pygame.K_SPACE:
                        return (selected, has_save)
                    elif event.unicode and event.unicode.isdigit():
                        n = int(event.unicode)
                        if n == 0:
                            n = 10
                        if 1 <= n <= MAX_SLOTS:
                            selected = n
                            has_save = any(s["slot_id"] == selected for s in saves)
                            return (selected, has_save)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mx, my = event.pos
                    rects = self._get_main_menu_slot_rects(selected)
                    btn_rects = self._get_main_menu_button_rects()
                    if btn_rects["start"].collidepoint(mx, my):
                        return (selected, has_save)
                    if btn_rects["delete"].collidepoint(mx, my):
                        mode = "delete_confirm"
                        continue
                    if btn_rects["settings"].collidepoint(mx, my):
                        mode = "settings"
                        continue
                    for r, sid in rects:
                        if r.collidepoint(mx, my):
                            selected = sid
                            has_save = any(s["slot_id"] == selected for s in saves)
                            return (selected, has_save)

            if delete_toast > 0:
                delete_toast -= 1
            mx, my = pygame.mouse.get_pos()
            rects = self._get_main_menu_slot_rects(selected)
            hover_slot = next((sid for r, sid in rects if r.collidepoint(mx, my)), None)
            self._render_main_menu(selected, hover_slot, "main", delete_toast)
            pygame.display.flip()
            self.clock.tick(30)
        return -1

    def _get_main_menu_slot_rects(self, _selected: int) -> List[Tuple[pygame.Rect, int]]:
        """计算主菜单存档位矩形（与 _render_main_menu 逻辑一致）"""
        from .save_manager import MAX_SLOTS
        w = self.width
        panel_w = 520
        px = (w - panel_w) // 2
        py = 180
        card_w, card_h = 88, 72
        gap = 12
        start_x = px + (panel_w - (5 * card_w + 4 * gap)) // 2 + gap // 2
        start_y = py + 95
        rects = []
        for i in range(MAX_SLOTS):
            slot_id = i + 1
            col, row = i % 5, i // 5
            cx = start_x + col * (card_w + gap)
            cy = start_y + row * (card_h + gap)
            rects.append((pygame.Rect(cx, cy, card_w, card_h), slot_id))
        return rects
    
    def run(self) -> Optional[str]:
        """主游戏循环。返回 'main_menu' 表示返回主菜单，None 表示退出"""
        camera_x = 0
        camera_y = 0
        running = True
        return_to_main_menu = False
        show_load_menu = False
        show_delete_menu = False
        show_upgrade_tree = False
        show_game_menu = False
        show_settings = False
        save_toast_frames = 0
        delete_toast_frames = 0
        last_autosave_ticks = pygame.time.get_ticks()
        
        while running:
            if show_settings:
                # 游戏设置子界面
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                        break
                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            show_settings = False
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        rects = self._get_settings_button_rects()
                        mx, my = event.pos
                        if rects["back"].collidepoint(mx, my):
                            show_settings = False
                        elif rects["main_menu_btn"].collidepoint(mx, my):
                            return_to_main_menu = True
                            running = False
                            show_settings = False
                            break
                        elif rects["fullscreen_btn"].collidepoint(mx, my) and not self.fullscreen:
                            self.fullscreen = True
                            self._apply_display_mode(1024, 768)
                            save_config(load_config() | {"fullscreen": True})
                        elif rects["windowed_btn"].collidepoint(mx, my) and self.fullscreen:
                            self.fullscreen = False
                            self._apply_display_mode(1024, 768)
                            save_config(load_config() | {"fullscreen": False})
                        for i, (ts_val, r) in enumerate(rects["tile_sizes"]):
                            if r.collidepoint(mx, my):
                                self.tile_size = ts_val
                                break
                    elif event.type == pygame.VIDEORESIZE:
                        self.width = event.w
                        self.height = event.h
                        self.screen = pygame.display.set_mode((self.width, self.height), pygame.RESIZABLE)
                        self.editor_panel.clamp_to_screen(self.width, self.height)
                if show_settings and running:
                    self._render_settings_panel()
                    pygame.display.flip()
                    self.clock.tick(30)
                continue
            
            if show_delete_menu:
                del_main_btn = pygame.Rect(self.width // 2 - 55, self.height // 2 + 120, 110, 36)
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                        break
                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            show_delete_menu = False
                        elif event.unicode and event.unicode.isdigit():
                            n = int(event.unicode)
                            if n == 0:
                                n = 10
                            if 1 <= n <= 10:
                                saves = list_saves()
                                if any(s["slot_id"] == n for s in saves):
                                    if delete_save(n):
                                        delete_toast_frames = 90
                                        if self.current_save_slot == n:
                                            self.current_save_slot = None
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        if del_main_btn.collidepoint(event.pos):
                            return_to_main_menu = True
                            running = False
                            show_delete_menu = False
                            break
                    elif event.type == pygame.VIDEORESIZE:
                        self.width = event.w
                        self.height = event.h
                        self.screen = pygame.display.set_mode((self.width, self.height), pygame.RESIZABLE)
                
                if show_delete_menu and running:
                    self.screen.fill(COLORS["background"])
                    overlay = pygame.Surface((self.width, self.height))
                    overlay.set_alpha(220)
                    overlay.fill((20, 20, 25))
                    self.screen.blit(overlay, (0, 0))
                    y = self.height // 2 - 130
                    title = self.font_large.render("删除存档 (按 1-9/0 选择, Esc 取消)", True, (255, 255, 255))
                    self.screen.blit(title, (self.width // 2 - title.get_width() // 2, y))
                    y += 35
                    warn = self.font.render("注意: 删除后无法恢复", True, (255, 150, 100))
                    self.screen.blit(warn, (self.width // 2 - warn.get_width() // 2, y))
                    y += 35
                    from .save_manager import MAX_SLOTS, list_saves
                    saves = list_saves()
                    for slot_id in range(1, MAX_SLOTS + 1):
                        save_info = next((s for s in saves if s["slot_id"] == slot_id), None)
                        key = "0" if slot_id == 10 else str(slot_id)
                        if save_info:
                            label = f"  [{key}] 存档{slot_id}: {save_info['name']} - {save_info['summary']}"
                        else:
                            label = f"  [{key}] 存档{slot_id}: (空)"
                        txt = self.font.render(label, True, (220, 220, 220))
                        self.screen.blit(txt, (self.width // 2 - 220, y))
                        y += 26
                    if delete_toast_frames > 0:
                        delete_toast_frames -= 1
                        toast = self.font.render("已删除", True, (100, 255, 100))
                        self.screen.blit(toast, (self.width // 2 - toast.get_width() // 2, y + 10))
                    # 返回主菜单按钮
                    mx, my = pygame.mouse.get_pos()
                    hov = del_main_btn.collidepoint(mx, my)
                    pygame.draw.rect(self.screen, (55, 75, 65) if hov else (50, 55, 65), del_main_btn)
                    pygame.draw.rect(self.screen, (80, 90, 105), del_main_btn, 2)
                    bt = self.font.render("返回主菜单", True, (255, 255, 255))
                    self.screen.blit(bt, (del_main_btn.centerx - bt.get_width() // 2, del_main_btn.centery - bt.get_height() // 2 - 1))
                    pygame.display.flip()
                    self.clock.tick(30)
                continue
            
            if show_load_menu:
                load_main_btn = pygame.Rect(self.width // 2 - 55, self.height // 2 + 100, 110, 36)
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                        break
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        if load_main_btn.collidepoint(event.pos):
                            return_to_main_menu = True
                            running = False
                            show_load_menu = False
                            break
                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            show_load_menu = False
                        elif event.unicode and event.unicode.isdigit():
                            n = int(event.unicode)
                            if n == 0:
                                n = 10
                            if 1 <= n <= 10:
                                saves = list_saves()
                                if any(s["slot_id"] == n for s in saves):
                                    if self.load_from_slot(n):
                                        show_load_menu = False
                                else:
                                    self.start_new_game(n)
                                    show_load_menu = False
                    elif event.type == pygame.VIDEORESIZE:
                        self.width = event.w
                        self.height = event.h
                        self.screen = pygame.display.set_mode((self.width, self.height), pygame.RESIZABLE)
                
                if show_load_menu and running:
                    self.screen.fill(COLORS["background"])
                    overlay = pygame.Surface((self.width, self.height))
                    overlay.set_alpha(220)
                    overlay.fill((20, 20, 25))
                    self.screen.blit(overlay, (0, 0))
                    y = self.height // 2 - 120
                    title = self.font_large.render("读档 (按 1-9/0 选择, Esc 取消)", True, (255, 255, 255))
                    self.screen.blit(title, (self.width // 2 - title.get_width() // 2, y))
                    y += 50
                    from .save_manager import MAX_SLOTS, list_saves
                    saves = list_saves()
                    for slot_id in range(1, MAX_SLOTS + 1):
                        save_info = next((s for s in saves if s["slot_id"] == slot_id), None)
                        key = "0" if slot_id == 10 else str(slot_id)
                        if save_info:
                            label = f"  [{key}] 存档{slot_id}: {save_info['summary']}"
                        else:
                            label = f"  [{key}] 存档{slot_id}: (空)"
                        txt = self.font.render(label, True, (220, 220, 220))
                        self.screen.blit(txt, (self.width // 2 - 200, y))
                        y += 26
                    mx, my = pygame.mouse.get_pos()
                    hov = load_main_btn.collidepoint(mx, my)
                    pygame.draw.rect(self.screen, (55, 75, 65) if hov else (50, 55, 65), load_main_btn)
                    pygame.draw.rect(self.screen, (80, 90, 105), load_main_btn, 2)
                    bt = self.font.render("返回主菜单", True, (255, 255, 255))
                    self.screen.blit(bt, (load_main_btn.centerx - bt.get_width() // 2, load_main_btn.centery - bt.get_height() // 2 - 1))
                    pygame.display.flip()
                    self.clock.tick(30)
                continue
            
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION, pygame.MOUSEWHEEL):
                    if event.type == pygame.MOUSEBUTTONDOWN and show_game_menu:
                        mx, my = pygame.mouse.get_pos()
                        handled = self._handle_game_menu_click(mx, my)
                        if handled:
                            action = handled
                            if action == "save":
                                if self.current_save_slot:
                                    if self.save_to_slot(self.current_save_slot):
                                        save_toast_frames = 90
                                        show_game_menu = False
                                else:
                                    show_game_menu = False
                                    show_load_menu = True
                            elif action == "load":
                                show_game_menu = False
                                if self.current_save_slot:
                                    self.save_to_slot(self.current_save_slot)
                                show_load_menu = True
                            elif action == "delete":
                                show_game_menu = False
                                show_delete_menu = True
                            elif action == "settings":
                                show_game_menu = False
                                show_settings = True
                            elif action == "wiki":
                                show_game_menu = False
                                self.show_wiki = True
                            elif action == "main_menu":
                                return_to_main_menu = True
                                running = False
                            elif action == "quit":
                                running = False
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and show_upgrade_tree and not show_game_menu:
                        mx, my = pygame.mouse.get_pos()
                        px, py, pw, ph = self._get_upgrade_panel_rect()
                        if not (px <= mx < px + pw and py <= my < py + ph):
                            show_upgrade_tree = False
                        else:
                            self._handle_upgrade_panel_click(mx, my)
                    if not show_game_menu:
                        if self.show_wiki and self._wiki_handle_events(event):
                            pass
                        elif self.show_terminal and self._terminal_handle_events(event):
                            pass
                        elif self._editor_handle_events(event):
                            pass
                elif event.type == pygame.KEYDOWN:
                    mods = pygame.key.get_mods()
                    mod = mods & _MOD_KEY
                    if event.key == pygame.K_ESCAPE:
                        if self.editor_rename_file:
                            self._handle_rename_key(event)
                        elif self.show_wiki:
                            self.show_wiki = False
                        else:
                            show_game_menu = not show_game_menu
                    elif mod and event.key == pygame.K_e:
                        self.show_editor = not self.show_editor
                    elif event.key == pygame.K_F1:
                        self.show_wiki = not self.show_wiki
                    elif mod and event.key == pygame.K_t:
                        self.show_terminal = not self.show_terminal
                    elif event.key == pygame.K_F2:
                        self.start_execution()
                    elif event.key == pygame.K_F3:
                        self.stop_execution()
                    elif event.key == pygame.K_F5:
                        if not self.current_save_slot:
                            show_load_menu = True  # 未选槽位时打开读档菜单选择
                        elif self.save_to_slot(self.current_save_slot):
                            save_toast_frames = 90
                    elif event.key == pygame.K_F9:
                        if self.current_save_slot:
                            self.save_to_slot(self.current_save_slot)
                        show_load_menu = True
                    elif mod and event.key == pygame.K_u:
                        show_upgrade_tree = not show_upgrade_tree
                    elif self.show_editor and not show_game_menu:
                        if self.editor_rename_file and self._handle_rename_key(event):
                            pass
                        else:
                            if self.is_running and self._is_editor_modifying_key(event):
                                self.stop_execution()
                            self.editor.set_project_files(self.editor_files, self.editor_current_file)
                            self.editor.handle_key(event)
                elif event.type == pygame.VIDEORESIZE:
                    self.width = event.w
                    self.height = event.h
                    self.screen = pygame.display.set_mode((self.width, self.height), pygame.RESIZABLE)
                    self.editor_panel.clamp_to_screen(self.width, self.height)
                    self.terminal_panel.clamp_to_screen(self.width, self.height)
            
            # 更新：按 tick 推进，每帧处理玩家操作
            dt = self.clock.get_time()
            self.tick += dt
            self._process_runtime_op()
            
            if self.tick - self._last_respawn_tick >= 60000:  # 每 60 秒游戏时间恢复资源
                self.world.respawn_resources()
                self._last_respawn_tick = self.tick
            
            # 每 60 秒自动存档
            now_ticks = pygame.time.get_ticks()
            if self.current_save_slot and (now_ticks - last_autosave_ticks) >= 60000:
                self.save_to_slot(self.current_save_slot)
                last_autosave_ticks = now_ticks
            
            # 摄像机跟随玩家
            ts = self.tile_size
            target_cx = self.player.x * ts - self.width // 2 + ts // 2
            target_cy = (self.world.height - 1 - self.player.y) * ts - self.height // 2 + ts // 2
            camera_x += (target_cx - camera_x) * 0.1
            camera_y += (target_cy - camera_y) * 0.1
            camera_x = max(0, min(camera_x, self.world.width * ts - self.width))
            camera_y = max(0, min(camera_y, self.world.height * ts - self.height))
            
            # 渲染
            self.screen.fill(COLORS["background"])
            self._render_tiles(int(camera_x), int(camera_y))
            self._render_grid(int(camera_x), int(camera_y))
            self._render_player(int(camera_x), int(camera_y))
            self._update_plant_particles()
            self._render_plant_particles(int(camera_x), int(camera_y))
            self._render_ui()
            
            if self.show_editor:
                self._render_editor_panel()
            
            if self.show_terminal:
                self.terminal_panel.render(self.screen)
            
            if show_upgrade_tree:
                self._render_upgrade_tree_panel()
            
            if show_game_menu:
                self._render_game_menu()
            
            if self.show_wiki:
                self._render_wiki_panel()
            
            if save_toast_frames > 0:
                save_toast_frames -= 1
                toast = self.font_large.render("已保存!", True, (100, 255, 100))
                tx = self.width // 2 - toast.get_width() // 2
                ty = self.height // 2 - 20
                pygame.draw.rect(self.screen, (40, 40, 45), (tx - 10, ty - 5, toast.get_width() + 20, toast.get_height() + 10))
                self.screen.blit(toast, (tx, ty))
            
            pygame.display.flip()
            self.clock.tick(60)  # 渲染 60 FPS，tick 由 get_time() 提供真实耗时
        
        # 退出前自动存档（返回主菜单时也保存）
        if self.current_save_slot:
            self.save_to_slot(self.current_save_slot)
        if return_to_main_menu:
            return "main_menu"
        pygame.quit()
        return None
