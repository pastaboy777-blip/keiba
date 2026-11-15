#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""その日1日を読む。**終わった鞍だけ**から、その日の性格を出す。

なぜこれを最初に回すのか:
  予想の前に「今日はどういう日か」を決めないと、材料の重みが決まらない。
  そして今日の性格は、過去の開催からは出てこない。**今日の終わった鞍にしか無い。**

出すもの:
  ① 上がり3F順位と着順の関係 ── その日を1本で説明する変数はたいていこれ
  ② 1番人気の着順            ── 軸を人気に置いていいか
  ③ 枠                      ── 内外
  ④ 上がり幅                ── 広いほど「ふるい」。馬場が脚を削っている

2026-09-15 大井（終日 不良）での実測:
      1-3着の36枠のうち 30枠（83%）が上がり3位以内
      1着の上がり順位 平均1.8位 / 2着 2.3位 / 3着 3.0位
      1番人気 勝ち6/11・3着内8/11
  → この日は「最後まで走れた馬から順に決まる」日だった。位置取りではない。
  ※これは2026-09-15の大井の話で、他の日に持ち越さない。毎日測り直すこと。

使い方:
    python3 scripts/ana/nichi.py --date 20260915 --place 大井
    python3 scripts/ana/nichi.py --date 20260915 --place 大井 --upto 9
