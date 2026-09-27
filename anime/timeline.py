"""Master timeline. Every agent reads this; times are GLOBAL seconds.

Story: 「最後の一完歩」— A horse-racing prediction AI (the very model in this repo)
gives the 14番 ハルカゼ a 0.8% chance. Young jockey 美月 and old groom 源さん
believe otherwise. At 大井競馬場's night race (トゥインクルレース), ハルカゼ comes
from last place and wins by a nose. The AI, defeated, "adds it to training data".
"""

# (shot_id, start, end, module under scenes/)
SHOTS = [
    ("s01", 0.0, 6.0, "s01_open"),       # AI boot HUD over night Tokyo -> 大井 racecourse
    ("s02", 6.0, 15.0, "s02_stable"),    # warm stable: 源さん, 美月, ハルカゼ
    ("s03", 15.0, 20.0, "s03_gate"),     # goggles eye close-up -> starting gate -> clang
    ("s04", 20.0, 33.0, "s04_race"),     # side tracking shot, last place, 4th corner "今だ"
    ("s05", 33.0, 45.0, "s05_straight"), # final straight, surge, HUD glitch
    ("s06", 45.0, 50.0, "s06_finish"),   # photo finish, white flash, freeze, win call
    ("s07", 50.0, 60.0, "s07_epilogue"), # embrace, AI updates, 美月's line, title card
]

# Transition INTO a shot: (shot_id, kind, seconds). kinds: "cut", "fade_black", "flash_white", "cross"
TRANSITIONS = {
    "s02": ("cross", 0.6),
    "s03": ("fade_black", 0.4),
    "s04": ("flash_white", 0.25),
    "s05": ("cut", 0.0),
    "s06": ("flash_white", 0.2),
    "s07": ("cross", 0.8),
}

# Speakers: voice + subtitle colour
SPEAKERS = {
    "AI":     {"name": "KEIBA-AI", "color": (0.25, 0.95, 1.00)},
    "MIZUKI": {"name": "美月",     "color": (1.00, 0.55, 0.62)},
    "GEN":    {"name": "源さん",   "color": (1.00, 0.80, 0.45)},
    "ANN":    {"name": "実況",     "color": (1.00, 1.00, 1.00)},
}

# Dialogue. start = global seconds; max = maximum allowed duration (slot).
# "text" is the spoken text (reading-friendly), "sub" is the subtitle as displayed.
LINES = [
    dict(id="L01", spk="AI",     start=1.2,  max=4.6, text="第十一レース。十四番、ハルカゼ。勝率、れいてん八パーセント。推奨は、見送りです。",
         sub="第11レース 14番 ハルカゼ。勝率 0.8%。推奨は——見送りです。"),
    dict(id="L02", spk="GEN",    start=6.9,  max=3.2, text="数字じゃ、こいつの心までは測れねえよ。",
         sub="数字じゃ、こいつの心までは測れねえよ。"),
    dict(id="L03", spk="MIZUKI", start=10.6, max=3.9, text="うん。行こう、ハルカゼ。最後まで、一緒に。",
         sub="うん。……行こう、ハルカゼ。最後まで、一緒に。"),
    dict(id="L04", spk="ANN",    start=18.7, max=1.5, text="スタートしました!",
         sub="スタートしました!"),
    dict(id="L05", spk="ANN",    start=20.9, max=3.0, text="ハルカゼは最後方!ここからどうか!",
         sub="ハルカゼは最後方! ここからどうか!"),
    dict(id="L06", spk="MIZUKI", start=25.2, max=1.9, text="まだ……まだだよ。",
         sub="まだ……まだだよ。"),
    dict(id="L07", spk="MIZUKI", start=29.6, max=1.8, text="今だ、ハルカゼ!",
         sub="今だ、ハルカゼ!"),
    dict(id="L08", spk="ANN",    start=33.4, max=3.8, text="直線コース!大外からハルカゼ!ハルカゼが来た!",
         sub="直線コース! 大外からハルカゼ! ハルカゼが来た!"),
    dict(id="L09", spk="ANN",    start=38.4, max=2.6, text="並ぶか、並ぶか、並んだ!",
         sub="並ぶか、並ぶか——並んだ!"),
    dict(id="L10", spk="AI",     start=41.4, max=1.8, text="計算、不能。",
         sub="計算……不能。"),
    dict(id="L11", spk="ANN",    start=47.4, max=2.4, text="ハルカゼ!差し切ったぁ!",
         sub="ハルカゼ! 差し切ったぁ!"),
    dict(id="L12", spk="AI",     start=51.0, max=3.6, text="予測を、更新します。学習データに、追加。",
         sub="予測を更新します。……学習データに、追加。"),
    dict(id="L13", spk="MIZUKI", start=54.8, max=2.8, text="ね。数字だけじゃ、わからないでしょ?",
         sub="ね。数字だけじゃ、わからないでしょ?"),
]

# Key beats scenes/music/sfx must hit (global seconds)
BEATS = {
    "hud_boot": 0.3,
    "gate_clang": 18.5,
    "fourth_corner_go": 29.6,   # "今だ" — horse kicks, speed lines, music drops in
    "straight_start": 33.0,
    "neck_and_neck": 40.2,      # "並んだ!"
    "ai_glitch": 41.4,
    "finish_line": 45.0,        # white flash, silence
    "win_call": 47.4,
    "title_card": 57.4,
    "end": 60.0,
}

def shot_at(t):
    for sid, a, b, mod in SHOTS:
        if a <= t < b:
            return sid, a, b, mod
    sid, a, b, mod = SHOTS[-1]
    return sid, a, b, mod
