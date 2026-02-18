"""
存档管理 - 每个存档为独立文件夹，包含 state.json 和玩家 Python 程序
"""

import json
import shutil
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any

# 存档根目录
SAVES_DIR = Path(__file__).resolve().parent.parent / "saves"
CONFIG_FILE = Path(__file__).resolve().parent.parent / "config.json"
MAX_SLOTS = 10


def load_config() -> Dict[str, Any]:
    """加载游戏配置"""
    default = {"fullscreen": True, "tile_size": 40}
    if not CONFIG_FILE.exists():
        return default
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("fullscreen", True)
        data.setdefault("tile_size", 40)
        return data
    except (json.JSONDecodeError, IOError):
        return default


def save_config(config: Dict[str, Any]) -> bool:
    """保存游戏配置"""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except IOError:
        return False
STATE_FILE = "state.json"
MAIN_FILE = "main.py"


def _ensure_saves_dir() -> Path:
    """确保存档根目录存在"""
    SAVES_DIR.mkdir(parents=True, exist_ok=True)
    return SAVES_DIR


def get_save_folder(slot_id: int) -> Path:
    """获取某个存档槽位的文件夹路径"""
    _ensure_saves_dir()
    return SAVES_DIR / f"save_{slot_id}"


def get_scratch_folder() -> Path:
    """获取临时运行目录（未加载存档时使用，不覆盖真实存档）"""
    _ensure_saves_dir()
    return SAVES_DIR / "_scratch"


def get_main_path(slot_id: int) -> Path:
    """获取存档的主程序路径 main.py"""
    return get_save_folder(slot_id) / MAIN_FILE


def list_saves() -> List[Dict[str, Any]]:
    """
    列出所有存档（文件夹内存在 state.json 的视为有效存档）
    返回: [{"slot_id", "name", "folder": Path, "main_path": Path, "updated_at", "summary"}, ...]
    """
    _ensure_saves_dir()
    saves = []
    for i in range(1, MAX_SLOTS + 1):
        folder = get_save_folder(i)
        state_path = folder / STATE_FILE
        if state_path.exists():
            try:
                with open(state_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                name = data.get("name", f"存档 {i}")
                updated = data.get("updated_at", "")
                player = data.get("player")
                inv = (player.get("inventory", {}) if isinstance(player, dict) else {}) or {}
                grass = inv.get("grass", 0)
                stone = inv.get("stone", 0)
                summary = f"草:{grass} 石头:{stone}"
                saves.append({
                    "slot_id": i,
                    "name": name,
                    "folder": folder,
                    "main_path": folder / MAIN_FILE,
                    "updated_at": updated,
                    "summary": summary,
                })
            except (json.JSONDecodeError, KeyError):
                saves.append({
                    "slot_id": i,
                    "name": f"存档 {i} (损坏)",
                    "folder": folder,
                    "main_path": folder / MAIN_FILE,
                    "updated_at": "",
                    "summary": "无法读取",
                })
    return saves


def save_game(data: Dict[str, Any], slot_id: int, main_script_content: str, name: Optional[str] = None,
              extra_scripts: Optional[Dict[str, str]] = None) -> bool:
    """
    保存游戏到指定槽位
    - 创建存档文件夹 save_N/
    - 写入 state.json（游戏状态）
    - 写入 main.py（玩家主程序，可覆盖）
    - extra_scripts: 额外的 .py 文件 {文件名: 内容}，一并写入
    """
    if not 1 <= slot_id <= MAX_SLOTS:
        return False
    data["updated_at"] = datetime.now().isoformat()
    if name:
        data["name"] = name
    if "name" not in data:
        data["name"] = f"存档 {slot_id}"
    
    folder = get_save_folder(slot_id)
    folder.mkdir(parents=True, exist_ok=True)
    
    try:
        state_path = folder / STATE_FILE
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        main_path = folder / MAIN_FILE
        with open(main_path, "w", encoding="utf-8") as f:
            f.write(main_script_content)
        
        if extra_scripts:
            for fname, content in extra_scripts.items():
                if fname != MAIN_FILE and fname.endswith(".py"):
                    (folder / fname).write_text(content, encoding="utf-8")
        # 删除已从编辑器中移除的文件
        keep = {MAIN_FILE} | {k for k in (extra_scripts or {}) if k.endswith(".py")}
        for p in folder.glob("*.py"):
            if not p.name.startswith("_") and p.name not in keep:
                try:
                    p.unlink()
                except IOError:
                    pass
        return True
    except (IOError, TypeError) as e:
        print(f"保存失败: {e}")
        return False


def load_game(slot_id: int) -> Optional[Dict[str, Any]]:
    """从指定槽位加载存档（仅 state.json）"""
    if not 1 <= slot_id <= MAX_SLOTS:
        return None
    state_path = get_save_folder(slot_id) / STATE_FILE
    if not state_path.exists():
        return None
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"加载失败: {e}")
        return None


