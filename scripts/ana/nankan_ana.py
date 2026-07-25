#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""南関・穴スコア（サラブレ流をデータ検証して南関に落とし込み）。

検証で効いた因子だけを重み付け（scratchpad の実測より）:
  - 人気薄(6番人気↓)が対象。
  - 前受け：今回/習性が逃・先＝穴の本命(人気薄の逃げ 単回収189%・先行179%)。
  - ローテ：連闘〜中1週(≤10日)＝単回収117%のプラス収支。中1-2週(11-20)は谷。
  - 馬体重：前走比 増(+2kg↑)は消し(単回収47-56%)、絞れ/維持は可。
  - 血統：daikeiのパワー軸(パ)＝穴率が中系の約2倍。
  - クロス：ND系(ストームキャット/ダンチヒ/サドラーズ)はスパイス(+微)。

使い方(単体):
  from nankan_ana import ana_score
  ana_score(nk=8, interval=7, wt_ch=-2, power='パ', habit_front=True) -> (score, 内訳)
バックテスト:
  python3 scripts/ana/nankan_ana.py backtest      # キャッシュで合成サインの回収率
"""
from __future__ import annotations

def ana_score(nk, interval=None, wt_ch=None, power=None, habit_front=False,
              cross_nd=False, prev_nk=None, prev_chaku=None):
    """人気薄の穴スコア。高いほど買い。nk=単勝人気(6以上が対象)。"""
    s = 0.0; why = []
    if (nk or 0) < 6:
        return 0.0, ["人気薄でない(対象外)"]
    # 前受け習性（最重要）
    if habit_front:
        s += 2.0; why.append("前受け習性+2")
    # 前走人気（着順でなく"人気"を見る＝発掘データ箱の手法・南関で実証）
    if prev_nk is not None:
        if prev_nk <= 3:       s += 2.0; why.append(f"前走{prev_nk}人気(市場評価高)+2")
        elif prev_nk <= 5:     s += 1.0; why.append(f"前走{prev_nk}人気+1")
        elif prev_nk >= 10:    s -= 1.0; why.append(f"前走{prev_nk}人気(評価低)-1")
        # 前走人気だが凡走＝巻き返し(単回収113%)
        if prev_nk <= 3 and (prev_chaku or 0) >= 6:
            s += 0.5; why.append("前走人気を裏切り凡走→巻き返し+0.5")
    # ローテ
    if interval is not None:
        if interval <= 10:      s += 2.0; why.append(f"連闘~中1週({interval}日)+2")
        elif interval <= 20:    s -= 1.0; why.append(f"中1-2週({interval}日)谷-1")
        elif interval >= 36:    s += 1.0; why.append(f"中5週+({interval}日)+1")
    # 馬体重（増は消し）
    if wt_ch is not None:
        if wt_ch >= 2:          s -= 2.0; why.append(f"体重増({wt_ch:+d})消し-2")
        elif wt_ch <= -2:       s += 1.0; why.append(f"絞れ({wt_ch:+d})+1")
    # 血統パワー軸
    if power == "パ":           s += 1.0; why.append("パワー血統+1")
    elif power in ("軽",):      s -= 0.5; why.append("軽い血統-0.5")
    # クロス(スパイス)
    if cross_nd:                s += 0.5; why.append("ND系クロス+0.5")
    return round(s, 1), why


# ---------------------------------------------------------------------------
# バックテスト（南関キャッシュ・血統は割愛＝間隔/体重/前受け習性/人気薄で合成）
# ---------------------------------------------------------------------------
def _backtest():
    import re, os, glob
    from datetime import date
    from collections import defaultdict
    CACHE = os.environ.get("NKCACHE",
        "/tmp/claude-0/-home-user-keiba/5c9e9520-78d2-57a1-98df-28a0a517ec92/scratchpad/nkcache")

    def parse(fn):
        t = open(fn, "rb").read().decode("euc-jp", errors="replace")
        hd = re.search(r"(20\d\d)年(\d+)月(\d+)日.{0,50}?(大井|川崎|船橋|浦和)", re.sub(r"<[^>]+>", " ", t))
        if not hd: return None
        d = date(int(hd.group(1)), int(hd.group(2)), int(hd.group(3)))
        rows = []
        for r in re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S):
            if "/horse/" not in r: continue
            cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip()
                     for c in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)]
            if len(cells) < 15: continue
            try: chaku = int(cells[0])
            except: continue
            hid = re.search(r"/horse/(\w+)/", r)
            nk = None; odds = None
            for i, c in enumerate(cells):
                if re.match(r"^\d+\.\d$", c) and i+1 < len(cells) and re.match(r"^\d+$", cells[i+1]):
                    odds = float(c); nk = int(cells[i+1]); break
            wt = None
            for c in cells:
                m = re.match(r"^(\d{3})\(", c) or re.match(r"^(\d{3})$", c)
                if m: wt = int(m.group(1)); break
            tsuka = next((c for c in cells if re.match(r"^\d+(-\d+){1,3}$", c)), "")
            if hid: rows.append((hid.group(1), chaku, nk, odds, wt, tsuka))
        n = len(rows); out = []
        for hid, chaku, nk, odds, wt, tsuka in rows:
            f = int(tsuka.split("-")[0]) if tsuka else None
            ky = ("?" if f is None else "逃" if f == 1 else "先" if f <= max(2, round(n*0.25))
                  else "差" if f <= round(n*0.6) else "追")
            out.append((hid, chaku, nk, odds, wt, ky))
        return d, out

    seq = defaultdict(list)
    for fn in glob.glob(os.path.join(CACHE, "2026*.html")):
        if os.path.getsize(fn) < 5000: continue
        p = parse(fn)
        if not p: continue
        d, rows = p
        for hid, chaku, nk, odds, wt, ky in rows:
            seq[hid].append((d, chaku, nk, odds, wt, ky))

    recs = []
    for hid, lst in seq.items():
        lst.sort()
        for i, (d, chaku, nk, odds, wt, ky) in enumerate(lst):
            prev = lst[i-1] if i >= 1 else None
            interval = (d - prev[0]).days if prev else None
            wt_ch = (wt - prev[4]) if (prev and wt and prev[4]) else None
            habit_front = bool(prev and prev[5] in ("逃", "先"))
            prev_nk = prev[2] if prev else None
            prev_chaku = prev[1] if prev else None
            sc, _ = ana_score(nk, interval, wt_ch, None, habit_front,
                              prev_nk=prev_nk, prev_chaku=prev_chaku)
            recs.append((chaku, odds, sc))

    def stats(rs):
        n = len(rs)
        if not n: return (0, 0, 0)
        hit = sum(1 for c, o, s in rs if c <= 3)
        tan = sum((o or 0)*100 for c, o, s in rs if c == 1)
        return n, hit/n, tan/(n*100)*100

    pop = [r for r in recs if r]  # all
    print("=== 南関穴スコア backtest（人気薄=6↓、血統抜き合成）===")
    base = [(c, o, s) for c, o, s in recs]
    for th in [1, 2, 3, 4]:
        sub = [(c, o, s) for c, o, s in recs if s >= th]
        n, p, t = stats(sub)
        print(f"  score≥{th}: n={n:>5} 複勝{p*100:>5.1f}% 単回収{t:>4.0f}%")
    print("  ※score≥3 が「連闘 or 前受け習性＋非体重増」級の合成。回収>100%が目標。")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "backtest":
        _backtest()
    else:
        for f in [dict(nk=9, interval=7, wt_ch=-2, power="パ", habit_front=True),
                  dict(nk=8, interval=14, wt_ch=4, power="軽", habit_front=False),
                  dict(nk=7, interval=42, wt_ch=0, power="パ", habit_front=True)]:
            print(f, "→", ana_score(**f))
