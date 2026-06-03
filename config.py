"""游戏配置"""
import math

# 世界尺寸
W, H = 3000, 1800

# 兵线
LANES = [
    dict(name='上路', y=280),
    dict(name='中路', y=900),
    dict(name='下路', y=1520),
]

# 防御塔
TOWER_POS = dict(
    blue_outer=[(500, 280), (500, 900), (500, 1520)],
    blue_inner=[(850, 280), (850, 900), (850, 1520)],
    red_inner=[(2150, 280), (2150, 900), (2150, 1520)],
    red_outer=[(2500, 280), (2500, 900), (2500, 1520)],
)

BLUE_BASE = (140, 900)
RED_BASE = (2860, 900)

# 三方水晶 (每队3个，全部摧毁才能获胜)
CRYSTAL_POS = dict(
    blue=[(120, 280), (120, 900), (120, 1520)],   # 上路/中路/下路
    red=[(2880, 280), (2880, 900), (2880, 1520)],
)
CRYSTAL_HEAL_RANGE = 200   # 水晶回血范围
CRYSTAL_HEAL_RATE = 0.08   # 每秒回复最大HP比例 (8%/秒)

# 小兵随时间强化
MINION_SCALING = [
    # (开始秒, HP倍率, 伤害倍率, 移速加成)
    (0,    1.0,  1.0,  0),
    (120,  1.15, 1.10, 5),
    (240,  1.30, 1.20, 10),
    (360,  1.50, 1.35, 15),
    (480,  1.75, 1.50, 20),
    (600,  2.0,  1.70, 25),
]
SUPER_MINION_TIME = 600  # 10分钟后出现超级兵

# 击杀奖励
KILL_BASE_GOLD = 200
KILL_BASE_EXP = 80
KILL_LEVEL_BONUS = 50    # 每高1级额外金币
KILL_SPREE_BONUS = 50    # 连续击杀额外金币（每层）

MINION_SPAWN_INTERVAL = 25  # 秒
JUNGLE_RESPAWN = 30         # 秒
ITEM_COUNT = 3

JUNGLE_CAMPS = [
    (550, 460, 'wolf'),   (800, 460, 'wolf'),
    (1150, 480, 'golem'), (550, 1340, 'wolf'),
    (800, 1340, 'wolf'),  (1150, 1320, 'golem'),
    (2000, 460, 'wolf'),  (2000, 1340, 'wolf'),
    (1500, 280, 'wolf'),  (1500, 1520, 'wolf'),
    (1800, 900, 'dragon'),
]

# 装备
ITEMS = [
    dict(id='fire',    name='火焰之刃', color='#ff5722', cost=300, tier=1, desc='攻击灼烧3秒 3%HP/秒',
         effect=dict(type='burn', dmgPct=0.03, dur=3)),
    dict(id='frost',   name='冰霜之锤', color='#4fc3f7', cost=250, tier=1, desc='攻击减速50% 2秒',
         effect=dict(type='slow', pct=0.5, dur=2)),
    dict(id='wind',    name='疾风之靴', color='#76ff03', cost=250, tier=1, desc='移速+40%',
         effect=dict(type='speed', pct=0.4)),
    dict(id='poison',  name='毒液之刃', color='#7c4dff', cost=280, tier=1, desc='中毒4秒3%HP/秒',
         effect=dict(type='poison', dmgPct=0.03, dur=4)),
    dict(id='vampire', name='嗜血之镰', color='#e91e63', cost=350, tier=2, desc='25%生命偷取',
         effect=dict(type='lifesteal', pct=0.25)),
    dict(id='thunder', name='雷霆之杖', color='#ffeb3b', cost=300, tier=2, desc='弹射2目标60%伤害',
         effect=dict(type='chain', targets=2, dmgPct=0.6)),
    dict(id='shield',  name='守护之盾', color='#00bcd4', cost=300, tier=2, desc='每15秒挡一次伤害',
         effect=dict(type='shield', cd=15)),
    dict(id='holy',    name='神圣之剑', color='#ffd54f', cost=350, tier=2, desc='攻击力+40',
         effect=dict(type='attack', bonus=40)),
    dict(id='crit',    name='暴击之弓', color='#ff6f00', cost=400, tier=3, desc='35%暴击200%伤害',
         effect=dict(type='crit', chance=0.35, mul=2)),
    dict(id='berserk', name='狂战之斧', color='#ff1744', cost=400, tier=3, desc='HP<30%伤害+60%',
         effect=dict(type='berserk', threshold=0.3, bonus=0.6)),
]