"""
from __future__ import annotations

import argparse
import re
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kb


def rank_map(rows):
    """上がり3F の速い順の順位。伏せられている鞍では空になる。"""
    ag = sorted(r["agari"] for r in rows if r["agari"])
    return {r["ub"]: ag.index(r["agari"]) + 1 for r in rows if r["agari"]}, len(ag)


def zone(d):
    return "短" if d <= 1200 else ("マ" if d <= 1700 else "長")


def main():
    ap = argparse.ArgumentParser(description="その日の性格を、終わった鞍から出す")
    ap.add_argument("--date", required=True, help="YYYYMMDD")
    ap.add_argument("--place", default="大井")
    ap.add_argument("--races", type=int, default=12)
    ap.add_argument("--upto", type=int, help="このRまでで読む（予想する鞍の直前まで）")
    a = ap.parse_args()

    pre = kb.prefix(a.date, a.place)
    if not pre:
        print(f"× {a.date} に {a.place} の開催が見つかりません")
        return

    hi = a.upto or a.races
    done, slots, top3 = [], [], 0
    print(f"■ {a.place} {a.date}   開催コード {pre}"
          + (f"   （{hi}Rまでで読む）" if a.upto else ""))
    print(f"\n{'R':>3}{'距離':>7}{'回り':>4}{'馬場':>5}{'上り幅':>7}  "
          f"{'1着':<20}{'2着':<20}{'3着'}")
    for r in range(1, hi + 1):
        rid = kb.rid_of(pre, r, a.date)
        m, rows = kb.seiseki(rid)
        if not rows:
            print(f"{r:>3}{'':>7}{'':>4}{'':>5}{'':>7}  （未発走）")
            continue
        rk, nag = rank_map(rows)
        ag = [x["agari"] for x in rows if x["agari"]]
        if len(ag) < 5:
            continue
        done.append((r, m, rows, rk))
        cell = []
        for i in range(min(3, len(rows))):
            x = rows[i]
            k = rk.get(x["ub"])
            if k:
                slots.append(k)
                top3 += (k <= 3)
            cell.append(f"{x['ub']}番{x['odds'] or '-'}倍 上{k or '-'}位")
        print(f"{r:>3}{str(m['dist'])+'m':>7}{(m['course'] or '')[1:]:>4}"
              f"{(m['baba'] or '?'):>5}{max(ag)-min(ag):>6.1f}秒  "
              + "  ".join(f"{c:<18}" for c in cell))

    if not slots:
        print("\n上がり3Fが取れていません。")
        return

    # ① 上がり順位と着順
    print(f"\n■ ① 上がり3F順位 ── その日を説明する一番強い変数になりやすい")
    print(f"   1-3着の {len(slots)} 枠のうち、上がり3位以内から {top3} "
          f"（{top3/len(slots)*100:.0f}%）")
    for i, lab in enumerate(("1着", "2着", "3着")):
        v = [slots[j] for j in range(i, len(slots), 3)]
        if v:
            print(f"   {lab} の上がり順位 平均 {st.mean(v):.1f}位")
    # ★上がり順位を主変数にしてよいかの判定（2026-09-14 で裏目に出たので入れた）
    import statistics as _st
    spans = []
    for r, m, rows, rk in done:
        ag = [x["agari"] for x in rows if x["agari"]]
        spans.append(max(ag) - min(ag))
    rate = top3 / len(slots)
    span = _st.mean(spans)
    if rate >= 0.80 and span >= 4.0:
        v = ("主変数にしてよい",
             "軸は『この馬場で上がりを使えるか』に寄せる")
    elif rate >= 0.70:
        v = ("補助にとどめる",
             "**着順と併せて読む。上がり順位だけで人気馬を落とさない**")
    else:
        v = ("使わない", "前が止まっていない。位置取りと当条件で読む")
    print(f"\n   判定: 上がり3位以内 {rate*100:.0f}% / 上がり幅 平均{span:.1f}秒"
          f"  →  **{v[0]}**")
    print(f"        {v[1]}")
    print("   ※多頭数(12頭超)の1400m以下は、この判定に関わらず上がり順位を使わない。")
    print("     2026-09-14 大井11R（1400m 16頭）は 1着が上り7位・3着が上り9位だった。")
    print("   ※上がり順位は『差した馬』を拾い『前で粘って勝った馬』を落とす。")
    print("     前走を1着でも上がり順位が下位なら、それは弱さではなく前にいた証拠。")

    # ② 人気
    print(f"\n■ ② 1番人気")
    fav, w, t = [], 0, 0
    for r, m, rows, rk in done:
        f = min((x for x in rows if x["odds"]), key=lambda x: x["odds"], default=None)
        if not f:
            continue
        fav.append(f"{r}R:{f['chaku']}着({f['odds']}倍)")
        w += f["chaku"] == 1
        t += f["chaku"] <= 3
    print("   " + "  ".join(fav))
    print(f"   勝ち {w}/{len(fav)}   3着内 {t}/{len(fav)}")

    # ③ 枠
    print(f"\n■ ③ 枠（1-3着の馬番を、頭数で内/中/外に割る）")
    cnt = {"内": 0, "中": 0, "外": 0}
    for r, m, rows, rk in done:
        n = len(rows)
        for x in rows[:3]:
            u = int(x["ub"])
            cnt["内" if u <= n/3 else ("中" if u <= n*2/3 else "外")] += 1
    tot = sum(cnt.values()) or 1
    print("   " + "   ".join(f"{k} {v}枠 ({v/tot*100:.0f}%)" for k, v in cnt.items()))

    # ④ 上がり幅
    print(f"\n■ ④ 上がり幅（広いほど馬場が脚を削っている＝ふるい）")
    for r, m, rows, rk in done:
        ag = [x["agari"] for x in rows if x["agari"]]
        span = max(ag) - min(ag)
        bar = "█" * int(span * 2)
        print(f"   {r:>2}R {m['dist']}m {zone(m['dist'])} {span:>5.1f}秒 {bar}")
    # ⑤ 3着内の4角の位置
    print(f"\n■ ⑤ 3着内の馬は4角でどこにいたか（頭数で前1/3・中・後1/3に割る）")
    zen_rows(done)
    print("\n   ※ここで出た性格は【その日のもの】。翌日に持ち越さないこと。")


def c4_of(pas):
    """通過順位「3-3-2-1」の最後＝最終4角。伏せ字や空は None。"""
    q = [int(y) for y in re.findall(r"\d+", pas or "")]
    return q[-1] if q else None


def zen_rows(done):
    """⑤ 前後の傾向 ── 2026-11-15、中央からの申し送り（handoff_jra_to_nankan.md 1-1）。

    中央では「今日ここまでの3着内が4角でどこにいたか」を後半の狙いに使った。
    前後の傾向は当てになり、内外は当てにならなかった。なので**前後だけ**を出す。

    ★ ふだんの平均とは比べない（CLAUDE.md 最優先ルール。「過去◯日と比べて」をしない）。
      中央の札は「ふだん比 ±15pt」で出していたが、南関ではその比べ方をしない。
      **今日の鞍だけの数**を並べる。どう読むかは人が決める。
    ★ 内外は出さない（ルール12・14。1日の内外は当てにならず、単独の馬は記録されない）。
    ★ 通過順位が伏せ字（cookie 切れ）の鞍は数えない。数えられなかった鞍は言う。
    """
    cnt = {"前": 0, "中": 0, "後": 0}
    miss = []
    for r, m, rows, rk in done:
        n = len(rows)
        cell = []
        for x in rows[:3]:
            c = c4_of(x.get("pas"))
            if c is None or n < 2:
                cell.append("?")
                continue
            rel = (c - 1) / (n - 1)
            k = "前" if rel < 1 / 3 else ("中" if rel < 2 / 3 else "後")
            cnt[k] += 1
            cell.append(f"{x['ub']}番{k}({c}/{n})")
        if all(c == "?" for c in cell):
            miss.append(f"{r}R")
            continue
        print(f"   {r:>2}R {m['dist']}m  " + "  ".join(cell))
    tot = sum(cnt.values())
    if not tot:
        print("   通過順位が取れていません（cookie 切れで伏せ字の可能性。ルール5）")
        return
    print("   今日ここまで " + "   ".join(
        f"{k} {v}頭 ({v / tot * 100:.0f}%)" for k, v in cnt.items()) + f"   計{tot}頭")
    if miss:
        print(f"   ※通過順位が無く数えていない鞍: {' '.join(miss)}")
    print("   ※前に偏った日は、後半の丸に「前へ出られる馬」を入れる。差しに偏った日はその逆。")
    print("     隊列（並び）は前日のまま変えない。変えるのは狙いだけ。")


if __name__ == "__main__":
    main()
