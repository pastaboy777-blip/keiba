#!/usr/bin/env python3
"""**過去走の騎手**にヒントがあるか測る。

ユーザー提示（2026-08-16）:

    下手な騎手が乗ると背中が硬くなって馬は走らなくなる。上手い騎手が乗ると
    背中の硬さが抜けて走るようになる。**穴馬に過去乗っていた騎手にヒント**。

仮説 ── **下手な騎手で乗られていた馬は、着順が実力を下回って記録されている。**
市場は着順しか見ないので人気が下がる。そこに上手い騎手が乗ったら穴になる。

── 騎手の巧拙をどう測るか ──────────────────────────────

⚠️⚠️ **生の騎手成績を使ってはいけない。**騎手間のばらつきは、
   **馬を固定しないと 0.183秒、固定すると 0.089秒**。**半分は馬の質**。
   減量騎手は弱い馬に乗るので、生のままだと構造的に下振れする
   （例：中山遥 生 56/106位 → 馬を固定 18/105位）。

   だからここでは **同じ馬の中で中心化した上がり残差** を騎手の点数とする。
   斤量ぶんも引く（実測 +0.0196秒/kg。通説「1kg=0.2秒」の1/10）。

⚠️⚠️ **点数を作るデータに、測る開催を入れないこと。**入れると答えが漏れる。
   `--score-until` より前の走だけで点数を作る。

    python3 scripts/nankan_kishu.py --place 大井 --from 2026-08-12 --to 2026-08-16

⚠️ 恒久ルール5により、**目の前の開催しか見ない**。

── 実測（大井 2026-08-12〜08-16・461頭）────────────────────────

⚠️⚠️ **仮説は逆向きに棄却された。** 過去3走の騎手が下手だった馬は、
   「着順が抑えられていた」のではなく **実際に弱い**。

      過去の騎手が上手い(上位20%) n=89  3着内 **42.7%**  複勝回収 99.6%(抜き87.4%)
      やや上手い                 n=95  3着内  23.2%   複勝回収 53.6%
      ふつう                    n=87  3着内  21.8%   複勝回収105.3%(抜き55.2%)
      やや下手                   n=97  3着内  20.6%   複勝回収 42.8%
      過去の騎手が下手(下位20%)   n=93  3着内 **11.8%**  複勝回収 30.6%(抜き22.2%)
      （この群の全体 n=461 3着内 23.9% 複勝回収 65.3%／抜き55.9%）

   **単調。**「どの騎手が乗っていたか」は集団で見ると**馬の質の代理**であって、
   抑圧の証拠ではない。上手い騎手は良い馬に乗る。馬を固定した騎手効果は
   標準偏差 0.089秒しかなく、馬の質の差に埋もれる。

  人気薄（7番人気以下）でも同じ:
      人気薄・全体                 n=242  3着内 7.4%  複勝回収 60.3%(抜き42.3%)
      × 過去が下手（下40%）         n=120  3着内 5.0%  複勝回収 23.1%(抜き16.5%)
      × 上手い方へ替わり（上40%）    n=160  3着内 8.8%  複勝回収 75.9%(抜き48.7%)
      × 両方                     n= 87  3着内 5.7%  複勝回収 24.1%(抜き15.0%)

  → **「過去が下手な騎手」は買い材料ではなく、強い消し材料。**
  → **「過去が上手い騎手」は、この開催で初めて全体を上回った買い側の群。**
     ただし穴ではない（強い馬を当てているだけ）。抜き87.4%はまだ控除率に届かない。

  参考：8/12より前で作った点数（104人中）
     小野俊 5位(-0.177) ／ 達城龍 20位(-0.068) ／ 中山遥 25位(-0.053)
     藤本現 40位(-0.017) ／ 和田譲 56位(+0.024) ／ **鷹見陸 81位(+0.063)**
     この開催で穴を出したのは上位寄りの騎手。鷹見陸は穴0本だった。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics as stt
import sys
from collections import defaultdict
from datetime import date as _date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import soutai                            # noqa: E402
from nankeiba.scraping import rakuten as rk                 # noqa: E402

RUNS = "data/bt/runs.jsonl"
LOOKBACK = 3
UNPOP = 7
#: 点数を出すのに必要な最低騎乗数（馬を固定したあとの本数）。
MIN_RIDES = 150
_MARK = re.compile(r"^[☆★▲△◇◆◎]+|[（(].*$")


def norm(j: str | None) -> str | None:
    """`'☆中山遥 (浦和)'` → `'中山遥'`。減量印と所属を落とす。

    ⚠️ **落とさないと同じ騎手が2人に割れる。**出馬表・馬柱・結果で表記が違う。
    """
    if not j:
        return None
    return _MARK.sub("", j).strip() or None


def jockey_scores(until: str) -> dict:
    """`until` より前の走だけで、**馬を固定した**騎手の点数を作る。

    マイナスほど「同じ馬から、同じ位置・同じ流れで速い脚を引き出した」。
    """
    by: dict = defaultdict(list)
    for line in open(RUNS, encoding="utf-8"):
        r = json.loads(line)
        if r["date"] < until:
            by[r["rid"]].append(r)
    horse: dict = defaultdict(list)
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
            j = norm(x.get("jockey"))
            if not x.get("agari") or not j or not x.get("kinryo"):
                continue
            b = soutai.pos_band(x.get("corner4"), fs)
            e = soutai.EXPECTED.get((b, flow)) if b else None
            if e is not None:
                horse[x["name"]].append((j, x["agari"] - ma - e, x["kinryo"]))

    # 斤量の係数を**実測**してから引く
    X, Y = [], []
    for rs in horse.values():
        if len(rs) < 3:
            continue
        md = stt.mean(d for _, d, _ in rs)
        mk = stt.mean(k for _, _, k in rs)
        for _, d, k in rs:
            X.append(k - mk)
            Y.append(d - md)
    mx, my = stt.mean(X), stt.mean(Y)
    beta = (sum((a - mx) * (b - my) for a, b in zip(X, Y))
            / sum((a - mx) ** 2 for a in X))

    within: dict = defaultdict(list)
    for rs in horse.values():
        if len({j for j, _, _ in rs}) < 2 or len(rs) < 3:      # 乗り替わりのある馬だけ
            continue
        md = stt.mean(d for _, d, _ in rs)
        mk = stt.mean(k for _, _, k in rs)
        for j, d, k in rs:
            within[j].append((d - md) - beta * (k - mk))
    return ({j: round(stt.mean(v), 4) for j, v in within.items()
             if len(v) >= MIN_RIDES}, round(beta, 4))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--place", default="大井")
    ap.add_argument("--from", dest="lo", required=True)
    ap.add_argument("--to", dest="hi", required=True)
    ap.add_argument("--score-until", default=None,
                    help="この日より前のデータだけで騎手の点数を作る（既定 = --from）")
    args = ap.parse_args()

    until = args.score_until or args.lo
    J, beta = jockey_scores(until)
    print(f"■ 騎手の点数：{until} より前のデータだけで作成。"
          f"{len(J)}人（{MIN_RIDES}騎乗以上）／斤量係数 {beta:+.4f}秒/kg")
    top = sorted(J.items(), key=lambda t: t[1])
    print("   上手い側:", "、".join(f"{k}{v:+.3f}" for k, v in top[:5]))
    print("   下手な側:", "、".join(f"{k}{v:+.3f}" for k, v in top[-5:]), "\n")

    cli = rk.KeibaRakuten()
    rows = []
    d = _date.fromisoformat(args.lo)
    while d <= _date.fromisoformat(args.hi):
        ymd = d.isoformat().replace("-", "")
        d += timedelta(days=1)
        try:
            base = cli.find_race_id(ymd, args.place, 1)[:-2]
        except Exception:                                   # noqa: BLE001
            continue
        for rno in range(1, 13):
            rid = f"{base}{rno:02d}"
            try:
                raw = cli.get(f"/race_performance/list/RACEID/{rid}")
                res = rk.parse_result(raw)
                card = rk.parse_card(cli.get(f"/race_card/list/RACEID/{rid}"))
            except Exception:                               # noqa: BLE001
                continue
            if not res or not card["entries"]:
                continue
            pay = rk.parse_place_payout(raw)
            hist = {e["name"]: (e.get("history") or []) for e in card["entries"]}
            for r in res:
                now = J.get(norm(r.get("jockey")))
                past = [J[j] for h in hist.get(r["name"], [])[:LOOKBACK]
                        if (j := norm(h.jockey)) in J]
                if now is None or len(past) < 2:
                    continue
                pm = stt.mean(past)
                rows.append(dict(
                    name=r["name"], finish=r["finish"], pop=r.get("popularity"),
                    pay=pay.get(r["umaban"], 0), now=now, past=pm,
                    delta=round(now - pm, 4)))

    def rep(lab, sel):
        n = len(sel)
        if not n:
            print(f"  {lab:<36} n=0")
            return
        hit = sum(1 for x in sel if x["finish"] <= 3)
        tot = sum(x["pay"] for x in sel)
        top_ = max((x["pay"] for x in sel), default=0)
        print(f"  {lab:<36} n={n:>4}  3着内 {hit:>3} ({hit/n*100:>5.1f}%)"
              f"  複勝回収 {tot/(100*n)*100:>6.1f}%"
              f"  最高配当抜き {(tot-top_)/(100*max(n-1,1))*100:>6.1f}%")

    print(f"■ {args.place} {args.lo}〜{args.hi}　"
          f"今回と過去2走以上の騎手の点数が取れた {len(rows)}頭\n")
    rep("この群の全体", rows)
    print()
    for key, title in (("past", "**過去3走の騎手**が下手だったか"),
                       ("delta", "**乗り替わり幅**（今回 − 過去平均）")):
        print(f"── {title} ──────────────────────")
        q = sorted(x[key] for x in rows)
        cuts = [q[int(len(q) * f)] for f in (0.2, 0.4, 0.6, 0.8)]
        labs = (["過去が上手い(上位20%)", "やや上手い", "ふつう",
                 "やや下手", "★過去が下手(下位20%)"] if key == "past" else
                ["★上手い方へ替わった(上位20%)", "やや上へ", "ほぼ同じ",
                 "やや下へ", "下手な方へ替わった(下位20%)"])
        for i, lb in enumerate(labs):
            lo_ = cuts[i - 1] if i else -9
            hi_ = cuts[i] if i < 4 else 9
            rep(lb, [x for x in rows
                     if (lo_ <= x[key] < hi_) or (i == 4 and x[key] >= hi_)])
        print()
    print("── 人気薄（7番人気以下）で組み合わせる ──────────────")
    u = [x for x in rows if (x["pop"] or 99) >= UNPOP]
    rep("人気薄・全体", u)
    pc = sorted(x["past"] for x in rows)[int(len(rows) * 0.6)]
    dc = sorted(x["delta"] for x in rows)[int(len(rows) * 0.4)]
    rep("★ 人気薄 × 過去が下手（下40%）", [x for x in u if x["past"] >= pc])
    rep("★ 人気薄 × 上手い方へ替わり（上40%）", [x for x in u if x["delta"] <= dc])
    rep("★ 人気薄 × 両方", [x for x in u if x["past"] >= pc and x["delta"] <= dc])


if __name__ == "__main__":
    main()