# 商店层级解锁时间
SHOP_TIERS = [
    (0,   1),  # 游戏开始 → 开放T1
    (180, 2),  # 3分钟 → 开放T2
    (480, 3),  # 8分钟 → 开放T3
]
SHOP_REFRESH_INTERVAL = 60  # 商店每60秒刷新

# 英雄职业定义
HERO_TYPES = dict(
    warrior=dict(
        id='warrior', name='战士', icon='战',
        hp=1400, atk=70, speed=190, range=155,
        bodyColor=(229, 57, 53), headColor=(239, 83, 80),
        weapon='sword',
        abilities=dict(
            q=dict(name='冲锋', cd=5, dmg=140, desc='向目标方向冲锋150距离，落点80范围造成140(+50%攻击)伤害，冲锋后获得30%减伤2秒 | 射程150 | CD5秒'),
            w=dict(name='震击', cd=8, dmg=100, desc='140范围造成100(+30%攻击)伤害+减速50%2秒+击退180 | 范围140 | CD8秒',
                   slowPct=0.5, slowDur=2),
            e=dict(name='战吼', cd=16, dmg=220, desc='180范围造成220(+80%攻击)伤害+减速50%，附带三重斩击+冲击波+地面裂纹，获得25%减伤3秒 | 范围180 | CD16秒',
                   radius=180),
        ),
    ),
    mage=dict(
        id='mage', name='法师', icon='法',
        hp=1050, atk=85, speed=185, range=260,
        bodyColor=(124, 77, 255), headColor=(156, 124, 255),
        weapon='staff',
        abilities=dict(
            q=dict(name='火球', cd=3, dmg=160, desc='发射一枚火球，命中50范围爆炸+80击退+灼烧3秒，近身100范围额外伤害+灼烧 | 射程350 | CD3秒', radius=60),
            w=dict(name='冰环', cd=8, dmg=80, desc='140范围造成80(+25%攻击)伤害，减速70%持续2.5秒，8道冰刺，自身获得25%减伤2秒 | 范围140 | CD8秒',
                   slowPct=0.7, slowDur=2.5),
            e=dict(name='陨石', cd=14, dmg=300, desc='召唤6颗陨石+中央大爆炸覆盖200范围，造成300(+100%攻击)伤害+减速40%+灼烧3秒 | 范围200 | CD14秒', radius=200),
        ),
    ),
    archer=dict(
        id='archer', name='射手', icon='射',
        hp=1100, atk=78, speed=200, range=280,
        bodyColor=(255, 143, 0), headColor=(255, 179, 0),
        weapon='bow',
        abilities=dict(
            q=dict(name='连射', cd=2.5, dmg=85, desc='快速射出3支箭矢，每支造成85伤害+破甲10%3秒 | 射程420 | CD2.5秒', hits=3),
            w=dict(name='冰箭', cd=7, dmg=70, desc='锁定射程内敌人射出减速箭，70(+50%攻击)伤害+定身0.8秒+减速60%2秒 | 射程攻击范围+80 | CD7秒',
                   slowPct=0.6, slowDur=2),
            e=dict(name='箭雨', cd=14, dmg=200, desc='12支箭矢从天而降+箭矢风暴覆盖220范围，200(+60%攻击)伤害+减速30%+破甲15%3秒 | 范围220 | CD14秒', radius=220),
        ),
    ),
    assassin=dict(
        id='assassin', name='刺客', icon='刺',
        hp=850, atk=95, speed=220, range=140,
        bodyColor=(0, 188, 212), headColor=(38, 198, 218),
        weapon='dagger',
        abilities=dict(
            q=dict(name='影袭', cd=5, dmg=170, desc='三段连续冲刺(每段间隔0.12秒)，每段55范围造成170(+45%攻击)伤害 | 总射程200 | CD5秒', range=200),
            w=dict(name='烟幕', cd=10, dmg=50, desc='130范围造成50(+20%攻击)伤害+击退200+减速40%持续3秒，回复造成伤害50%生命+3秒30%吸血+50%攻速buff | 范围130 | CD10秒'),
            e=dict(name='绝杀', cd=14, dmg=380, desc='锁定180范围内最近敌人，380(+100%攻击)终结伤害+8道影分身环绕斩击 | 范围180 | CD14秒', range=180),
        ),
    ),
    paladin=dict(
        id='paladin', name='圣骑士', icon='骑',
        hp=1600, atk=55, speed=175, range=140,
        bodyColor=(253, 216, 53), headColor=(255, 238, 88),
        weapon='mace',
        abilities=dict(
            q=dict(name='圣光击', cd=5, dmg=110, desc='16道光柱绕身旋转一圈，170范围造成110(+55%攻击)伤害+击退220距离，摧毁敌方弹道，回复20%伤害量 | 范围170 | CD5秒',
                   radius=170),
            w=dict(name='庇护', cd=10, dmg=60, desc='150范围友军获得30%护盾3秒+回复30生命 | 范围150 | CD10秒',
                   radius=150),
            e=dict(name='天罚', cd=16, dmg=240, desc='朝目标方向扇形240范围降下8道天罚光柱+中央圣光审判，240(+90%攻击)伤害+减速60%+击退300 | 范围240 | CD16秒',
                   radius=220, stunDur=0.8),
        ),
    ),
    necromancer=dict(
        id='necromancer', name='死灵法师', icon='死',
        hp=1000, atk=90, speed=180, range=260,
        bodyColor=(106, 27, 154), headColor=(142, 36, 170),
        weapon='scythe',
        abilities=dict(
            q=dict(name='暗影弹', cd=3, dmg=150, desc='发射暗影能量弹追踪300范围内最近敌人，命中40范围爆炸造成150(+40%攻击)伤害 | 射程320 | CD3秒', radius=50),
            w=dict(name='骨牢', cd=7, dmg=90, desc='160范围造成90(+30%攻击)伤害+定身0.8秒+减速80%持续2.5秒，6道暗影骨柱升起 | 范围160 | CD7秒',
                   slowPct=0.8, slowDur=2.5),
            e=dict(name='亡灵天灾', cd=15, dmg=230, desc='10道灵魂从地面升起+暗影漩涡，220范围造成230(+70%攻击)伤害+中毒4%HP/秒持续3秒+25%伤害吸血 | 范围220 | CD15秒',
                   radius=220),
        ),
    ),
    druid=dict(
        id='druid', name='德鲁伊', icon='德',
        hp=1150, atk=75, speed=195, range=190,
        bodyColor=(67, 160, 71), headColor=(102, 187, 106),
        weapon='claw',
        abilities=dict(
            q=dict(name='藤蔓', cd=4, dmg=110, desc='180范围造成110(+30%攻击)伤害+定身0.8秒+减速50%+中毒3%HP/秒持续3秒 | 范围180 | CD4秒', dur=3),
            w=dict(name='野性治愈', cd=7, dmg=50, desc='170范围友军回复25(+30%攻击)生命+25%减伤护盾3秒，8道治愈光束 | 范围170 | CD7秒',
                   radius=170),
            e=dict(name='自然之怒', cd=14, dmg=250, desc='14条藤蔓+12片叶刃+生命绽放覆盖240范围，250(+80%攻击)伤害+减速60%持续3秒+友军回复15%最大生命 | 范围240 | CD14秒',
                   radius=240),
        ),
    ),
    berserker=dict(
        id='berserker', name='狂战士', icon='狂',
        hp=1250, atk=95, speed=205, range=145,
        bodyColor=(255, 109, 0), headColor=(255, 145, 0),
        weapon='axe',
        abilities=dict(
            q=dict(name='狂砍', cd=4, dmg=170, desc='攻击范围内造成170(+60%攻击)伤害，附带三重扇形斩击，命中获得减伤护盾 | 范围攻击范围+30 | CD4秒'),
            w=dict(name='嗜血', cd=7, dmg=80, desc='130范围造成80(+30%攻击)伤害，回复造成伤害30%的生命+40%攻速3秒，6道血光 | 范围130 | CD7秒',
                   healPct=0.3),
            e=dict(name='狂暴', cd=13, dmg=320, desc='狂暴旋风180范围造成320(+100%攻击)伤害，HP<30%时伤害×1.5，清除负面效果+30%减伤3秒，减速30%+血怒脉冲+地面爆裂 | 范围180 | CD13秒',
                   radius=180),
        ),
    ),
)

# Pygame 窗口
VIEW_W, VIEW_H = 1300, 750
FPS = 60

# ====== LLM AI 控制配置 ======
# 在游戏启动画面中可以覆盖这些设置
LLM_SETTINGS = {
    'enabled': False,           # 是否启用 LLM 控制人机英雄
    'provider': 'deepseek',     # 提供商: deepseek / glm / qwen / custom
    'api_key': '',              # API 密钥
    'api_url_override': '',     # 自定义 API URL（留空=使用默认）
    'model': '',                # 模型名（留空=使用提供商默认）
    'control_team': 'red',      # 控制哪一方: red / blue / both
    'control_positions': ['all'],  # 控制位置: ['all'] 或 ['top','mid','bottom','jungle']
    'interval': 8.0,            # LLM 决策间隔（秒）
    'max_tokens': 300,
    'timeout': 15.0,
}