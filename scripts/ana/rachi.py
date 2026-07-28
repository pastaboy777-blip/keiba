#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""4角の通過順位から「どこを通ったか」を逆算し、その日のラチ沿いバイアスを出す。

通過順位の表記規約：括弧()は併走を表し、括弧の中は【内側の馬から順に】書かれる。
  例) 4角[(4,7),2,(1,3)] → 4が最内で先頭、7はその外、2は単独、1は内で3はその外。

区分:
  先頭            4角で1番手
  ラチ沿い追走    先頭以外で、併走グループの最内
  外を回す        併走グループの2頭目以降
  単独(証拠なし)  単独表記＝内外の手がかりなし（後方馬に多い）

使い方:
  python3 scripts/ana/rachi.py <楽天RACEID接頭辞16桁> [レース数]
  例) python3 scripts/ana/rachi.py 2026072721150601
"""
import re, subprocess, os, sys
from collections import Counter

TMP = os.environ.get("RACHI_TMP", "/tmp/rachi")
os.makedirs(TMP, exist_ok=True)

def fetch(pre, RR):
    fp = f"{TMP}/{pre}{RR:02d}.html"
    if not (os.path.exists(fp) and os.path.getsize(fp) > 20000):
        subprocess.run(["curl", "-s", "-L", "--max-time", "20",
                        f"https://keiba.rakuten.co.jp/race_performance/list/RACEID/{pre}{RR:02d}",
                        "-o", fp], check=False)
    return open(fp, encoding="utf-8", errors="replace").read()

def parse(t):
    y = re.sub(r"<[^>]+>", "|", t); y = re.sub(r"[ 　]+", " ", y); y = re.sub(r"\|{3,}", "||", y)
    i = y.find("着順"); j = y.find("■|払戻金")
    order = []
    if i >= 0 and j > i:
        seg = re.sub(r"\s+", " ", y[i:j])
        for m in re.finditer(r"\|(\d{1,2})\| \|(\d{1,2})\| \|(\d{1,2})\| \|", seg):
            order.append((int(m.group(1)), int(m.group(3))))     # (着順, 馬番)
    c4 = re.search(r"４角\| \|([^|]+)\|", re.sub(r"\s+", " ", y))
    d = re.search(r"ダ\s*([\d,]+)m", re.sub(r"<[^>]+>", " ", t))
    return order, (c4.group(1).strip() if c4 else ""), (d.group(1).replace(",", "") if d else "?")

def classify(c4):
    """馬番 -> (区分, 4角順位)"""
    out, rank = {}, 0
    for tok in re.findall(r"\([^)]*\)|\d+", c4):
        if tok.startswith("("):
            for k, u in enumerate(int(v) for v in re.findall(r"\d+", tok)):
                rank += 1
                out[u] = ("先頭" if rank == 1 else ("ラチ沿い追走" if k == 0 else "外を回す"), rank)
        else:
            rank += 1
            out[int(tok)] = ("先頭" if rank == 1 else "単独(証拠なし)", rank)
    return out

KEYS = ["先頭", "ラチ沿い追走", "外を回す", "単独(証拠なし)"]


def _table(label, tot, hit, win):
    N = sum(tot.values())
    if not N: return None
    base = sum(hit.values())/N
    print(f"\n── {label}（{N}頭）──")
    print(f"{'区分':<16}{'頭数':>5}{'1着':>5}{'3着内':>6}{'3着内率':>9}{'倍率':>7}")
    for k in KEYS:
        if not tot[k]: continue
        p = hit[k]/tot[k]
        print(f"{k:<16}{tot[k]:>5}{win[k]:>5}{hit[k]:>6}{p*100:>8.1f}%{p/base:>7.2f}")
    print(f"{'全体':<16}{N:>5}{sum(win.values()):>5}{sum(hit.values()):>6}{base*100:>8.1f}%{1.0:>7.2f}")
    return {k: (hit[k]/tot[k]/base if tot[k] else None) for k in KEYS}


def run(pre, upto=12):
    tot, hit, win = Counter(), Counter(), Counter()
    H = {"前半": [Counter(), Counter(), Counter()], "後半": [Counter(), Counter(), Counter()]}
    print(f"■ ラチ沿い逆算  {pre}\n")
    for RR in range(1, upto+1):
        order, c4, dist = parse(fetch(pre, RR))
        if not order: continue
        r = classify(c4)
        half = "前半" if RR <= 6 else "後半"
        print(f"{RR:>3}R {dist:>5}m  4角[{c4}]")
        print("      " + " / ".join(f"{ch}着{ub}{r.get(ub,('?',0))[0]}" for ch, ub in sorted(order)[:3]))
        for ch, ub in order:
            k = r.get(ub, ("?", 0))[0]
            tot[k] += 1; H[half][0][k] += 1
            if ch <= 3: hit[k] += 1; H[half][1][k] += 1
            if ch == 1: win[k] += 1; H[half][2][k] += 1
    if not sum(tot.values()): print("データなし"); return
    _table("4角のポジション別 3着内率", tot, hit, win)
    a = _table("前半 1R〜6R", *H["前半"])
    b = _table("後半 7R〜12R", *H["後半"])
    print("\n読み方：先頭が突出して後ろの内が沈むなら『ハナ有利・内は蓋をされると終い甘い』。")
    print("        外を回した馬が差してくるなら、穴は外を使える枠から取る。")
    _shift(a, b)


def _shift(a, b):
    """前後半の向きを当日実測で判定する。

    ※川崎84R(2026/7/6-7/10, 7/27, 7/28)で検証したところ、
      「後半ほどハナが強くなる」は日替わりで事前には決められない。
        先頭の倍率 前半→後半：7/6 2.07→1.13 / 7/7 3.33→1.13 / 7/8 2.96→1.19
                              7/9 1.74→2.48 / 7/10 2.08→1.56 / 7/27 1.81→2.87 / 7/28 1.89→3.15
      5日が下降・2日が上昇。平均すると前半2.25 → 後半1.91 でむしろ前半のほうがハナ有利。
      よって固定の補正は入れず、6R終了時点の実測で向きを出す。

    一方で配当だけは全7日で安定して後半が高い：
      三連単 中央値 前半5,150円 → 後半14,740円 ／ 1万超 31%(13/42) → 60%(25/42)
      → 勝負するなら7R以降、は事前に使ってよい。
    """
    if not (a and b): 
        print("\n（前後半の比較には1R〜6Rと7R以降の両方が必要）")
        return
    print("\n── 前後半の向き（当日実測）──")
    for k in ("先頭", "外を回す"):
        x, y = a.get(k), b.get(k)
        if x is None or y is None: continue
        arrow = "↑強まる" if y - x >= 0.3 else ("↓弱まる" if x - y >= 0.3 else "→ほぼ変化なし")
        print(f"  {k:<8} 前半{x:.2f} → 後半{y:.2f}  {arrow}")
    d = (b.get("先頭") or 0) - (a.get("先頭") or 0)
    if d >= 0.3:
        print("  → 後半はハナを取れる馬に絞る。外から差す馬は評価を下げる。")
    elif d <= -0.3:
        print("  → 後半はハナの利が薄れている。前に行く馬の頭固定は緩めて相手を広げる。")
    else:
        print("  → 前後半で位置バイアスは変わっていない。前半の読みをそのまま延長してよい。")
    print("  ※配当は全日で後半のほうが高い（84R検証：三連単中央 前半5,150円→後半14,740円、")
    print("    1万超31%→60%）。勝負を厚くするなら7R以降。")

if __name__ == "__main__":
    run(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 12)
