#!/usr/bin/env python3
"""
ByteFarm - 主入口

在内置编辑器中编写 Python 程序控制机器人，按 F2 开始执行、F3 停止执行。
"""

import pygame
from game.engine import GameEngine
from game.save_manager import migrate_old_save, MAX_SLOTS, load_config


def main():
    config = load_config()
    tile_size = config.get("tile_size", 40)
    engine = GameEngine(width=1024, height=768, tile_size=tile_size)
    
    for i in range(1, MAX_SLOTS + 1):
        migrate_old_save(i)
    
    while True:
        choice = engine.run_menu()
        if choice == -1:
            pygame.quit()
            return

        slot_id, has_save = choice
        if has_save:
            if not engine.load_from_slot(slot_id):
                print("加载存档失败")
        else:
            engine.start_new_game(slot_id)

        result = engine.run()
        if result != "main_menu":
            break

    pygame.quit()


if __name__ == "__main__":
    main()
