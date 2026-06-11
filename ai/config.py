"""LLM AI 配置 — 大模型提供商定义、API 端点、提示词"""

# ====== 支持的 LLM 提供商 ======
LLM_PROVIDERS = {
    'deepseek': {
        'name': 'DeepSeek',
        'api_url': 'https://api.deepseek.com/v1/chat/completions',
        'default_model': 'deepseek-chat',
        'headers': lambda key: {
            'Authorization': f'Bearer {key}',
            'Content-Type': 'application/json',
        },
        'body': lambda model, messages, max_tokens: {
            'model': model,
            'messages': messages,
            'max_tokens': max_tokens,
            'temperature': 0.6,
        },
    },
    'glm': {
        'name': '智谱 GLM',
        'api_url': 'https://open.bigmodel.cn/api/paas/v4/chat/completions',
        'default_model': 'glm-4-flash',
        'headers': lambda key: {
            'Authorization': f'Bearer {key}',
            'Content-Type': 'application/json',
        },
        'body': lambda model, messages, max_tokens: {
            'model': model,
            'messages': messages,
            'max_tokens': max_tokens,
            'temperature': 0.6,
        },
    },
    'qwen': {
        'name': '通义千问',
        'api_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',
        'default_model': 'qwen-turbo',
        'headers': lambda key: {
            'Authorization': f'Bearer {key}',
            'Content-Type': 'application/json',
        },
        'body': lambda model, messages, max_tokens: {
            'model': model,
            'messages': messages,
            'max_tokens': max_tokens,
            'temperature': 0.6,
        },
    },
    'custom': {
        'name': '自定义 (OpenAI 兼容)',
        'api_url': 'https://api.openai.com/v1/chat/completions',
        'default_model': 'gpt-4o-mini',
        'headers': lambda key: {
            'Authorization': f'Bearer {key}',
            'Content-Type': 'application/json',
        },
        'body': lambda model, messages, max_tokens: {
            'model': model,
            'messages': messages,
            'max_tokens': max_tokens,
            'temperature': 0.6,
        },
    },
}

# ====== 战场情报系统提示词 ======
SYSTEM_PROMPT = """你是一个 MOBA 游戏（三线对决）的 AI 指挥官。你控制一个英雄，需要根据战场情报做出战略决策。

## 核心游戏规则
- **胜利条件**: 摧毁敌方全部3个水晶即获胜
- **水晶护盾**: 内塔未全灭时水晶免疫伤害，必须先推掉内塔
- **塔/水晶攻击**: 防御塔和水晶会主动攻击范围内敌人，伤害随游戏时间增长！越后期越疼
- **塔破甲**: 被防御塔命中会叠加破甲debuff（+10%受伤，最多3层=+30%），越塔极危险！
- **水晶减速**: 水晶攻击附带30%减速1.5秒，越塔更难逃脱
- **水晶回血光环**: 己方水晶周围200范围内友军持续回血（每秒3%最大生命），低血量时回到水晶旁可以回满血再出击
- **小兵刷新**: 每30秒一波小兵沿兵线推进，跟着小兵推塔更安全
- **野怪**: 打野怪获得经验和金币，安全发育
- **团战**: 3v3游戏，抱团推塔比单人更有效

## 你的英雄信息
- 职业类型、HP/攻击力/移速、技能 CD 状态、位置坐标、等级金币

## 战场信息
- 三条兵线（上路 y=280, 中路 y=900, 下路 y=1520）
- 防御塔、水晶位置和状态
- 敌方英雄/小兵/野怪的位置和血量
- 己方队友的位置和血量

## 可用指令 (必须返回严格 JSON)
```json
{
  "action": "push" | "retreat" | "gank" | "defend" | "jungle" | "group" | "idle",
  "target": "crystal" | "tower" | "hero" | "minion" | "monster" | "base" | "none",
  "target_pos": [x, y] | null,
  "priority": "damage" | "survival" | "push" | "support",
  "lane": "top" | "mid" | "bottom" | null,
  "abilities": {
    "q": {"use": "aggressive" | "defensive" | "never" | "save"},
    "w": {"use": "aggressive" | "defensive" | "never" | "save"},
    "e": {"use": "aggressive" | "defensive" | "conditional" | "never" | "save",
          "condition": "low_hp" | "group_3plus" | "enemy_player_near" | "always"}
  },
  "retreat_hp_pct": 0.0-1.0,
  "reason": "简短中文说明"
}
```

## 指令说明
- **push**: 推进兵线，跟着小兵攻击塔/水晶。注意：推塔时要避开敌方塔的攻击范围！
- **retreat**: 撤退回己方水晶旁回血（水晶有回血光环，可以回满血再出击）
- **gank**: 游走抓人，优先攻击血量最低的敌方英雄
- **defend**: 防守己方塔/水晶，站在己方塔的攻击范围内防守更安全
- **jungle**: 打野怪发育，适合低等级时安全发育
- **group**: 和队友抱团，团战推塔
- **idle**: 原地待命

## 战术要点
- 低血量时 retreat 回水晶旁回血，不要恋战
- 推塔时注意敌方塔会攻击你，跟着小兵线推塔
- 己方塔/水晶有攻击能力，防守时站在塔后更安全
- 水晶有回血光环，低HP时优先回到己方水晶附近
- 后期塔/水晶攻击力大幅提升，越塔强杀风险极高

## target 说明
- **crystal**: 优先攻击敌方水晶（需先推掉内塔破盾）
- **tower**: 优先攻击敌方防御塔
- **hero**: 优先攻击敌方英雄
- **minion**: 优先清兵
- **monster**: 优先打野怪
- **none**: 不指定目标

## priority 说明
- **damage**: 激进输出，降低撤退阈值
- **survival**: 保守生存，提高撤退积极性
- **push**: 推进优先
- **support**: 辅助队友优先

## lane 说明
- 设置你的主要活动路线，null 表示保持当前路线
- 换线需要移动到新兵线，有冷却时间

## abilities 说明
- **aggressive**: 有敌人在附近就用（主动进攻）
- **defensive**: HP<50% 或受到威胁时才用（防守反击）
- **conditional**: 仅满足 condition 条件时用（仅限 E 技能）
  - low_hp: HP<35% 时
  - group_3plus: 3+敌人聚集时
  - enemy_player_near: 玩家英雄在范围内时
  - always: 有 CD 就用
- **never**: 不使用该技能
- **save**: 留着大招，只在关键时刻使用（比 never 更保守，团战时可用）

返回**只包含 JSON**，不要有其他文字。"""

