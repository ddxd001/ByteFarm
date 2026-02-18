"""
终端界面 - 显示玩家代码的 print 输出与运行报错
"""

import threading
from typing import List, Optional
import pygame


class TerminalBuffer:
    """线程安全的终端输出缓冲"""
    
    def __init__(self, max_lines: int = 500):
        self._lines: List[str] = []
        self._lock = threading.Lock()
        self._max_lines = max_lines
        self._partial = ""  # 未换行结尾的片段
    
    def write(self, text: str) -> None:
        """写入文本（支持多行，兼容 print），线程安全"""
        if not text:
            return
        with self._lock:
            text = self._partial + text
            self._partial = ""
            parts = text.split("\n")
            if not text.endswith("\n"):
                self._partial = parts.pop() if parts else ""
            for line in parts:
                self._lines.append(line)
            while len(self._lines) > self._max_lines:
                self._lines.pop(0)
    
    def append_line(self, line: str) -> None:
        """追加一行"""
        with self._lock:
            self._lines.append(line)
            while len(self._lines) > self._max_lines:
                self._lines.pop(0)
    
    def get_lines(self) -> List[str]:
        """获取当前所有行，线程安全"""
        with self._lock:
            return list(self._lines)
    
    def clear(self) -> None:
        """清空"""
        with self._lock:
            self._lines.clear()
    
    def __len__(self) -> int:
        with self._lock:
            return len(self._lines)


