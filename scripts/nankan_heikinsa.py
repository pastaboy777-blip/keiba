#!/usr/bin/env python3
"""「脚は出ていたのに着外だった」馬を、事前に拾えるか測る。

ユーザー提示（2026-08-16）の条件をそのまま道具にしたもの。

    過去3走のうち、**上がりのレース平均差が しきい値以下**（メンバー平均より
    それだけ速い脚）で、**かつ4着以下**だった走りが1回以上ある馬。

    → 脚は出ていた。着順に結びついていなかっただけ。
      市場は着順しか見ないので、人気が下がり続ける。そこが取りどころ。

対照群として「**速い脚を使って、ちゃんと3着内に入っていた**馬」も同時に測る。
こちらが効かなければ、「**着順に結びついていない**」ことが本質だという証明になる。

    python3 scripts/nankan_heikinsa.py --place 大井 --from 2026-08-12 --to 2026-08-16

⚠️ 恒久ルール5により、**目の前の開催しか見ない**。期間を広げて回さないこと。
⚠️ 過去走のレース平均上がりは `data/bt/runs.jsonl` から引く。そこに無いレースは
   **材料なし**として数え、カバー率を必ず表示する（黙って落とさない）。

── 実測（大井 2026-08-12〜08-16・578頭）────────────────────────

⚠️⚠️ **この条件は棄却された。当たらなかったことをそのまま残す（恒久ルール4）。**

    全体                          3着内 26.0%  複勝回収 68.1%

    しきい値 -1.0（平均差 / 残差）
      ★ 濃い脚 × 着外   3着内 19.7% / 15.8%   複勝回収 58.3% / 41.1%  ← **全体より下**
        濃い脚 × 3着内   3着内 40.8% / 44.9%   複勝回収 67.4% / 68.6%

    しきい値を -0.8 → -1.2 と厳しくすると、**本命群はさらに下がり
    （20.8%→12.8%）、対照群は上がる（38.2%→46.2%）**。方向が一貫している。

  ① 「濃い脚を使ったのに着外」は、それ単体では次走の材料に**ならない**。
  ② 効いているのは「**3着内に入っていた**」ほうだけ。ただし複勝回収は全体と
     同じ（62〜76%）＝**オッズに完全に織り込まれている**。儲けにはならない。
  ③ 「平均差ではなく残差（位置×展開を補正）にすれば直る」も**棄却**。悪化した。

── 残った線（まだ潰れていない）────────────────────────────

    同じ66頭を「今回の4角位置が前走より上がったか」で割ると方向は出る:

        位置が大きく上がった(0.20以上)  n=21  3着内 38.1%  複勝回収 137.6%
        ほぼ同じ                        n=11  3着内  9.1%  複勝回収  19.1%
        位置が下がった                  n=17  3着内 17.6%  複勝回収  32.9%

    ⚠️ **これは事前の条件ではない。**「今回の位置」はレース後にしか分からない。
    ⚠️ **n=21 のうちコスモトロイメル1頭（複勝1,170円）で回収率の4割。**
       この馬を抜くと 137.6% → **86.0%**。結論は出せない。

    次に組むなら「位置が上がるか」を**事前に分かる材料**（距離延長・内枠替わり・
    メンバーの先行型が少ない）に置き換える。材料は `core/mhousoku.py` にある。
"""

from __future__ import annotations

import argparse
import json
import os
import statistics as stt
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import soutai                            # noqa: E402
from nankeiba.scraping import rakuten as rk                  # noqa: E402

RUNS = "data/bt/runs.jsonl"
#: 過去何走を見るか。
LOOKBACK = 3
#: 「7番人気以下」を人気薄とみなす。
UNPOP = 7


