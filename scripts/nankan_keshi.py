#!/usr/bin/env python3
"""**穴は見抜けない。穴でない人気薄を消す。**

このセッションで穴を当てる「買い材料」を10通り試して、10回とも失敗した
（濃い脚×着外／位置を上げてくる／乗り替わり／過去の騎手が下手→上手いへ／
状態の傾き／ペースの犠牲 ほか）。**人気薄の3着内率 7〜10% を上げられたものが
一つも無かった。**

一方で「消し材料」は、試したものがほぼ全部効いた。だから向きを変える。

    穴を見抜くのではなく、**穴でない人気薄を全部消して、残りを買う。**

── 実測（大井 2026-08-12〜17 ＋ 川崎 08-18・7日・人気薄374頭）──────

                            n     3着内    複勝回収   上位3件抜き
    ① 出発点（7番人気以下）   374    7.8%     56.2%      37.8%
    ② 馬体重 +3kg以上を切る   237    9.3%     73.2%      44.3%
    ③ 位置を下げる馬を切る     165   10.9%     92.5%      51.0%
    ④ 状態が悪化を切る        131   12.2%     78.2%      50.9%
    ⑤ 過去の騎手が下手を切る   100  **15.0%** **94.4%**  **58.9%**

  **全ステップで3着内率が単調に上がる。**上位3件の配当を抜いても 37.8→58.9。

── なぜ消しだけが効くのか（このセッションの解釈）─────────────

  買い材料は「市場より正確に強さを当てる」ことを要求する。人気薄の帯では
  それが一度もできなかった。消し材料は「明らかに来ない馬を外す」だけなので、
  市場より正確である必要がない。**人は買う理由を探すので、切る側の情報のほうが
  織り込みが甘い**、という説明とも整合する。

⚠️⚠️ **決定的な弱点：4つのルールを、この同じ7日で作って同じ7日で測っている。**
   ②③④の閾値はこの期間の分位から取った。**当然よく出る。**
   ⑤だけは騎手の点数を 8/12 より前のデータで作っているので、そこは漏れていない。
   **次の開催で確かめるまで信じないこと。**

⚠️ 100頭まで絞ると1レースあたり1〜2頭しか残らない。買い目としては薄い。
⚠️ 複勝回収 94.4% は**まだ100%に届いていない**。「良い母集団」であって
   「儲かる馬券」ではない。

⚠️⚠️⚠️ **場で割ると崩れる。大井では効き、川崎では効かない。**

      日付       場   出発 3着内  → くぐった 3着内  複勝回収
      08-12    大井    54    5        14    3    175%
      08-13    大井    61    4        20    3     61%
      08-14    大井    56    5        17    3    116%
      08-15    大井    57    4        13    1     49%
      08-16    大井    52    4         8    3    316%
      08-17    大井    46    3         8    1     39%
      **08-18   川崎    48    4        20    1     16%**   ← 唯一の川崎で失敗

      大井だけ  出発326頭 7.7% → くぐった80頭 **17.5%** 複勝114.0%
      川崎だけ  出発 48頭 8.3% → くぐった20頭 ** 5.0%** 複勝 16%

   **標本の87%が大井なので、閾値が大井に合っているだけの可能性が高い。**
   同じことが `nankan_norikae.py`（乗り替わり）でも起きた ── **大井で出て
   川崎で反転**。これで2回目。**場ごとに作り直すか、単なる過適合か、
   まだ分けられていない。**

    python3 scripts/nankan_keshi.py --place 大井 --from 2026-08-12 --to 2026-08-17
"""

from __future__ import annotations

import argparse
import json
import os
import statistics as stt
import sys
from collections import defaultdict
from datetime import date as _date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from nankeiba.core import soutai                            # noqa: E402
from nankeiba.scraping import rakuten as rk                 # noqa: E402
from nankan_kishu import jockey_scores, norm                # noqa: E402
from nankan_move import scan_cache                          # noqa: E402

RUNS = "data/bt/runs.jsonl"
UNPOP = 7
#: ② 馬体重がこれを超えて増えていたら切る[kg]。実測で +3〜+8 が 5.5%、+9〜 が 3.6%
#:    （人気薄の全体は 7.8%）。**人気馬では効かない。人気薄の帯にだけ出る。**
W_GAIN = 2
#: ③ 補正後の位置変動がこれを超えていたら切る（道中で下げる馬）。
MOVE_BAD = 0.05
#: ④ 上がり残差の傾きがこれ以上なら切る（状態が悪化）[秒/走]。
TREND_BAD = 0.35
#: ⑤ 過去3走の騎手の平均点がこれ以上なら切る（下手な騎手が続いていた＝弱い馬）。
JOCKEY_BAD = 0.05


def residuals() -> dict:
    """`(日付, 馬名) -> 上がり残差`。"""
    by: dict = defaultdict(list)
    for line in open(RUNS, encoding="utf-8"):
        r = json.loads(line)
        by[r["rid"]].append(r)
    out = {}
    for rs in by.values():
        ag = [x["agari"] for x in rs if x.get("agari")]
        if len(ag) < 6:
            continue
        ma = stt.mean(ag)
        fs = rs[0].get("field_size") or len(rs)
        fr = [x["agari"] - ma for x in rs if x.get("agari")
              and soutai.pos_band(x.get("corner4"), fs) == "前"]
        flow = "止" if (stt.mean(fr) if fr else 0.0) > soutai.STOPPED else "楽"
        for x in rs:
            if not x.get("agari"):
                continue
            b = soutai.pos_band(x.get("corner4"), fs)
            e = soutai.EXPECTED.get((b, flow)) if b else None
            if e is not None:
                out[(rs[0]["date"], x["name"])] = x["agari"] - ma - e
    return out


