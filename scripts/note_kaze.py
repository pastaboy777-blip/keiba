"""note(むねひろ)の【先週の風傾向】を全部拾って、場ごとの「最後の直線で馬が走る向き」を決める。

    python3 scripts/note_kaze.py      → models/course_straight.json を上書き

1文ごとに「風が吹いてくる方位 θ」と「直線での効き(向かい/追い/横)」を取り、走る向きを1つ出す:
  向かい風 … 走る向き = θ
  追い風   … θ + 180
  横風(スタンドから内ラチ) … スタンドは右回りなら走る馬の左、左回りなら右 → 右回り θ+90 / 左回り θ−90
  横風(内ラチからスタンド) … その逆
場ごとに円周平均し、ばらつき(平均ベクトルの長さ R、1に近いほど揃っている)も出す。
"""

from __future__ import annotations

import collections
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRS = ["北", "北北東", "北東", "東北東", "東", "東南東", "南東", "南南東", "南", "南南西", "南西", "西南西", "西", "西北西", "北西", "北北西"]
DEG = {d: i * 22.5 for i, d in enumerate(DIRS)}
MIGI = {"札幌", "函館", "福島", "中山", "京都", "阪神", "小倉"}       # 右回り
PLACES = ["札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉"]


def cmean(degs):
    x = sum(math.cos(math.radians(d)) for d in degs) / len(degs)
    y = sum(math.sin(math.radians(d)) for d in degs) / len(degs)
    return math.degrees(math.atan2(y, x)) % 360, math.hypot(x, y)


def from_dir(s):
    """「西北西～北西」→ 2つの円周平均。"""
    ds = [DEG[d] for d in re.findall("|".join(sorted(DIRS, key=len, reverse=True)), s)]
    return cmean(ds)[0] if ds else None


def statements(text):
    m = re.search(r"【先週の風傾向】\n(.*?)\n(?:\n|＜|【)", text, re.S)
    if not m:
        return
    cur = None
    for line in m.group(1).split("\n"):
        pm = re.match(r"(%s)…" % "|".join(PLACES), line)
        if pm:
            cur = pm.group(1)
        if not cur:
            continue
        for cl in re.split("。", line):
            em = re.search(r"直線は(追い風|向かい風|横風（(スタンドから内ラチ|内ラチからスタンド)）)", cl)
            wm = re.search(r"([東西南北～]+)の風", cl)
            if em and wm:
                th = from_dir(wm.group(1))
                if th is not None:
                    yield cur, th, em.group(1), cl


def run_dir(place, th, eff):
    if eff == "向かい風":
        return th % 360
    if eff == "追い風":
        return (th + 180) % 360
    s = 90 if place in MIGI else -90
    if "内ラチからスタンド" in eff:
        s = -s
    return (th + s) % 360


def main():
    B = [json.loads(l) for l in open(ROOT / "data/note/munehironet/body.jsonl")]
    per = collections.defaultdict(list)
    eff_n = collections.defaultdict(collections.Counter)
    for b in B:
        for place, th, eff, cl in statements(b["text"]):
            per[place].append(run_dir(place, th, eff))
            eff_n[place][eff[:2]] += 1
    out = {"_note": "最後の直線で馬が走っていく方位(度, 北=0 東=90)。note『先週の風傾向』の全記述から円周平均(scripts/note_kaze.py)。"}
    for p in PLACES:
        if per[p]:
            m, R = cmean(per[p])
            out[p] = round(m)
            out["_R_" + p] = round(R, 2)
            print(f"{p}: 走る向き {m:5.0f}°  揃い R={R:.2f}  記述 {len(per[p])}件 {dict(eff_n[p])}")
    json.dump(out, open(ROOT / "models/course_straight.json", "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
