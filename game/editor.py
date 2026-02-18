"""
内置代码编辑器 - 行号、滚轮、语法高亮、撤销、复制粘贴、点击定位等
"""

import sys
import pygame
from typing import Dict, List, Optional, Tuple
from pathlib import Path

# 内部剪贴板
_clipboard: str = ""

# Python 语法高亮
PYTHON_HIGHLIGHT = {
    "keyword": (255, 120, 180),
    "string": (155, 220, 120),
    "comment": (110, 130, 140),
    "builtin": (100, 200, 255),
    "user_def": (230, 200, 100),  # 玩家自定义函数
    "number": (180, 200, 120),
    "default": (220, 220, 220),
}

PYTHON_KEYWORDS = {
    "def", "class", "if", "else", "elif", "for", "while", "return", "import",
    "from", "try", "except", "finally", "with", "as", "pass", "break",
    "continue", "and", "or", "not", "in", "is", "None", "True", "False",
    "lambda", "yield", "async", "await", "global", "nonlocal",
}

BUILTIN_NAMES = {
    "run", "move", "collect", "measure", "can_collect", "upgrade", "till", "plant", "print",
    "get_position", "get_nearby", "get_purchasable", "get_map_size", "get_ground",
    "East", "West", "North", "South",
    "Ground", "Grassland", "Sandyland",
    "Entities", "Entity", "Grass", "Stone", "Bush", "Tree",
}

# Python 内置函数（与游戏 API 使用相同 builtin 颜色）
PYTHON_BUILTINS = {
    "range", "len", "str", "int", "float", "list", "dict", "set", "tuple",
    "abs", "min", "max", "sum", "sorted", "reversed", "enumerate", "zip",
    "map", "filter", "any", "all", "round", "bool", "type", "isinstance",
    "open", "input", "print", "format", "repr", "chr", "ord",
}

ALL_BUILTINS = BUILTIN_NAMES | PYTHON_BUILTINS


def _extract_user_def_names(lines: List[str]) -> set:
    """从代码中提取 def/class 定义的名称"""
    names = set()
    for line in lines:
        s = line.strip()
        if s.startswith("def "):
            # def func_name( 或 def func_name:
            rest = s[4:].lstrip()
            for i, c in enumerate(rest):
                if c in "(:":
                    name = rest[:i].strip()
                    if name and name.replace("_", "").isalnum():
                        names.add(name)
                    break
        elif s.startswith("class "):
            rest = s[6:].lstrip()
            for i, c in enumerate(rest):
                if c in "(:":
                    name = rest[:i].strip()
                    if name and name.replace("_", "").isalnum():
                        names.add(name)
                    break
    return names


def _extract_user_var_names(lines: List[str], module_level_only: bool = True) -> set:
    """从代码中提取变量名。module_level_only=True 时仅提取模块级变量，函数内局部变量不参与全局高亮/补全。"""
    names = set()
    skip = PYTHON_KEYWORDS | ALL_BUILTINS
    for line in lines:
        if module_level_only and line != line.lstrip() and line.strip():
            continue
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("def ") or s.startswith("class "):
            continue
        # for x in ... 或 for i, x in ...
        if s.startswith("for "):
            rest = s[4:].strip()
            if " in " in rest:
                targets = rest.split(" in ", 1)[0].strip()
                for part in targets.replace("(", " ").replace(")", " ").replace(",", " ").split():
                    name = part.strip()
                    if name and name.replace("_", "").isalnum() and name not in skip:
                        names.add(name)
        # x = ... 或 x, y = ...（排除 ==、!= 等比较）
        elif " = " in s and "==" not in s and "!=" not in s:
            lhs = s.split(" = ", 1)[0].strip()
            if lhs and not lhs.endswith(("!", "<", ">", "+", "-", "*", "/", "&", "|")):
                for part in lhs.replace("(", " ").replace(")", " ").replace(",", " ").replace("[", " ").replace("]", " ").split():
                    name = part.strip()
                    if name and name.replace("_", "").isalnum() and name not in skip:
                        names.add(name)
    return names