def slope(v: list) -> float | None:
    """3点の最小二乗の傾き。⚠️ **2点の引き算で取らないこと**（水準が消える）。"""
    if len(v) < 3:
        return None
    v = list(reversed(v))                        # 古い順
    xs = list(range(len(v)))
    mx, my = stt.mean(xs), stt.mean(v)
    return sum((a - mx) * (b - my) for a, b in zip(xs, v)) / sum((a - mx) ** 2
                                                                for a in xs)


def collect(cli, place, lo, hi, rmove, res, J) -> list:
    rows = []
    d = _date.fromisoformat(lo)
    while d <= _date.fromisoformat(hi):
        ymd = d.isoformat().replace("-", "")
        d += timedelta(days=1)
        try:
            base = cli.find_race_id(ymd, place, 1)[:-2]
        except Exception:                                   # noqa: BLE001
            continue
        for rno in range(1, 13):
            rid = f"{base}{rno:02d}"
            try:
                raw = cli.get(f"/race_performance/list/RACEID/{rid}")
                out = rk.parse_result(raw)
                card = rk.parse_card(cli.get(f"/race_card/list/RACEID/{rid}"))
            except Exception:                               # noqa: BLE001
                continue
            if not out or not card["entries"]:
                continue
            pay = rk.parse_place_payout(raw)
            hist = {e["name"]: (e.get("history") or []) for e in card["entries"]}
            for r in out:
                hs = hist.get(r["name"], [])[:3]
                mv = [rmove[(h.date, r["name"])] for h in hs
                      if (h.date, r["name"]) in rmove]
                rz = [res[(h.date, r["name"])] for h in hs
                      if (h.date, r["name"]) in res]
                jk = [J[j] for h in hs if (j := norm(h.jockey)) in J]
                rows.append(dict(
                    date=ymd, race=rno, name=r["name"], finish=r["finish"],
                    pop=r.get("popularity"), pay=pay.get(r["umaban"], 0),
                    wd=r.get("weight_diff"),
                    mv=(stt.mean(mv) if len(mv) >= 2 else None),
                    tr=slope(rz),
                    jk=(stt.mean(jk) if len(jk) >= 2 else None)))
    return rows


def survives(x) -> bool:
    """4つの消し材料を全部くぐったか。**材料が取れない馬は残す**（消さない）。"""
    if x["wd"] is not None and x["wd"] > W_GAIN:
        return False
    if x["mv"] is not None and x["mv"] > MOVE_BAD:
        return False
    if x["tr"] is not None and x["tr"] >= TREND_BAD:
        return False
    if x["jk"] is not None and x["jk"] >= JOCKEY_BAD:
        return False
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--place", default="大井")
    ap.add_argument("--from", dest="lo", required=True)
    ap.add_argument("--to", dest="hi", required=True)
    ap.add_argument("--score-until", default=None,
                    help="騎手の点数をこの日より前のデータで作る（既定 = --from）")
    ap.add_argument("--list", action="store_true", help="残った馬を並べる")
    args = ap.parse_args()

    J, _ = jockey_scores(args.score_until or args.lo)
    rows = collect(rk.KeibaRakuten(), args.place, args.lo, args.hi,
                   scan_cache(), residuals(), J)

    def rep(lab, sel):
        n = len(sel)
        if n < 6:
            print(f"  {lab:<32} n={n}")
            return
        hit = sum(1 for x in sel if x["finish"] <= 3)
        tot = sum(x["pay"] for x in sel)
        s = sorted((x["pay"] for x in sel), reverse=True)
        print(f"  {lab:<32} n={n:>4}  3着内 {hit:>3} ({hit/n*100:>5.1f}%)"
              f"  複勝回収 {tot/(100*n)*100:>6.1f}%"
              f"  上位3件抜き {(tot-sum(s[:3]))/(100*max(n-3,1))*100:>6.1f}%")

    u = [x for x in rows if x["pop"] is not None and x["pop"] >= UNPOP]
    print(f"\n=== {args.place} {args.lo}〜{args.hi} ===")
    print(f"■ 出走 {len(rows)}頭／{UNPOP}番人気以下 {len(u)}頭\n")
    rep("① 出発点", u)
    u = [x for x in u if not (x["wd"] is not None and x["wd"] > W_GAIN)]
    rep(f"② 馬体重 +{W_GAIN+1}kg以上を切る", u)
    u = [x for x in u if not (x["mv"] is not None and x["mv"] > MOVE_BAD)]
    rep("③ 道中で位置を下げる馬を切る", u)
    u = [x for x in u if not (x["tr"] is not None and x["tr"] >= TREND_BAD)]
    rep("④ 状態が悪化している馬を切る", u)
    u = [x for x in u if not (x["jk"] is not None and x["jk"] >= JOCKEY_BAD)]
    rep("⑤ 過去の騎手が下手な馬を切る", u)
    if args.list:
        print("\n■ 全部くぐった人気薄")
        for x in sorted(u, key=lambda y: (y["date"], y["race"])):
            print(f"   {x['date']} {x['race']:>2}R {x['name']:<12} "
                  f"{x['pop']}人気 → {x['finish']}着"
                  + (f"  複勝{x['pay']}円" if x["pay"] else ""))


if __name__ == "__main__":
    main()
