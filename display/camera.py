"""相机系统"""
import math
from config import W, H, VIEW_W, VIEW_H
from utils import clamp


class Camera:
    def __init__(self):
        self.x = W / 2
        self.y = H / 2
        self.view_w = VIEW_W
        self.view_h = VIEW_H
        self.follow_target = None

    def follow(self, entity):
        self.follow_target = entity

    def update(self, dt):
        if self.follow_target:
            # 基于 dt 的指数平滑：smooth_factor 越大跟随越快
            # 8.0 表示约 1/8 秒到达目标位置
            smooth = 8.0 if self.follow_target.alive else 4.0
            factor = 1 - math.exp(-smooth * dt)
            self.x += (self.follow_target.x - self.x) * factor
            self.y += (self.follow_target.y - self.y) * factor
        self.x = clamp(self.x, self.view_w / 2, W - self.view_w / 2)
        self.y = clamp(self.y, self.view_h / 2, H - self.view_h / 2)

    def screen_to_world(self, sx, sy):
        return sx + self.x - self.view_w / 2, sy + self.y - self.view_h / 2
