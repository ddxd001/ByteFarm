"""
游戏素材加载 - 支持从 assets/ 目录加载图片，缺失时使用程序绘制
素材来源见 assets/README.md（CC0 免费可商用）
"""

import pygame
from pathlib import Path
from typing import Optional, Dict, Tuple

# 项目根目录下的 assets
_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
_CACHE: Dict[str, pygame.Surface] = {}


def _path(*parts: str) -> Path:
    return _ASSETS_DIR.joinpath(*parts)


def load_image(*path_parts: str, scale: Optional[Tuple[int, int]] = None) -> Optional[pygame.Surface]:
    """加载图片，可选缩放。失败返回 None。"""
    key = "/".join(path_parts) + (f"@{scale}" if scale else "")
    if key in _CACHE:
        return _CACHE[key]
    p = _path(*path_parts)
    if not p.exists():
        return None
    try:
        surf = pygame.image.load(str(p))
        if surf.get_alpha() is None:
            surf = surf.convert()
        else:
            surf = surf.convert_alpha()
        if scale:
            surf = pygame.transform.smoothscale(surf, scale)
        _CACHE[key] = surf
        return surf
    except (pygame.error, OSError):
        return None


def has_tiles() -> bool:
    """是否有地形瓦片素材"""
    return _path("tiles", "grass.png").exists() or _path("tiles", "grass_0.png").exists()


def has_robot() -> bool:
    """是否有机器人素材"""
    return _path("character", "robot.png").exists()


def get_tile_surface(ground: str, tile_size: int, x: int, y: int) -> Optional[pygame.Surface]:
    """
    获取地形瓦片 Surface，尺寸 (tile_size, tile_size)。
    ground: 'grassland' | 'sandyland'
    无素材时返回 None，由调用方用程序绘制。
    """
    folder = "tiles"
    if ground == "sandyland":
        for name in ("sand.png", "sandyland.png", "sand_0.png"):
            s = load_image(folder, name, scale=(tile_size, tile_size))
            if s is not None:
                return s
        return None
    # grassland
    for name in ("grass.png", "grass_0.png", "grass_1.png", "grassland.png"):
        s = load_image(folder, name, scale=(tile_size, tile_size))
        if s is not None:
            return s
    # 可选：用 (x,y) 选不同变体
    for i in range(4):
        s = load_image(folder, f"grass_{i}.png", scale=(tile_size, tile_size))
        if s is not None:
            return s
    return None


def get_robot_surface(tile_size: int) -> Optional[pygame.Surface]:
    """获取机器人贴图，尺寸约 tile_size x tile_size。无则返回 None。"""
    for name in ("robot.png", "character.png", "robot_front.png"):
        s = load_image("character", name, scale=(tile_size, tile_size))
        if s is not None:
            return s
    return None


def get_resource_surface(entity: str, tile_size: int, progress: float = 1.0) -> Optional[pygame.Surface]:
    """
    获取资源（草/石头）贴图。progress 0~1 表示生长进度。
    无素材返回 None。
    """
    folder = "resources"
    base = "grass" if entity == "grass" else ("bush" if entity == "bush" else ("tree" if entity == "tree" else "stone"))
    for name in (f"{base}.png", f"{base}_0.png"):
        s = load_image(folder, name, scale=(max(4, tile_size // 2), max(4, tile_size // 2)))
        if s is not None:
            if progress < 1.0 and tile_size >= 16:
                # 未成熟时缩小
                w, h = s.get_size()
                scale = 0.3 + 0.7 * progress
                nw, nh = max(2, int(w * scale)), max(2, int(h * scale))
                s = pygame.transform.smoothscale(s, (nw, nh))
            return s
    return None