def get_script_content(slot_id: int) -> Optional[str]:
    """读取存档的 main.py 内容"""
    main_path = get_main_path(slot_id)
    if not main_path.exists():
        return None
    try:
        return main_path.read_text(encoding="utf-8")
    except IOError:
        return None


def list_py_files(slot_id: int) -> List[str]:
    """列出存档目录下所有 .py 文件（含 main.py），排除临时文件"""
    folder = get_save_folder(slot_id)
    if not folder.exists():
        return []
    result = []
    for p in sorted(folder.glob("*.py")):
        if p.name.startswith("_"):  # 排除 _editor_run.py 等临时文件
            continue
        if p.name not in result:
            result.append(p.name)
    # 保证 main.py 在最前
    if MAIN_FILE in result:
        result.remove(MAIN_FILE)
        result.insert(0, MAIN_FILE)
    return result


def load_all_scripts(slot_id: int) -> Dict[str, str]:
    """加载存档下所有 .py 文件，返回 {文件名: 内容}"""
    folder = get_save_folder(slot_id)
    result = {}
    for name in list_py_files(slot_id):
        path = folder / name
        try:
            result[name] = path.read_text(encoding="utf-8")
        except IOError:
            result[name] = ""
    return result


def save_all_scripts(slot_id: int, files: Dict[str, str]) -> bool:
    """将 {文件名: 内容} 写入存档目录"""
    folder = get_save_folder(slot_id)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        for name, content in files.items():
            if not name.endswith(".py"):
                continue
            (folder / name).write_text(content, encoding="utf-8")
        return True
    except IOError as e:
        print(f"保存脚本失败: {e}")
        return False


def delete_save(slot_id: int) -> bool:
    """删除指定槽位的存档（整个文件夹）"""
    if not 1 <= slot_id <= MAX_SLOTS:
        return False
    folder = get_save_folder(slot_id)
    if folder.exists():
        try:
            shutil.rmtree(folder)
            return True
        except IOError:
            return False
    return True


def migrate_old_save(slot_id: int) -> bool:
    """将旧版 save_N.json 迁移到 save_N/state.json + main.py"""
    old_path = SAVES_DIR / f"save_{slot_id}.json"
    if not old_path.exists():
        return False
    try:
        with open(old_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 使用默认模板作为 main.py
        default_main = get_default_main_template()
        folder = get_save_folder(slot_id)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / STATE_FILE).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        (folder / MAIN_FILE).write_text(default_main, encoding="utf-8")
        old_path.unlink()
        return True
    except Exception:
        return False


def get_default_main_template() -> str:
    """获取默认 main.py 模板（新存档或迁移时使用）"""
    template_path = Path(__file__).resolve().parent.parent / "player_strategy.py"
    if template_path.exists():
        try:
            return template_path.read_text(encoding="utf-8")
        except IOError:
            pass
    _mod = "Cmd+T" if sys.platform == "darwin" else "Ctrl+T"
    return '''"""
机器人程序 - 绕着地图边缘逆时针转，遇资源则采集
print() 输出会显示在终端 (''' + _mod + ''' 切换)
"""
def run():
    w, h = get_map_size()
    while True:
        if measure() > 0:
            collect()
        else:
            for nid in get_purchasable():
                upgrade(nid)
                break
            else:
                x, y = get_position()
                # 坐标系：左下角(0,0)，x向右，y向上。逆时针沿边缘
                if x == 0 and y > 0:
                    move(South)
                elif x == 0 and y == 0:
                    move(East)
                elif y == 0 and x < w - 1:
                    move(East)
                elif x == w - 1 and y < h - 1:
                    move(North)
                elif x == w - 1 and y == h - 1:
                    move(West)
                elif y == h - 1 and x > 0:
                    move(West)
                else:
                    move(South)
'''
