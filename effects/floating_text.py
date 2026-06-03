"""浮动文字 (伤害数字/提示)"""


class FloatingText:
    def __init__(self, x, y, text, is_damage=False, color='#ff5252'):
        self.x, self.y = x, y
        self.text = text
        self.life = 1.2
        self.max_life = 1.2
        self.color = color if color else ('#ff5252' if is_damage else '#4caf50')
        self.is_damage = is_damage

    def update(self, dt):
        self.life -= dt
        self.y -= dt * 40
