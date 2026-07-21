#!/usr/bin/env python3
"""新聞風「指数＆展開予想」のデモ。

南関の現実的な合成データ(走破タイム・コーナー通過順・脚質)を生成し、
スピード指数を自己校正して、新聞レイアウトの HTML とテキストを出力する。

    python3 scripts/paper_demo.py                 # HTML を out/paper_demo.html に出力
    python3 scripts/paper_demo.py --text          # テキストも標準出力

依存ライブラリなし(標準ライブラリのみ)。
"""
from __future__ import annotations

import argparse
import os
import random
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core.interval import RunRecord                       # noqa: E402
from nankeiba.core.hindex import SpeedIndexModel, DEFAULT_STANDARD_TIME, estimate_first3f  # noqa: E402
from nankeiba.core import newspaper as nb                          # noqa: E402

PLACES = ["大井", "川崎", "船橋", "浦和"]
GOINGS = ["良", "良", "良", "稍", "重", "不"]         # 良多め
GOING_DT = {"良": 0.0, "稍": -0.4, "重": -0.9, "不": -1.4}   # 濡れると速い(秒)
STYLES = ["逃げ", "先行", "差し", "追込"]


def _std(place, dist):
    t = DEFAULT_STANDARD_TIME[place]
    if dist in t:
        return t[dist]
    nd = min(t, key=lambda d: abs(d - dist))
    return t[nd] / nd * dist


def _corner_for_style(style, field_size, rng):
    """脚質から4コーナーぶんの通過順を生成する。"""
    if style == "逃げ":
        early = 1 if rng.random() < 0.7 else 2
    elif style == "先行":
        early = rng.randint(2, 4)
    elif style == "差し":
        early = rng.randint(5, max(6, field_size - 3))
    else:  # 追込
        early = rng.randint(max(6, field_size - 4), field_size)
    seq = []
    pos = early
    for _ in range(4):
        pos = max(1, min(field_size, pos + rng.randint(-1, 1)))
        seq.append(pos)
    # 差し・追込は最後に押し上げることがある
    if style in ("差し", "追込") and rng.random() < 0.5:
        seq[-1] = max(1, seq[-1] - rng.randint(1, 3))
    return seq


def make_horse(hid, rng):
    ability = rng.gauss(0.0, 1.0)          # 大きいほど強い(タイム速い)
    style = rng.choices(STYLES, weights=[2, 4, 3, 1])[0]
    home = rng.choice(PLACES)
    return {"id": hid, "name": f"デモ馬{hid:02d}", "ability": ability,
            "style": style, "home": home, "sex_age": rng.choice(["牝3", "牡3", "セ3"]),
            "jockey": f"騎手{rng.randint(1, 18):02d}"}


def gen_history(horse, n_runs, today, rng):
    runs = []
    d = today
    for i in range(n_runs):
        d = d - timedelta(days=rng.randint(12, 40))
        place = horse["home"] if rng.random() < 0.6 else rng.choice(PLACES)
        dist = rng.choice([1200, 1400, 1500, 1600, 1700, 1800])
        going = rng.choice(GOINGS)
        field_size = rng.randint(9, 14)
        # タイム: 基準 − 能力*係数 + 馬場 + ノイズ。良基準からの相対。
        base = _std(place, dist)
        t = base - horse["ability"] * (dist / 1600 * 1.6) + GOING_DT[going] + rng.gauss(0.6, 0.7)
        t = round(t, 1)
        corner = _corner_for_style(horse["style"], field_size, rng)
        # 着順: 能力+位置取り+運。強い/前にいるほど上位。
        score = horse["ability"] - 0.08 * (corner[-1] - 1) + rng.gauss(0, 0.7)
        finish = max(1, min(field_size, int(round((field_size + 1) / 2 - score * 2.2))))
        last3f = round(37.0 + (dist - 1200) / 400 * 0.6 + rng.gauss(0, 0.8), 1)
        f3 = estimate_first3f(t, dist, last3f_sec=last3f, corner_pos=corner, field_size=field_size)
        runs.append(RunRecord(
            date=f"{d:%Y-%m-%d}", place=place, distance=dist, field_size=field_size,
            finish_pos=finish, jockey=horse["jockey"], baba=going,
            corner_pos=corner, time_sec=t, last3f_sec=last3f, first3f_sec=f3,
            agari_rank=None,
        ))
    return runs


def build_demo(seed=7):
    rng = random.Random(seed)
    today = date(2026, 7, 21)
    n = 12
    horses = [make_horse(i + 1, rng) for i in range(n)]

    entries = []
    all_runs = []
    for i, h in enumerate(horses):
        hist = gen_history(h, rng.randint(5, 10), today, hist_rng := rng)
        all_runs.extend(hist)
        entries.append(nb.PaperEntry(
            umaban=i + 1, name=h["name"], history=hist,
            sex_age=h["sex_age"], jockey=h["jockey"], waku=(i // 2) + 1,
        ))

    # 指数モデルを過去走から自己校正
    model = SpeedIndexModel.fit(all_runs, base=0.0)

    header = nb.RaceHeader(
        place="大井", distance=1600, date="2026-07-21", race_no=11,
        baba="良", post_time="20:10", race_name="デモ特別（C1） 3歳以上",
    )
    return nb.build_card(header, entries, model)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out/paper_demo.html")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--text", action="store_true")
    args = ap.parse_args()

    card = build_demo(args.seed)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(nb.render_html(card))
    print(f"HTML を書き出しました: {args.out}")

    if args.text:
        print()
        print(nb.render_text(card))


if __name__ == "__main__":
    main()
