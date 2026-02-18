"""
示例 - 绕着地图边缘逆时针转，遇资源则采集
无需 import，由游戏注入 move()、collect()、measure()、get_map_size()、print()
"""

def run():
    print("程序开始运行")
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