def _highlight_python_line(line: str, font, default_color: tuple, user_def_names: Optional[set] = None) -> List[Tuple[str, tuple]]:
    """将一行解析为 (文本片段, 颜色) 列表"""
    user_def_names = user_def_names or set()
    result = []
    i = 0
    n = len(line)

    while i < n:
        if line[i] == "#":
            result.append((line[i:], PYTHON_HIGHLIGHT["comment"]))
            break
        if line[i] == '"':
            j = i + 1
            while j < n:
                if line[j] == '\\':
                    j += 2
                    continue
                if line[j] == '"':
                    j += 1
                    break
                j += 1
            result.append((line[i:j], PYTHON_HIGHLIGHT["string"]))
            i = j
            continue
        if line[i] == "'":
            j = i + 1
            while j < n:
                if line[j] == '\\':
                    j += 2
                    continue
                if line[j] == "'":
                    j += 1
                    break
                j += 1
            result.append((line[i:j], PYTHON_HIGHLIGHT["string"]))
            i = j
            continue
        if line[i:i+3] in ('"""', "'''"):
            q = line[i:i+3]
            j = i + 3
            while j <= n - 3 and line[j:j+3] != q:
                if line[j] == '\\':
                    j += 1
                j += 1
            j = min(n, j + 3)
            result.append((line[i:j], PYTHON_HIGHLIGHT["string"]))
            i = j
            continue
        if line[i].isdigit():
            j = i
            while j < n and (line[j].isdigit() or line[j] == '.'):
                j += 1
            result.append((line[i:j], PYTHON_HIGHLIGHT["number"]))
            i = j
            continue
        if line[i].isalpha() or line[i] == '_':
            j = i
            while j < n and (line[j].isalnum() or line[j] == '_'):
                j += 1
            word = line[i:j]
            color = PYTHON_HIGHLIGHT["keyword"] if word in PYTHON_KEYWORDS else default_color
            if word in ALL_BUILTINS:
                color = PYTHON_HIGHLIGHT["builtin"]
            elif word in user_def_names:
                color = PYTHON_HIGHLIGHT["user_def"]
            result.append((word, color))
            i = j
            continue
        result.append((line[i], default_color))
        i += 1
    return result


def _normalize_selection(r1: int, c1: int, r2: int, c2: int) -> Tuple[int, int, int, int]:
    """保证 start <= end"""
    if (r1, c1) <= (r2, c2):
        return r1, c1, r2, c2
    return r2, c2, r1, c1


