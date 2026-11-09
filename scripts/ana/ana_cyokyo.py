#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""荒れたレースで絡んだ人気薄の調教推移を、対照つきで出す。

★この道具は【結果で切ってから中身を見る】形をしている。
  これは今回のセッションで4回落ちた形（きついラップ組・中山×人気薄・
  父の残差・調教の上昇度）と同じ構造で、そのままでは検証にならない。
  穴をあけた馬の調教を50頭並べれば、必ず何か共通点が見つかる。
  だが「同じ調教をして凡走した馬」が見えていないので、条件にはならない。

  よって本ツールは必ず【対照】を並べる:
      ① 人気薄で3着内に来た馬     ← 見たいもの
      ② 同じレースの1-2番人気     ← 上位人気の標準形
      ③ 同じレースの人気薄で着外   ← ★いちばん大事な対照
  ③と①が同じ顔をしていたら、それは条件ではない。

使いかたの前提:
  仮説を【作る】ためだけに使う。作った仮説は、これから走るレースで
  前向きに確かめること。この表そのものは根拠にならない。

使い方:
    python3 scripts/ana/ana_cyokyo.py --pre 2026091101 --mmdd 0818
    python3 scripts/ana/ana_cyokyo.py --pre 2026091101 --mmdd 0818 --ninki 8
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cyokyo_jikei as C

ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)


def result(rid):
    """成績ページ → [{着順,馬番,馬名,人気,オッズ,体重,増減}]"""
    h = C.get(f"{C.BASE}/chihou/seiseki/{rid}", C.ARC + f"/sei_{rid}.html")
    out = []
    for m in ROW.finditer(h):
        c = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", x)).strip()
             for x in re.findall(r"<td[^>]*>(.*?)</td>", m.group(1), re.S)]
        if len(c) < 18 or not c[0].isdigit():
            continue
        nums = [i for i, x in enumerate(c) if re.fullmatch(r"\d{3}", x)]
        wi = nums[-1] if nums else None
        try:
            nin = next(int(x) for x in c[15:wi or len(c)] if x.isdigit())
        except StopIteration:
            nin = None
        out.append(dict(chaku=int(c[0]), ub=c[4], name=c[5], nin=nin,
                        w=int(c[wi]) if wi else None,
                        dw=c[wi + 1] if wi and wi + 1 < len(c) else None))
    return out


def kyo(rows, name):
    """1頭の調教推移を、走ごとに1行で圧縮して返す。"""
    g = {}
    for q in rows:
        g.setdefault(q.get("rid", ""), []).append(q)
    out = []
    for k in sorted(g, key=C.ymd):
        rep = C.main_work(g[k])
        if not rep:
            continue
        m = C.race_meta(k)
        w, dw = C.weight_of(k, name)
        out.append(f"{m['mm']}/{m['dd']}{m['place'][:2]} "
                   f"{rep['f3'] or 0:.1f}/{rep['ashi'] or '—'}"
                   f"/{len(g[k])}本" + (f"/{w}({dw})" if w else ""))
    return out


def main():
    ap = argparse.ArgumentParser(description="人気薄好走馬の調教推移（対照つき）")
    ap.add_argument("--pre", required=True)
    ap.add_argument("--mmdd", required=True)
    ap.add_argument("--races", default="1-12")
    ap.add_argument("--ninki", type=int, default=6, help="この人気以下を『人気薄』とする")
    ap.add_argument("--back", type=int, default=4)
    a = ap.parse_args()

    lo, _, hi = a.races.partition("-")
    for r in range(int(lo), int(hi or lo) + 1):
        rid = f"{a.pre}{r:02d}{a.mmdd}"
        res = result(rid)
        if not res:
            continue
        hits = [x for x in res if x["chaku"] <= 3 and (x["nin"] or 0) >= a.ninki]
        if not hits:
            continue
        H = C.with_history(rid, a.back)
        idx = {h["name"]: h for h in H.values()}
        m = C.race_meta(rid)
        print(f"\n{'='*78}\n■ {r}R  {m['name'][:24]}   "
              f"人気薄で3着内 {len(hits)}頭\n{'='*78}")

        def show(tag, xs):
            for x in xs:
                h = idx.get(x["name"])
                line = kyo(h["rows"], x["name"]) if h else []
                print(f"  {tag} {x['chaku']:>2}着 {x['nin'] or 0:>2}人気 "
                      f"{x['name']:<14}{x['w'] or 0}({x['dw'] or ''})")
                print("       " + ("  →  ".join(line) if line else "（調教なし）"))

        show("★", hits)
        print("  ─── 対照 ───")
        show("  ", [x for x in res if (x["nin"] or 99) <= 2])
        show("  ", [x for x in res if x["chaku"] > 3 and (x["nin"] or 0) >= a.ninki][:3])
    print("\n※ ★と、下の『人気薄で着外』が同じ顔なら、それは条件ではありません。")
    print("  この表は仮説を作るためのもので、根拠にはなりません。")


if __name__ == "__main__":
    main()