class TerminalPanel:
    """可拖动、可调整大小、可最小化的终端面板"""
    
    MIN_W, MIN_H = 320, 120
    TITLE_H = 28
    RESIZE_HANDLE = 24  # 伸缩把手大小，便于拖动
    MINIMIZED_H = 36
    LINE_HEIGHT = 20
    PADDING = 8
    SCROLLBAR_W = 12
    
    def __init__(self, font: pygame.font.Font, screen_w: int, screen_h: int):
        self.font = font
        self.x = 330  # 在左下角信息框(10,300)右侧，避免遮挡
        self.y = screen_h - 230  # 位于底部 UI 上方
        self.w = 480
        self.h = min(180, screen_h - 120)
        self.minimized = False
        self._drag_mode = None
        self._drag_start = (0, 0)
        self._drag_rect_start = (0, 0, 0, 0)
        self._scroll_offset = 0
        self._last_line_count = 0
        self._buffer: Optional[TerminalBuffer] = None
    
    def set_buffer(self, buffer: TerminalBuffer) -> None:
        self._buffer = buffer
    
    def rect(self) -> pygame.Rect:
        if self.minimized:
            return pygame.Rect(self.x, self.y, self.w, self.MINIMIZED_H)
        return pygame.Rect(self.x, self.y, self.w, self.h)
    
    def content_rect(self) -> pygame.Rect:
        r = self.rect()
        return pygame.Rect(r.x + self.PADDING, r.y + self.TITLE_H + self.PADDING,
                          r.w - self.PADDING * 2 - self.SCROLLBAR_W,
                          r.h - self.TITLE_H - self.PADDING * 2)
    
    def title_rect(self) -> pygame.Rect:
        return pygame.Rect(self.x, self.y, self.w, self.TITLE_H)
    
    def resize_handle_rect(self) -> pygame.Rect:
        """右下角伸缩把手"""
        return pygame.Rect(self.x + self.w - self.RESIZE_HANDLE,
                          self.y + self.h - self.RESIZE_HANDLE,
                          self.RESIZE_HANDLE, self.RESIZE_HANDLE)
    
    def in_resize_zone(self, pos: tuple) -> bool:
        """鼠标是否在可伸缩区域（右下角+右边缘+底边缘）"""
        if self.minimized:
            return False
        px, py = pos
        # 右边缘 20px 或 底边缘 20px 或 右下角
        right_zone = px >= self.x + self.w - 20 and self.y <= py <= self.y + self.h
        bottom_zone = py >= self.y + self.h - 20 and self.x <= px <= self.x + self.w
        return right_zone or bottom_zone
    
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
        if self.in_resize_zone(pos):
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
    
    def scroll(self, dy: int) -> None:
        """滚轮滚动"""
        if self.minimized or not self._buffer:
            return
        lines = self._buffer.get_lines()
        content = self.content_rect()
        visible_lines = max(1, content.h // self.LINE_HEIGHT)
        max_offset = max(0, len(lines) - visible_lines)
        self._scroll_offset = max(0, min(self._scroll_offset - dy, max_offset))
    
    def render(self, surface: pygame.Surface) -> None:
        """渲染终端面板"""
        r = self.rect()
        # 背景
        pygame.draw.rect(surface, (28, 30, 36), r)
        pygame.draw.rect(surface, (70, 75, 90), r, 2)
        # 标题
        title = self.font.render("OUTPUT", True, (220, 225, 235))
        surface.blit(title, (r.x + 10, r.y + 4))
        # 最小化/展开
        if self.minimized:
            btn_rect = self.minmax_button_rect()
            pygame.draw.rect(surface, (70, 90, 120), btn_rect)
            txt = self.font.render("展开", True, (255, 255, 255))
            surface.blit(txt, (btn_rect.x + (btn_rect.w - txt.get_width()) // 2, btn_rect.y + 2))
            return
        btn_rect = self.minmax_button_rect()
        pygame.draw.rect(surface, (60, 70, 90), btn_rect)
        txt = self.font.render("-", True, (255, 255, 255))
        surface.blit(txt, (btn_rect.x + (btn_rect.w - txt.get_width()) // 2, btn_rect.y + 2))
        
        content = self.content_rect()
        pygame.draw.rect(surface, (18, 20, 24), content)
        if not self._buffer:
            # 无内容时也显示伸缩把手
            h_rect = self.resize_handle_rect()
            pygame.draw.polygon(surface, (90, 95, 105), [
                (h_rect.x + 6, h_rect.y + h_rect.h - 6),
                (h_rect.x + h_rect.w - 6, h_rect.y + h_rect.h - 6),
                (h_rect.x + h_rect.w - 6, h_rect.y + 6),
            ])
            return
        
        lines = self._buffer.get_lines()
        visible_lines = max(1, content.h // self.LINE_HEIGHT)
        # 有新输出时自动滚到最下面
        if len(lines) > self._last_line_count:
            self._scroll_offset = max(0, len(lines) - visible_lines)
            self._last_line_count = len(lines)
        
        # 终端风格：深色背景
        pygame.draw.rect(surface, (18, 20, 24), content)
        
        # 显示行（错误行用红色）
        for i in range(visible_lines):
            idx = self._scroll_offset + i
            if idx >= len(lines):
                break
            line = lines[idx]
            # Traceback/Error 行用红色
            is_error = (line.strip().startswith("Traceback") or
                        line.strip().startswith("Error") or
                        "Error:" in line or
                        "Exception:" in line or
                        "  File " in line)
            color = (255, 100, 100) if is_error else (180, 200, 180)
            # 长行截断
            if len(line) > 200:
                line = line[:197] + "..."
            surf = self.font.render(line, True, color)
            surface.blit(surf, (content.x, content.y + i * self.LINE_HEIGHT))
        
        # 滚动条
        if len(lines) > visible_lines:
            sb_h = content.h
            thumb_h = max(20, int(sb_h * visible_lines / len(lines)))
            thumb_y = content.y + int((sb_h - thumb_h) * self._scroll_offset / max(1, len(lines) - visible_lines))
            sb_x = content.x + content.w + 4
            pygame.draw.rect(surface, (50, 52, 58), (sb_x, content.y, self.SCROLLBAR_W, sb_h))
            pygame.draw.rect(surface, (90, 95, 105), (sb_x, thumb_y, self.SCROLLBAR_W, thumb_h))
        
        # 调整大小把手（右下角三角形，拖拽伸缩）
        h_rect = self.resize_handle_rect()
        pygame.draw.polygon(surface, (90, 95, 105), [
            (h_rect.x + 6, h_rect.y + h_rect.h - 6),
            (h_rect.x + h_rect.w - 6, h_rect.y + h_rect.h - 6),
            (h_rect.x + h_rect.w - 6, h_rect.y + 6),
        ])
