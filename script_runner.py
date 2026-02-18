"""
脚本加载 - 加载玩家程序，注入 move/collect/measure 等（由 runtime 完成）
玩家只需定义 run()，无需 import 游戏模块
"""

import importlib.util
import sys
from pathlib import Path
from typing import Optional


_current_script_dir: Optional[str] = None


def load_player_script(script_path: str):
    """
    加载玩家主程序，必须定义 run()
    不注入 API（由 PlayerRuntime 在启动时注入）
    """
    global _current_script_dir
    
    path = Path(script_path).resolve()
    if path.is_dir():
        main_path = path / "main.py"
        script_dir = path
    else:
        main_path = path
        script_dir = path.parent
    
    if not main_path.exists():
        raise FileNotFoundError(f"主程序不存在: {main_path}")
    
    script_dir_str = str(Path(script_dir).resolve())
    # 每次都清除该目录下的模块缓存，确保执行的是玩家刚写入的最新代码
    _cleanup_script_modules(script_dir_str)
    
    if _current_script_dir and _current_script_dir != script_dir_str:
        if _current_script_dir in sys.path:
            sys.path.remove(_current_script_dir)
    
    if script_dir_str not in sys.path:
        sys.path.insert(0, script_dir_str)
    _current_script_dir = script_dir_str
    
    module_name = f"player_main_{hash(script_dir_str) % 10**8}"
    spec = importlib.util.spec_from_file_location(module_name, main_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"无法加载: {main_path}")
    
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    
    if not hasattr(module, "run"):
        raise ValueError("主程序必须定义 run() 函数")
    
    return module


def _cleanup_script_modules(script_dir: str) -> None:
    to_remove = []
    script_dir_norm = str(Path(script_dir).resolve())
    for name, mod in list(sys.modules.items()):
        if hasattr(mod, "__file__") and mod.__file__:
            try:
                mod_path = str(Path(mod.__file__).resolve().parent)
                if mod_path == script_dir_norm and not name.startswith("game"):
                    to_remove.append(name)
            except (ValueError, OSError):
                pass
    for name in to_remove:
        del sys.modules[name]


def run_script_from_code(code: str, script_dir: Optional[str] = None):
    """从编辑器代码加载，写入临时文件后加载"""
    base = Path(script_dir).resolve() if script_dir else Path(__file__).resolve().parent
    if base.is_file():
        base = base.parent
    run_file = base / "_editor_run.py"
    try:
        run_file.write_text(code, encoding="utf-8")
        return load_player_script(str(run_file))
    except Exception as e:
        print(f"加载失败: {e}")
        return None
