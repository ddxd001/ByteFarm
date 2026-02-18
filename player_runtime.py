"""
玩家程序运行时 - 时间基准、顺序执行
玩家编写 run()，直接调用 move()、collect()、measure()，无需 import 游戏模块
新建的子模块（被 main 导入的 .py）也会自动注入相同 API
"""

import builtins
import sys
import traceback
import threading
from pathlib import Path
from typing import Optional, List, Any, Callable
from queue import Queue, Empty


# 方向常量 - 注入到玩家命名空间
East = "east"
West = "west"
North = "north"
South = "south"

# 地面类型
class Ground:
    Grassland = "grassland"
    Sandyland = "sandyland"

# 实体类型
class Entities:
    Grass = "grass"
    Stone = "stone"
    Bush = "bush"
    Tree = "tree"


class PlayerRuntime:
    """
    玩家程序运行时
    - 玩家程序在独立线程运行，定义 run()
    - move(direction)、collect()、measure() 作为全局函数注入
    - 每个操作消耗时间，顺序执行
    """
    
    def __init__(self):
        self._op_queue: Queue = Queue()
        self._result_event = threading.Event()
        self._op_done = False
        self._thread: Optional[threading.Thread] = None
        self._module = None
        self._running = False
        self._measure_fn: Optional[Callable[[], int]] = None
        self._upgrade_fn: Optional[Callable[[str], bool]] = None
        self._get_purchasable_fn: Optional[Callable[[], List[str]]] = None
        self._get_position_fn: Optional[Callable[[], tuple]] = None
        self._get_nearby_fn: Optional[Callable[[], List[tuple]]] = None
        self._get_map_size_fn: Optional[Callable[[], tuple]] = None
        self._get_ground_fn: Optional[Callable[[], str]] = None
        self._output_buffer: Optional[Any] = None  # TerminalBuffer 或兼容 write() 的对象
    
    def set_output_buffer(self, buffer: Any) -> None:
        """设置输出缓冲，用于 print 和异常信息"""
        self._output_buffer = buffer
    
    def set_measure_fn(self, fn: Callable[[], int]) -> None:
        self._measure_fn = fn
    
    def set_upgrade_fn(self, fn: Callable[[str], bool]) -> None:
        self._upgrade_fn = fn
    
    def set_get_purchasable_fn(self, fn: Callable[[], List[str]]) -> None:
        self._get_purchasable_fn = fn
    
    def set_get_position_fn(self, fn: Callable[[], tuple]) -> None:
        self._get_position_fn = fn
    
    def set_get_nearby_fn(self, fn: Callable[[], List[tuple]]) -> None:
        self._get_nearby_fn = fn
    
    def set_get_map_size_fn(self, fn: Callable[[], tuple]) -> None:
        self._get_map_size_fn = fn
    
    def set_get_ground_fn(self, fn: Callable[[], str]) -> None:
        self._get_ground_fn = fn
    
    def _create_injected_namespace(self):
        """创建注入 move/collect/measure 的命名空间"""
        runtime = self
        
        def move(direction: str) -> None:
            if direction in (East, West, North, South):
                runtime._op_queue.put(("move", direction))
                runtime._result_event.wait()
                runtime._result_event.clear()
        
        def collect() -> None:
            runtime._op_queue.put(("collect",))
            runtime._result_event.wait()
            runtime._result_event.clear()
        
        def measure() -> int:
            if runtime._measure_fn:
                return runtime._measure_fn()
            return 0
        
        def can_collect() -> bool:
            """当前格子是否有成熟实体可采集"""
            if runtime._measure_fn:
                return runtime._measure_fn() > 0
            return False
        
        def upgrade(node_id: str) -> bool:
            if runtime._upgrade_fn:
                return runtime._upgrade_fn(node_id)
            return False
        
        def get_purchasable() -> List[str]:
            if runtime._get_purchasable_fn:
                return runtime._get_purchasable_fn()
            return []
        
        def get_position() -> tuple:
            if runtime._get_position_fn:
                return runtime._get_position_fn()
            return (0, 0)
        
        def get_nearby() -> List[tuple]:
            if runtime._get_nearby_fn:
                return runtime._get_nearby_fn()
            return []
        
        def get_map_size() -> tuple:
            if runtime._get_map_size_fn:
                return runtime._get_map_size_fn()
            return (5, 5)
        
        def get_ground() -> str:
            if runtime._get_ground_fn:
                return runtime._get_ground_fn()
            return Ground.Grassland
        
        def till() -> None:
            runtime._op_queue.put(("till",))
            runtime._result_event.wait()
            runtime._result_event.clear()
        
        def plant(entity_type: str) -> None:
            runtime._op_queue.put(("plant", entity_type))
            runtime._result_event.wait()
            runtime._result_event.clear()
        
        return {
            "move": move,
            "collect": collect,
            "measure": measure,
            "can_collect": can_collect,
            "upgrade": upgrade,
            "get_purchasable": get_purchasable,
            "get_position": get_position,
            "get_nearby": get_nearby,
            "get_map_size": get_map_size,
            "get_ground": get_ground,
            "till": till,
            "plant": plant,
            "Ground": Ground,
            "Entities": Entities,
            "Entity": Entities,  # 别名，可用 Entity.Grass
            "East": East,
            "West": West,
            "North": North,
            "South": South,
        }
    
    def start(self, module) -> bool:
        """启动玩家程序（在后台线程运行 run()）"""
        if not hasattr(module, "run"):
            return False
        self._module = module
        self._running = True
        self._thread = threading.Thread(target=self._run_player, daemon=True)
        self._thread.start()
        return True
    
    def _run_player(self) -> None:
        ns = self._create_injected_namespace()
        script_dir = Path(self._module.__file__).resolve().parent
        script_dir_str = str(script_dir)
        
        def _inject_into_module(mod) -> None:
            """向模块注入 API（若该模块来自存档目录）"""
            if mod is None or not hasattr(mod, "__file__") or not mod.__file__:
                return
            try:
                mod_path = str(Path(mod.__file__).resolve().parent)
                if mod_path == script_dir_str and not mod.__file__.split("/")[-1].split("\\")[-1].startswith("_"):
                    for k, v in ns.items():
                        setattr(mod, k, v)
            except (ValueError, OSError):
                pass
        
        _orig_import = builtins.__import__
        
        def _wrapped_import(name, globals=None, locals=None, fromlist=(), level=0):
            result = _orig_import(name, globals or {}, locals or {}, fromlist, level)
            _inject_into_module(result)
            if fromlist:
                for attr in fromlist:
                    if attr != "*" and hasattr(result, attr):
                        obj = getattr(result, attr)
                        if hasattr(obj, "__module__") and obj.__module__:
                            submod = sys.modules.get(obj.__module__)
                            _inject_into_module(submod)
            return result
        
        for k, v in ns.items():
            setattr(self._module, k, v)
        builtins.__import__ = _wrapped_import
        for mod in list(sys.modules.values()):
            _inject_into_module(mod)
        
        # 替换 builtins.print 确保玩家代码中的 print 被捕获（含子函数、import 的模块等）
        _orig_print = builtins.print
        if self._output_buffer:
            def _capture_print(*args, **kwargs):
                if threading.current_thread() is self._thread:
                    sep = kwargs.get("sep", " ")
                    end = kwargs.get("end", "\n")
                    s = sep.join(str(a) for a in args) + end
                    self._output_buffer.write(s)
                else:
                    _orig_print(*args, **kwargs)
            builtins.print = _capture_print
        try:
            self._module.run()
        except Exception as e:
            tb = traceback.format_exc()
            if self._output_buffer:
                self._output_buffer.append_line("")
                self._output_buffer.write(tb)
            else:
                _orig_print(f"玩家程序异常: {e}")
        finally:
            builtins.__import__ = _orig_import
            if self._output_buffer:
                builtins.print = _orig_print
            self._running = False
    
    def poll_op(self) -> Optional[tuple]:
        """主线程轮询：获取一个待执行的操作，无则返回 None"""
        try:
            return self._op_queue.get_nowait()
        except Empty:
            return None
    
    def op_done(self) -> None:
        """主线程在操作执行完后调用，唤醒玩家线程"""
        self._result_event.set()
    
    def stop(self) -> None:
        self._running = False
        # 放入空操作以唤醒可能阻塞的玩家线程
        self._op_queue.put(("_stop",))
    
    def is_running(self) -> bool:
        return self._running