def load_means(mode: str = "diff") -> tuple[dict, dict]:
    """runs.jsonl から (レース平均上がり, 1頭1走の指標) を作る。

    mode="diff"     … ①レース内相対だけ（**平均差**）
    mode="residual" … ①②③を全部使う（**残差** = 平均差 − 位置×展開の期待値）

    ⚠️ **平均差と残差は別物。**後方から追えば平均差はマイナスに出るのが標準
       （後40%×前が楽 で +0.31、×前が止まった で -0.23）。平均差だけで拾うと
       **ただの追い込み馬リスト**になる。残差はその標準ぶんを引いてある。

    return: (`mean[...]`, `diff[(date,place,distance,馬名)] = (指標, 着順)`)
    """
    by_rid: dict = defaultdict(list)
    for line in open(RUNS, encoding="utf-8"):
        r = json.loads(line)
        by_rid[r["rid"]].append(r)
    mean: dict = defaultdict(list)
    diff: dict = {}
    for rid, rs in by_rid.items():
        ag = [x["agari"] for x in rs if x.get("agari")]
        if len(ag) < 4:
            continue
        ma = stt.mean(ag)
        h = rs[0]
        key = (h["date"], h["place"], h["distance"])
        mean[key].append((rid, ma, {x["name"] for x in rs}))
        fs = h.get("field_size") or len(rs)
        fr = [x["agari"] - ma for x in rs
              if x.get("agari") and soutai.pos_band(x.get("corner4"), fs) == "前"]
        flow = "止" if (stt.mean(fr) if fr else 0.0) > soutai.STOPPED else "楽"
        for x in rs:
            if not x.get("agari"):
                continue
            d = round(x["agari"] - ma, 2)
            if mode == "residual":
                b = soutai.pos_band(x.get("corner4"), fs)
                e = soutai.EXPECTED.get((b, flow)) if b else None
                if e is None:            # 通過順が無ければ材料なし
                    continue
                d = round(d - e, 2)
            diff[(h["date"], h["place"], h["distance"], x["name"])] = (
                d, x.get("finish"))
    return mean, diff


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--place", default="大井")
    ap.add_argument("--from", dest="lo", required=True)
    ap.add_argument("--to", dest="hi", required=True)
    ap.add_argument("--thresholds", default="-0.8,-1.0,-1.2")
    ap.add_argument("--lookback", type=int, default=LOOKBACK)
    ap.add_argument("--mode", choices=["diff", "residual"], default="diff",
                    help="diff=平均差だけ / residual=位置と展開を補正した残差")
    args = ap.parse_args()

    mean, diff = load_means(args.mode)
    cli = rk.KeibaRakuten()

    days = sorted({d for d in _days(args.lo, args.hi)})
    rows = []          # 1頭1行（対象開催の出走馬）
    nocov = 0
    for d in days:
        ymd = d.replace("-", "")
        try:
            base = cli.find_race_id(ymd, args.place, 1)[:-2]
        except Exception:                                    # noqa: BLE001
            continue
        for rno in range(1, 13):
            rid = f"{base}{rno:02d}"
            try:
                raw = cli.get(f"/race_performance/list/RACEID/{rid}")
                res = rk.parse_result(raw)
            except Exception:                                # noqa: BLE001
                continue
            if not res:
                continue
            pay = rk.parse_place_payout(raw)
            try:
                card = rk.parse_card(cli.get(f"/race_card/list/RACEID/{rid}"))
            except Exception:                                # noqa: BLE001
                continue
            hist = {e["name"]: (e.get("history") or []) for e in card["entries"]}
            for r in res:
                ev = []
                for h in hist.get(r["name"], [])[:args.lookback]:
                    ev.append(diff.get((h.date, h.place, h.distance, r["name"])))
                if not ev or all(x is None for x in ev):
                    nocov += 1
                rows.append({
                    "date": d, "race": rno, "name": r["name"],
                    "finish": r["finish"], "pop": r.get("popularity"),
                    "pay": pay.get(r["umaban"], 0),
                    "ev": [x for x in ev if x is not None],
                    "ncov": sum(1 for x in ev if x is not None), "nhist": len(ev),
                })
    print(f"■ {args.place} {args.lo}〜{args.hi}　指標={args.mode}　出走 {len(rows)}頭"
          f"／過去走の平均差が1走も引けなかった馬 {nocov}頭"
          f"（カバー率 {(1-nocov/max(len(rows),1))*100:.0f}%）")
    print(f"  払戻が取れたレースの馬 {sum(1 for x in rows if x['pay'] or x['finish']>3)}頭\n")

    def report(label, sel):
        n = len(sel)
        if not n:
            print(f"  {label:<34} n=0")
            return
        hit = sum(1 for x in sel if x["finish"] <= 3)
        ret = sum(x["pay"] for x in sel) / (100 * n) * 100
        print(f"  {label:<34} n={n:>4}  3着内 {hit:>3} ({hit/n*100:>5.1f}%)"
              f"  複勝回収 {ret:>6.1f}%")

    for thr in [float(x) for x in args.thresholds.split(",")]:
        print(f"── しきい値 {thr:+.1f}秒 " + "─" * 42)
        # 本命群：速い脚 × 着外
        hid = [x for x in rows if any(d <= thr and f is not None and f >= 4
                                      for d, f in x["ev"])]
        # 対照群：速い脚 × 3着内（本命群に入らないものだけ）
        ctl = [x for x in rows if x not in hid
               and any(d <= thr and f is not None and f <= 3 for d, f in x["ev"])]
        rest = [x for x in rows if x not in hid and x not in ctl]
        report("全体", rows)
        report("★ 速い脚 × 着外（本命群）", hid)
        report("　 速い脚 × 3着内（対照群）", ctl)
        report("　 どちらでもない", rest)
        print()
        u = [x for x in rows if (x["pop"] or 99) >= UNPOP]
        report(f"{UNPOP}番人気以下・全体", u)
        report(f"{UNPOP}番人気以下・★本命群", [x for x in hid if (x["pop"] or 99) >= UNPOP])
        report(f"{UNPOP}番人気以下・対照群", [x for x in ctl if (x["pop"] or 99) >= UNPOP])
        print()


def _days(lo: str, hi: str):
    from datetime import date, timedelta
    a = date.fromisoformat(lo)
    b = date.fromisoformat(hi)
    while a <= b:
        yield a.isoformat()
        a += timedelta(days=1)


if __name__ == "__main__":
    main()