class CodeEditor:
    """代码编辑器 - 行号、语法高亮、撤销、复制粘贴、点击定位、横竖滚动"""

    LINE_NUM_WIDTH = 40
    SCROLLBAR_W = 10
    UNDO_LIMIT = 50

    def __init__(self, font, line_height: int = 26, tab_width: int = 4):
        self.font = font
        self.line_height = line_height
        self.tab_width = tab_width
        self.lines: List[str] = [""]
        self.cursor_row = 0
        self.cursor_col = 0
        self.scroll_y = 0
        self.scroll_x = 0
        self._cursor_blink = 0
        # 选区: (start_row, start_col, end_row, end_col) 或 None
        self._selection: Optional[Tuple[int, int, int, int]] = None
        self._undo_stack: List[Tuple[List[str], int, int]] = []
        self._last_saved_state: Optional[Tuple[List[str], int, int]] = None
        self._project_files: Dict[str, str] = {}
        self._current_filename: str = "main.py"
        # 代码补全
        self._completion_visible = False
        self._completion_matches: List[str] = []
        self._completion_index = 0
        self._cursor_moved_by_user = False

    def set_text(self, text: str) -> None:
        self.lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if not self.lines:
            self.lines = [""]
        self.cursor_row = min(self.cursor_row, len(self.lines) - 1)
        self.cursor_col = min(self.cursor_col, len(self.lines[self.cursor_row]))
        self.scroll_y = 0
        self.scroll_x = 0
        self._selection = None
        self._undo_stack.clear()
        self._cursor_moved_by_user = False
        self._push_undo()

    def get_text(self) -> str:
        return "\n".join(self.lines)

    def scroll(self, delta_y: int = 0, delta_x: int = 0, visible_lines: int = 15, visible_width: int = 400) -> None:
        """滚轮滚动，delta_y/delta_x 来自 event.y/event.x"""
        max_y = max(0, len(self.lines) - visible_lines)
        self.scroll_y = max(0, min(max_y, int(self.scroll_y - delta_y * 3)))
        max_x = max(0, self._max_line_width_px() - visible_width)
        self.scroll_x = max(0, min(max_x, int(self.scroll_x - delta_x * 3)))

    def _max_line_width_px(self) -> int:
        """当前所有行最大像素宽度"""
        if not self.lines:
            return 0
        return max(self.font.size(line[:1000])[0] for line in self.lines)

    def _push_undo(self) -> None:
        state = ([s for s in self.lines], self.cursor_row, self.cursor_col)
        if self._undo_stack and self._undo_stack[-1][0] == state[0]:
            return
        self._undo_stack.append(state)
        if len(self._undo_stack) > self.UNDO_LIMIT:
            self._undo_stack.pop(0)

    def _pop_undo(self) -> bool:
        if len(self._undo_stack) < 2:
            return False
        self._undo_stack.pop()  # 当前状态
        prev = self._undo_stack[-1]
        self.lines = [s for s in prev[0]]
        self.cursor_row = prev[1]
        self.cursor_col = prev[2]
        self._selection = None
        return True

    def _clamp_cursor(self) -> None:
        self.cursor_row = max(0, min(self.cursor_row, len(self.lines) - 1))
        self.cursor_col = max(0, min(self.cursor_col, len(self.lines[self.cursor_row])))

    def _ensure_line(self) -> None:
        while len(self.lines) <= self.cursor_row:
            self.lines.append("")

    def _get_selection_text(self) -> str:
        if not self._selection:
            return ""
        r1, c1, r2, c2 = _normalize_selection(*self._selection)
        if r1 == r2:
            return self.lines[r1][c1:c2]
        parts = [self.lines[r1][c1:]]
        for r in range(r1 + 1, r2):
            parts.append(self.lines[r])
        parts.append(self.lines[r2][:c2])
        return "\n".join(parts)

    def _delete_selection(self) -> str:
        if not self._selection:
            return ""
        r1, c1, r2, c2 = _normalize_selection(*self._selection)
        text = self._get_selection_text()
        if r1 == r2:
            self.lines[r1] = self.lines[r1][:c1] + self.lines[r1][c2:]
        else:
            merged = self.lines[r1][:c1] + self.lines[r2][c2:]
            self.lines[r1] = merged
            for _ in range(r2 - r1):
                self.lines.pop(r1 + 1)
        self.cursor_row, self.cursor_col = r1, c1
        self._selection = None
        return text

    def _select_all(self) -> None:
        self._selection = (0, 0, len(self.lines) - 1, len(self.lines[-1]))

    def _get_prefix_at_cursor(self) -> Tuple[str, int]:
        """返回光标前的标识符前缀及起始列。若不在标识符中则返回 ("", cursor_col)"""
        line = self.lines[self.cursor_row]
        c = self.cursor_col
        if c <= 0:
            return ("", 0)
        j = c - 1
        while j >= 0 and (line[j].isalnum() or line[j] == "_"):
            j -= 1
        prefix = line[j + 1 : c]
        return (prefix, j + 1)

    def set_project_files(self, files: Dict[str, str], current_file: str) -> None:
        """设置项目内所有文件，用于跨文件补全和高亮。current_file 为当前正在编辑的文件名。"""
        self._project_files = files or {}
        self._current_filename = current_file

    def _get_all_user_def_names(self) -> set:
        """从当前文件及项目内其他 .py 文件提取 def/class 定义的名称"""
        names = set()
        files = self._project_files or {}
        cur = getattr(self, "_current_filename", "main.py")
        for fname, content in files.items():
            if not fname.endswith(".py"):
                continue
            if fname == cur:
                lines = self.lines
            else:
                lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n") if content else [""]
            names |= _extract_user_def_names(lines)
        if not files:
            names |= _extract_user_def_names(self.lines)
        return names

    def _get_all_user_var_names(self) -> set:
        """从当前文件及项目内其他 .py 文件提取赋值/for 循环中的变量名"""
        names = set()
        files = self._project_files or {}
        cur = getattr(self, "_current_filename", "main.py")
        for fname, content in files.items():
            if not fname.endswith(".py"):
                continue
            if fname == cur:
                lines = self.lines
            else:
                lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n") if content else [""]
            names |= _extract_user_var_names(lines)
        if not files:
            names |= _extract_user_var_names(self.lines)
        return names

    def _get_module_names(self) -> set:
        """获取项目内 .py 文件的模块名（不含后缀），用于 import 补全"""
        files = self._project_files or {}
        return {fname[:-3] for fname in files if fname.endswith(".py")}

    def _get_completion_candidates(self) -> set:
        """获取所有补全候选（关键字、内置API、Python 内置、自定义函数/类/变量、模块名）"""
        user = self._get_all_user_def_names() | self._get_all_user_var_names()
        modules = self._get_module_names()
        return PYTHON_KEYWORDS | ALL_BUILTINS | user | modules

    def _update_completion(self, force: bool = False) -> None:
        """根据当前前缀更新补全列表。force=True 时无前缀也显示全部"""
        prefix, start_col = self._get_prefix_at_cursor()
        if not force and not prefix:
            self._completion_visible = False
            return
        candidates = self._get_completion_candidates()
        if force and not prefix:
            matches = sorted(candidates)
        else:
            matches = sorted(s for s in candidates if s.startswith(prefix))
        if not matches:
            self._completion_visible = False
            return
        self._completion_matches = matches
        self._completion_index = 0
        self._completion_visible = True

    def _hide_completion(self) -> None:
        self._completion_visible = False

    def _apply_completion(self) -> bool:
        """应用当前选中的补全项，返回是否已应用"""
        if not self._completion_visible or not self._completion_matches:
            return False
        prefix, start_col = self._get_prefix_at_cursor()
        chosen = self._completion_matches[self._completion_index]
        line = self.lines[self.cursor_row]
        self.lines[self.cursor_row] = line[:start_col] + chosen + line[self.cursor_col :]
        self.cursor_col = start_col + len(chosen)
        self._hide_completion()
        return True

    def handle_click(self, pos: Tuple[int, int], rect: pygame.Rect) -> bool:
        """点击定位光标，返回是否在编辑区内"""
        if not rect.collidepoint(pos):
            return False
        self._hide_completion()
        self._selection = None
        text_left = rect.x + self.LINE_NUM_WIDTH + 4
        if pos[0] < text_left:
            pos = (text_left, pos[1])
        rel_y = pos[1] - rect.y
        rel_x = pos[0] - text_left + self.scroll_x  # 加上 scroll_x 得到内容坐标
        row = self.scroll_y + rel_y // self.line_height
        row = max(0, min(row, len(self.lines) - 1))
        line = self.lines[row]
        col = 0
        x = 0
        for i, ch in enumerate(line):
            w = self.font.size(ch)[0]
            if x + w // 2 > rel_x:
                break
            col = i + 1
            x += w
        else:
            col = len(line)
        self.cursor_row = row
        self.cursor_col = col
        self._cursor_moved_by_user = True
        return True

    def handle_key(self, event: pygame.event.Event) -> bool:
        global _clipboard
        if event.type != pygame.KEYDOWN:
            return False

        mods = pygame.key.get_mods()
        mod_key = pygame.KMOD_META if sys.platform == "darwin" else pygame.KMOD_CTRL
        ctrl = mods & mod_key
        shift = mods & pygame.KMOD_SHIFT

        self._ensure_line()
        line = self.lines[self.cursor_row]

        # 补全面板打开时：Tab/Enter 应用，Up/Down 选择，Escape 关闭
        if self._completion_visible:
            if event.key == pygame.K_TAB and not shift:
                if self._apply_completion():
                    self._cursor_moved_by_user = True
                    return True
            if event.key == pygame.K_RETURN:
                if self._apply_completion():
                    self._cursor_moved_by_user = True
                    return True
            if event.key == pygame.K_UP:
                self._completion_index = (self._completion_index - 1) % len(self._completion_matches)
                return True
            if event.key == pygame.K_DOWN:
                self._completion_index = (self._completion_index + 1) % len(self._completion_matches)
                return True
            if event.key == pygame.K_ESCAPE:
                self._hide_completion()
                return True

        # Ctrl+Space 手动触发补全
        if ctrl and event.key == pygame.K_SPACE:
            self._update_completion(force=True)
            return True

        # 光标移动时关闭补全
        if event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN, pygame.K_HOME, pygame.K_END):
            self._hide_completion()

        # Ctrl+Z 撤销
        if ctrl and event.key == pygame.K_z and not shift:
            if self._pop_undo():
                self._cursor_moved_by_user = True
                return True

        # Ctrl+C 复制
        if ctrl and event.key == pygame.K_c:
            if self._selection:
                _clipboard = self._get_selection_text()
            else:
                _clipboard = line + "\n" if line else "\n"
            return True

        # Ctrl+X 剪切
        if ctrl and event.key == pygame.K_x:
            self._push_undo()
            if self._selection:
                _clipboard = self._delete_selection()
            else:
                _clipboard = line + "\n" if line else "\n"
                self.lines[self.cursor_row] = ""
                self.cursor_col = 0
            self._cursor_moved_by_user = True
            return True

        # Ctrl+V 粘贴
        if ctrl and event.key == pygame.K_v:
            if not _clipboard:
                return True
            self._push_undo()
            self._hide_completion()
            if self._selection:
                self._delete_selection()
            lines = _clipboard.replace("\r\n", "\n").replace("\r", "\n").split("\n")
            if len(lines) == 1:
                self.lines[self.cursor_row] = line[: self.cursor_col] + lines[0] + line[self.cursor_col :]
                self.cursor_col += len(lines[0])
            else:
                self.lines[self.cursor_row] = line[: self.cursor_col] + lines[0]
                for i in range(1, len(lines)):
                    self.lines.insert(self.cursor_row + i, lines[i])
                self.lines[self.cursor_row + len(lines) - 1] += line[self.cursor_col :]
                self.cursor_row += len(lines) - 1
                self.cursor_col = len(lines[-1])
            self._cursor_moved_by_user = True
            return True

        # Ctrl+A 全选
        if ctrl and event.key == pygame.K_a:
            self._select_all()
            return True

        # Ctrl+Home / Ctrl+End
        if ctrl and event.key == pygame.K_HOME:
            self.cursor_row = 0
            self.cursor_col = 0
            self._selection = None
            self._cursor_moved_by_user = True
            return True
        if ctrl and event.key == pygame.K_END:
            self.cursor_row = len(self.lines) - 1
            self.cursor_col = len(self.lines[-1])
            self._selection = None
            self._cursor_moved_by_user = True
            return True

        # Home / End (行首行尾)
        if event.key == pygame.K_HOME:
            self.cursor_col = 0
            self._cursor_moved_by_user = True
            return True
        if event.key == pygame.K_END:
            self.cursor_col = len(line)
            self._cursor_moved_by_user = True
            return True

        # Shift+Tab 减少缩进
        if shift and event.key == pygame.K_TAB:
            self._push_undo()
            indent = len(line) - len(line.lstrip())
            if indent > 0:
                remove = min(self.tab_width, indent, self.cursor_col)
                new_line = line[remove:] if remove <= len(line) else line
                self.lines[self.cursor_row] = new_line
                self.cursor_col = max(0, self.cursor_col - remove)
            self._cursor_moved_by_user = True
            return True

        # Backspace/Delete：有选区时删除选区
        if event.key in (pygame.K_BACKSPACE, pygame.K_DELETE) and self._selection:
            self._push_undo()
            self._delete_selection()
            self._hide_completion()
            self._cursor_moved_by_user = True
            return True

        # 常规编辑
        self._selection = None

        if event.key == pygame.K_BACKSPACE:
            self._push_undo()
            if self.cursor_col > 0:
                self.lines[self.cursor_row] = line[: self.cursor_col - 1] + line[self.cursor_col :]
                self.cursor_col -= 1
                self._update_completion()
            elif self.cursor_row > 0:
                self.cursor_col = len(self.lines[self.cursor_row - 1])
                self.lines[self.cursor_row - 1] += self.lines[self.cursor_row]
                self.lines.pop(self.cursor_row)
                self.cursor_row -= 1
            self._cursor_moved_by_user = True
            return True

        if event.key == pygame.K_DELETE:
            self._push_undo()
            if self.cursor_col < len(line):
                self.lines[self.cursor_row] = line[: self.cursor_col] + line[self.cursor_col + 1 :]
                self._update_completion()
            elif self.cursor_row < len(self.lines) - 1:
                self.lines[self.cursor_row] += self.lines.pop(self.cursor_row + 1)
            self._cursor_moved_by_user = True
            return True

        if event.key == pygame.K_RETURN:
            self._push_undo()
            self._hide_completion()
            prefix = line[: self.cursor_col]
            rest = line[self.cursor_col :]
            self.lines[self.cursor_row] = prefix
            base_indent = len(prefix) - len(prefix.lstrip())
            extra = self.tab_width if prefix.rstrip().endswith(":") else 0
            next_indent = " " * (base_indent + extra)
            self.lines.insert(self.cursor_row + 1, next_indent + rest.lstrip())
            self.cursor_row += 1
            self.cursor_col = len(next_indent)
            self._cursor_moved_by_user = True
            return True

        if event.key == pygame.K_TAB and not shift:
            insert = " " * (self.tab_width - self.cursor_col % self.tab_width)
            self.lines[self.cursor_row] = line[: self.cursor_col] + insert + line[self.cursor_col :]
            self.cursor_col += len(insert)
            self._cursor_moved_by_user = True
            return True

        if event.key == pygame.K_LEFT:
            if self.cursor_col > 0:
                self.cursor_col -= 1
            elif self.cursor_row > 0:
                self.cursor_row -= 1
                self.cursor_col = len(self.lines[self.cursor_row])
            self._cursor_moved_by_user = True
            return True

        if event.key == pygame.K_RIGHT:
            if self.cursor_col < len(line):
                self.cursor_col += 1
            elif self.cursor_row < len(self.lines) - 1:
                self.cursor_row += 1
                self.cursor_col = 0
            self._cursor_moved_by_user = True
            return True

        if event.key == pygame.K_UP:
            if self.cursor_row > 0:
                self.cursor_row -= 1
                self.cursor_col = min(self.cursor_col, len(self.lines[self.cursor_row]))
            self._cursor_moved_by_user = True
            return True

        if event.key == pygame.K_DOWN:
            if self.cursor_row < len(self.lines) - 1:
                self.cursor_row += 1
                self.cursor_col = min(self.cursor_col, len(self.lines[self.cursor_row]))
            self._cursor_moved_by_user = True
            return True

        if event.unicode and event.unicode.isprintable():
            self._push_undo()
            self.lines[self.cursor_row] = line[: self.cursor_col] + event.unicode + line[self.cursor_col :]
            self.cursor_col += 1
            # 输入字母或下划线时自动触发补全
            if event.unicode.isalpha() or event.unicode == "_":
                self._update_completion()
            else:
                self._hide_completion()
            self._cursor_moved_by_user = True
            return True

        return False

    def render(self, surface: pygame.Surface, rect: pygame.Rect, colors: dict, visible_lines: int, highlight: bool = True) -> None:
        bg = colors.get("bg", (22, 25, 30))
        border = colors.get("border", (58, 64, 78))
        pygame.draw.rect(surface, bg, rect, border_radius=4)
        pygame.draw.rect(surface, border, rect, 2, border_radius=4)

        sb = self.SCROLLBAR_W
        max_line_w = self._max_line_width_px()
        content_w = rect.w - self.LINE_NUM_WIDTH - sb - 8
        content_h = rect.h - sb - 8
        need_h_scroll = max_line_w > content_w
        if not need_h_scroll:
            content_h = rect.h - 8
        effective_visible = max(1, content_h // self.line_height)
        need_v_scroll = len(self.lines) > effective_visible
        if not need_v_scroll:
            content_w = rect.w - self.LINE_NUM_WIDTH - 8

        ln_color = colors.get("line_num", (95, 102, 118))
        ln_bg = colors.get("line_num_bg", (28, 30, 38))
        default_color = colors.get("text", (225, 228, 235))
        text_left = rect.x + self.LINE_NUM_WIDTH + 4

        self._clamp_cursor()
        self._cursor_blink = (self._cursor_blink + 1) % 60

        # 滚动范围限制：确保不超出最后一行的可见
        max_scroll_y = max(0, len(self.lines) - effective_visible)
        self.scroll_y = min(max_scroll_y, max(0, self.scroll_y))
        # 仅在用户编辑/移动光标时自动翻页跟随，滚轮翻页时不强制
        if self._cursor_moved_by_user:
            self._cursor_moved_by_user = False
            if self.cursor_row < int(self.scroll_y):
                self.scroll_y = float(self.cursor_row)
            elif self.cursor_row >= int(self.scroll_y) + effective_visible:
                self.scroll_y = float(self.cursor_row - effective_visible + 1)

        first_visible = int(self.scroll_y)
        last_visible = min(first_visible + effective_visible, len(self.lines))

        # 行号背景
        ln_h = rect.h - (sb if need_h_scroll else 0)
        ln_rect = pygame.Rect(rect.x + 2, rect.y + 2, self.LINE_NUM_WIDTH - 2, ln_h - 4)
        pygame.draw.rect(surface, ln_bg, ln_rect, border_radius=3)
        pygame.draw.line(surface, (52, 56, 68), (rect.x + self.LINE_NUM_WIDTH, rect.y + 4), (rect.x + self.LINE_NUM_WIDTH, ln_rect.bottom))

        # 代码内容区：裁剪，防止绘制到编辑器外
        content_rect = pygame.Rect(rect.x + self.LINE_NUM_WIDTH + 4, rect.y + 4, content_w, content_h)
        surface.set_clip(content_rect)

        for i in range(first_visible, last_visible):
            line = self.lines[i]
            y = rect.y + 4 + (i - first_visible) * self.line_height
            if y + self.line_height > content_rect.bottom:
                break

            # 行号
            ln_txt = self.font.render(str(i + 1), True, ln_color)
            surface.blit(ln_txt, (rect.x + self.LINE_NUM_WIDTH - ln_txt.get_width() - 6, y))

            # 代码行（应用 scroll_x，仅绘制可见部分）
            x = text_left - self.scroll_x
            if highlight:
                user_names = self._get_all_user_def_names() | self._get_all_user_var_names() | self._get_module_names()
                tokens = _highlight_python_line(line, self.font, default_color, user_names)
                for chunk, c in tokens:
                    if chunk:
                        txt = self.font.render(chunk, True, c)
                        surface.blit(txt, (x, y))
                        x += txt.get_width()
            else:
                txt = self.font.render(line, True, default_color)
                surface.blit(txt, (x, y))
                x += txt.get_width()

            # 选区高亮
            if self._selection:
                r1, c1, r2, c2 = _normalize_selection(*self._selection)
                if r1 <= i <= r2:
                    start_c = c1 if i == r1 else 0
                    end_c = c2 if i == r2 else len(line)
                    if start_c < end_c:
                        pre = line[:start_c]
                        sel = line[start_c:end_c]
                        sw = self.font.size(pre)[0]
                        sel_w = self.font.size(sel)[0]
                        sel_rect = pygame.Rect(text_left + sw - self.scroll_x, y, sel_w, self.line_height - 2)
                        s = pygame.Surface((sel_w, self.line_height - 2))
                        sc = colors.get("selection", (60, 100, 160, 100))
                        s.set_alpha(sc[3] if len(sc) > 3 else 100)
                        s.fill(sc[:3] if len(sc) >= 3 else (80, 120, 180))
                        surface.blit(s, sel_rect)

            # 光标
            if i == self.cursor_row and self._cursor_blink < 30:
                pre = line[: self.cursor_col]
                cw = self.font.size(pre)[0]
                cx = text_left + cw - self.scroll_x
                cy = y + self.line_height - 2
                if content_rect.x <= cx <= content_rect.right:
                    pygame.draw.line(surface, (255, 255, 255), (cx, y + 2), (cx, cy), 2)

        surface.set_clip(None)

        # 补全提示弹窗
        if self._completion_visible and self._completion_matches:
            line = self.lines[self.cursor_row]
            cursor_x = text_left + self.font.size(line[: self.cursor_col])[0] - self.scroll_x
            if first_visible <= self.cursor_row < last_visible:
                popup_y = rect.y + 4 + (self.cursor_row - first_visible + 1) * self.line_height
            else:
                popup_y = rect.y + 4 + effective_visible * self.line_height
            max_items = min(8, len(self._completion_matches))
            item_h = self.line_height
            popup_h = max_items * item_h + 8
            # 确保选中项在可见范围内
            start_idx = max(0, min(self._completion_index, len(self._completion_matches) - max_items))
            visible_matches = self._completion_matches[start_idx : start_idx + max_items]
            popup_w = max(120, max(self.font.size(m)[0] for m in visible_matches) + 24)
            popup_x = min(max(rect.x + self.LINE_NUM_WIDTH, cursor_x - 4), rect.right - popup_w - self.SCROLLBAR_W)
            if popup_y + popup_h > rect.bottom - sb:
                popup_y = rect.y + 4 + (self.cursor_row - first_visible) * self.line_height - popup_h if first_visible <= self.cursor_row < last_visible else rect.bottom - popup_h - sb - 4
            popup_rect = pygame.Rect(popup_x, popup_y, popup_w, popup_h)
            cp_bg = colors.get("completion_bg", (32, 36, 46))
            cp_border = colors.get("completion_border", (68, 75, 92))
            cp_hl = colors.get("completion_highlight", (55, 62, 78))
            pygame.draw.rect(surface, cp_bg, popup_rect, border_radius=4)
            pygame.draw.rect(surface, cp_border, popup_rect, 2, border_radius=4)
            for i, item in enumerate(visible_matches):
                idx = start_idx + i
                color = (240, 242, 250) if idx == self._completion_index else (200, 208, 222)
                if idx == self._completion_index:
                    pygame.draw.rect(surface, cp_hl, (popup_x + 4, popup_y + 4 + i * item_h, popup_w - 8, item_h - 2), border_radius=3)
                txt = self.font.render(item, True, color)
                surface.blit(txt, (popup_x + 8, popup_y + 4 + i * item_h))

        sb_bg = colors.get("scrollbar", (45, 48, 58))
        sb_thumb = colors.get("scrollbar_thumb", (82, 90, 108))
        v_sb_bottom = rect.bottom - (sb if need_h_scroll else 0)
        if need_v_scroll:
            thumb_h = max(24, int((v_sb_bottom - rect.y) * effective_visible / len(self.lines)))
            thumb_y = rect.y + int((v_sb_bottom - rect.y - thumb_h) * self.scroll_y / max(1, len(self.lines) - effective_visible))
            sb_x = rect.right - sb
            pygame.draw.rect(surface, sb_bg, (sb_x + 1, rect.y + 2, sb - 2, v_sb_bottom - rect.y - 4), border_radius=3)
            pygame.draw.rect(surface, sb_thumb, (sb_x + 2, thumb_y + 2, sb - 4, thumb_h - 4), border_radius=3)

        if need_h_scroll:
            h_sb_right = rect.right - (sb if need_v_scroll else 0)
            thumb_w = max(48, int((h_sb_right - rect.x) * content_w / max(1, max_line_w)))
            thumb_x = rect.x + int((h_sb_right - rect.x - thumb_w) * self.scroll_x / max(1, max_line_w - content_w))
            sb_y = rect.bottom - sb
            pygame.draw.rect(surface, sb_bg, (rect.x + 2, sb_y + 1, h_sb_right - rect.x - 4, sb - 2), border_radius=3)
            pygame.draw.rect(surface, sb_thumb, (thumb_x + 2, sb_y + 2, thumb_w - 4, sb - 4), border_radius=3)


class EditorPanel:
    """可拖动、可调整大小、可最小化的编辑器面板"""

    MIN_W, MIN_H = 320, 140
    TITLE_H = 28
    RESIZE_HANDLE = 14
    MINIMIZED_H = 36

    def __init__(self, screen_w: int, screen_h: int):
        # 默认布局与存档1一致：右侧堆叠
        self.w = 641
        self.x = min(829, screen_w - self.w - 20)
        self.y = 15
        self.h = min(427, screen_h - 80)
        self.minimized = False
        self._drag_mode = None
        self._drag_start = (0, 0)
        self._drag_rect_start = (0, 0, 0, 0)

    def rect(self) -> pygame.Rect:
        if self.minimized:
            return pygame.Rect(self.x, self.y, self.w, self.MINIMIZED_H)
        return pygame.Rect(self.x, self.y, self.w, self.h)

    def content_rect(self) -> pygame.Rect:
        r = self.rect()
        return pygame.Rect(r.x, r.y + self.TITLE_H, r.w, r.h - self.TITLE_H)

    def title_rect(self) -> pygame.Rect:
        return pygame.Rect(self.x, self.y, self.w, self.TITLE_H)

    def resize_handle_rect(self) -> pygame.Rect:
        return pygame.Rect(self.x + self.w - self.RESIZE_HANDLE, self.y + self.h - self.RESIZE_HANDLE, self.RESIZE_HANDLE, self.RESIZE_HANDLE)

    def minmax_button_rect(self) -> pygame.Rect:
        return pygame.Rect(self.x + self.w - 50, self.y + 6, 40, 20)

    def clamp_to_screen(self, screen_w: int, screen_h: int) -> None:
        self.x = max(0, min(self.x, screen_w - 100))
        self.y = max(0, min(self.y, screen_h - 80))
        self.w = max(self.MIN_W, min(self.w, screen_w - self.x))
        self.h = max(self.MIN_H, min(self.h, screen_h - self.y - 20))

    def handle_mousedown(self, pos: tuple, screen_w: int, screen_h: int) -> bool:
        if not self.rect().collidepoint(pos):
            return False
        if self.minmax_button_rect().collidepoint(pos):
            self.minimized = not self.minimized
            return True
        if self.minimized:
            self._drag_mode = "move"
            self._drag_start = pos
            self._drag_rect_start = (self.x, self.y, self.w, self.h)
            return True
        if self.resize_handle_rect().collidepoint(pos):
            self._drag_mode = "resize"
            self._drag_start = pos
            self._drag_rect_start = (self.x, self.y, self.w, self.h)
            return True
        if not self.minimized and self.title_rect().collidepoint(pos):
            self._drag_mode = "move"
            self._drag_start = pos
            self._drag_rect_start = (self.x, self.y, self.w, self.h)
        return True

    def handle_mousemotion(self, pos: tuple) -> None:
        if self._drag_mode == "move":
            dx = pos[0] - self._drag_start[0]
            dy = pos[1] - self._drag_start[1]
            self.x = self._drag_rect_start[0] + dx
            self.y = self._drag_rect_start[1] + dy
        elif self._drag_mode == "resize":
            dx = pos[0] - self._drag_start[0]
            dy = pos[1] - self._drag_start[1]
            self.w = max(self.MIN_W, self._drag_rect_start[2] + dx)
            self.h = max(self.MIN_H, self._drag_rect_start[3] + dy)

    def handle_mouseup(self) -> None:
        self._drag_mode = None

    def is_dragging(self) -> bool:
        return self._drag_mode is not None
