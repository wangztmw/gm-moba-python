"""掉落物"""
import math


class LootDrop:
    def __init__(self, x, y, item):
        self.x, self.y = x, y
        self.item = item
        self.life = 20.0
        self.bob_offset = 0.0

    def update(self, dt):
        self.life -= dt
        self.bob_offset += dt * 3
