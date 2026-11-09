#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""南関版コンピ指数（オッズ→勝率→40〜90点の序列指数）。

日刊コンピ指数の思想（出走馬を序列点数化し、1位指数・指数合計で堅い/荒れを判定）を
南関の単勝オッズから自作したもの。日刊コンピは新聞社の予想順位ベースだが、
本エンジンは市場（単勝オッズ）→控除補正勝率ベースなので"市場コンピ"に近い。

指数の定義:
  p_i  = (1/odds_i) / Σ(1/odds)          # 単勝オッズ→控除(テラ銭)を除いた真の勝率
  idx_i = clamp(40, 90, round(BASE + SCALE * p_i))
          BASE=40, SCALE=170  → 勝率29.4%で90到達、10%で57、5%で48.5
  ※40〜90帯に収め、日刊コンピの見た目レンジを再現。1位指数はレースごとに変動する
    （断然人気がいれば高く、混戦なら低い）＝荒れ判定に使える。

レース指標:
  ichii     : 1位指数（最大値）           … 高いほど堅い軸
  gap12     : 1位指数 − 2位指数           … 大きいほど抜けた1頭
  goukei    : 上位5頭の指数合計           … 上位の充実度
  top3share : p1+p2+p3（上位3頭の勝率占有）… 高いほど上位決着=堅い
  arate     : 荒れ度スコア/判定（下記ロジック）
"""
import subprocess, re, os, sys, math

SP = os.path.dirname(os.path.abspath(__file__))
BASE_URL = "https://p.keibabook.co.jp"
BASE, SCALE = 40, 150          # 指数変換の係数（勝率33.3%で90到達）
FLOOR, CEIL = 40, 90

def _conf():
    # kb.conf(cookie)をscripts/ana か scratchpad から探す
    for c in (os.path.join(SP, "kb.conf"),
              os.path.expanduser("~/keiba/scripts/ana/kb.conf")):
        if os.path.exists(c):
            return c
    # scratchpad fallback
    import glob
    g = glob.glob("/tmp/claude-*/**/kb.conf", recursive=True)
    return g[0] if g else None

def fetch_odds(rid, cache=None):
    """単勝オッズ {umaban:(name, odds)} を返す。"""
    conf = _conf()
    out = cache or f"/tmp/od_{rid}.html"
    if not (os.path.exists(out) and os.path.getsize(out) > 2000):
        cmd = ["curl", "-s", "-L"]
        if conf: cmd += ["-K", conf]
        cmd += [f"{BASE_URL}/chihou/odds/1/{rid}", "-o", out]
        subprocess.run(cmd, check=False)
    h = open(out, encoding="utf-8", errors="replace").read()
    res = {}
    for r in re.split(r'(?=<td class="umaban">)', h)[1:]:
        ub = re.match(r'<td class="umaban">\s*(\d+)', r)
        nm = re.search(r'/db/uma/\d+[^>]*>([^<]+)<', r)
        od = re.search(r'odds5 \{sortValue:\s*([\d.]+)\}', r)
        if ub and od and float(od.group(1)) > 0:
            res[int(ub.group(1))] = (nm.group(1).strip() if nm else "?", float(od.group(1)))
    return res

def index_from_odds(odds):
    """{umaban:(name,odds)} -> リスト[dict]（指数降順）とレース指標dict。"""
    inv = {ub: 1.0 / o for ub, (n, o) in odds.items()}
    s = sum(inv.values()) or 1.0
    horses = []
    for ub, (n, o) in odds.items():
        p = inv[ub] / s
        idx = max(FLOOR, min(CEIL, round(BASE + SCALE * p)))
        horses.append({"ub": ub, "name": n, "odds": o, "p": p, "idx": idx})
    horses.sort(key=lambda x: (-x["idx"], -x["p"]))
    idxs = [h["idx"] for h in horses]
    ps = [h["p"] for h in horses]
    ichii = idxs[0] if idxs else 0
    gap12 = (idxs[0] - idxs[1]) if len(idxs) > 1 else 0
    goukei = sum(idxs[:5])
    # 荒れ判定は指数(90飽和あり)でなく勝率空間で行う
    p1 = ps[0] if ps else 0
    p2 = ps[1] if len(ps) > 1 else 0
    p3 = ps[2] if len(ps) > 2 else 0
    gap_p = p1 - p2
    top3share = p1 + p2 + p3
    if   p1 >= 0.33 and gap_p >= 0.12:                 verdict = "断然（軸1点で信頼）"
    elif p1 >= 0.25 and gap_p >= 0.07:                 verdict = "堅い（軸中心）"
    elif p1 >= 0.22 and p2 >= 0.18 and gap_p < 0.06:   verdict = "2強対決（馬連本線・単は割れ）"
    elif top3share >= 0.58 and p1 < 0.28:              verdict = "上位拮抗（3頭ボックス）"
    elif p1 < 0.17:                                    verdict = "混戦・波乱含み（手広く）"
    else:                                              verdict = "中間（軸+相手厚め）"
    # 荒れ度スコア（大きいほど荒れやすい／並べ替え用）
    score = max(0, 0.30 - p1) * 100 + max(0, 0.08 - gap_p) * 120 + max(0, 0.60 - top3share) * 50
    race = {"ichii": ichii, "gap12": gap12, "goukei": goukei,
            "p1": round(p1, 3), "gap_p": round(gap_p, 3),
            "top3share": round(top3share, 3), "arate_score": round(score, 1),
            "verdict": verdict, "n": len(horses)}
    return horses, race

def compi(rid, cache=None):
    return index_from_odds(fetch_odds(rid, cache))

def _fmt(rid, horses, race):
    out = [f"=== 南関版コンピ指数  rid={rid}  {race['n']}頭 ==="]
    out.append(f"1位指数 {race['ichii']} ｜ 1-2位差 {race['gap12']} ｜ 上位5合計 {race['goukei']}"
               f" ｜ 上位3占有 {race['top3share']*100:.1f}%")
    out.append(f"荒れ度 {race['arate_score']} → 【{race['verdict']}】")
    out.append("-" * 46)
    out.append(" 順  馬番  指数   勝率   単勝  馬名")
    for i, h in enumerate(horses, 1):
        out.append(f"{i:>2}   {h['ub']:>2}   {h['idx']:>2}   {h['p']*100:4.1f}%  {h['odds']:>6}  {h['name']}")
    return "\n".join(out)

if __name__ == "__main__":
    rid = sys.argv[1] if len(sys.argv) > 1 else "2026111003110724"
    hs, rc = compi(rid)
    print(_fmt(rid, hs, rc))