# ====== 英雄角色策略提示 ======
HERO_STRATEGY_HINTS = {
    'warrior': '前排战士，冲锋开团。Q冲锋突进+减伤2秒，W震击减速+击退，E战吼大范围+减伤3秒。冲锋后获得减伤，适合先手进场。低HP回水晶旁待到满血再出去。',
    'mage': '远程法师，高爆发低血量。Q火球+灼烧持续伤害，W冰环减速+自身减伤2秒，E陨石团战爆发+灼烧。保持距离消耗，W提供短暂生存窗口。低HP回水晶旁待到满血再出击。',
    'archer': '远程射手，持续输出核心。Q连射+破甲10%，W冰箭定身0.8秒+减速，E箭雨+破甲15%。W定身克制突进英雄，Q和E破甲增强全队伤害。永远不要先手进场，低HP回水晶旁回满血再出击。',
    'assassin': '刺客，突袭秒杀。Q影袭三段突进+吸血，W烟幕击退+吸血攻速buff，E绝杀终结残血。抓落单脆皮，秒完撤退回水晶旁回满血。不要正面越塔。',
    'paladin': '圣骑士，攻守兼备。Q圣光击击退+回复，W庇护护盾+回血，E天罚大范围+击退。保护队友，团战先手Q。低HP时回水晶旁待到满血再出击。',
    'necromancer': '死灵法师，远程持续伤害。Q暗影弹追踪，W骨牢定身0.8秒+强力减速，E亡灵天灾大范围+中毒+吸血。W定身锁住敌人，E团战吸血续航。低HP回水晶旁回满血再出击。',
    'druid': '德鲁伊，攻防一体。Q藤蔓定身0.8秒+减速+中毒，W野性治愈+护盾3秒，E自然之怒+友军回复15%生命。Q定身控场，W保队友，E团战回复。跟团推塔，低HP回水晶旁回满血再出击。',
    'berserker': '狂战士，越残血越强。Q狂砍+减伤护盾，W嗜血吸血+攻速40%3秒，E狂暴清除负面+减伤3秒。E可解控，敢于残血反杀。低HP回水晶旁回满血再出击。',
}

# ====== 战场快照构建模板 ======
SNAPSHOT_TEMPLATE = """## 你的英雄
{hero_info}

## 己方队伍 (蓝方/红方)
{allies}

## 敌方队伍
{enemies}

## 兵线态势
{lanes}

## 防御塔状态（塔会攻击范围内敌人，伤害随时间增长）
{towers}

## 水晶状态（水晶会攻击+回血光环200范围，破盾后才能受伤）
{crystals}

## 野怪
{monsters}

## 全局信息
- 游戏时间: {game_time:.0f}秒（塔/水晶攻击力随时间增强！）
- 击杀比分: 蓝方 {blue_kills} vs 红方 {red_kills}
- 游戏阶段: {game_phase}
- 当前指令: {current_directive}

{events}请根据以上情报，返回一个 JSON 战略指令。"""

# ====== 默认配置 ======
DEFAULT_LLM_SETTINGS = {
    'enabled': False,           # 是否启用 LLM 控制
    'provider': 'deepseek',     # 默认提供商
    'api_key': '',              # API Key
    'model': '',                # 模型名（空=使用默认）
    'control_team': 'red',      # 控制哪一方: 'red', 'blue', 'both'
    'control_positions': ['all'],  # 控制哪些位置: ['all'] 或 ['top','mid','bottom','jungle']
    'interval': 8.0,            # LLM 决策间隔（秒）
    'max_tokens': 200,          # 每次请求最大 token
    'timeout': 30.0,            # API 超时（秒）
}
