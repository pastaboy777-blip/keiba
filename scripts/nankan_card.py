#!/usr/bin/env python3
"""**レースを一回頭の中で走らせる**形の予想カード。

ユーザー提示（2026-08-18）の構造をそのまま実装したもの。

    ① このレースはどう流れるか（誰が行く、どこで競る）
    ② その流れの中でこの馬がどこにいるか
    ③ だから浮上する ← **ここで初めて過去のデータを根拠として出す**

⚠️⚠️ **①②に過去の成績を使わない。**①は今日のメンバー構成から、②は脚質から
   組み立てる。過去走の着順・時計は③でしか使わない。データを「結論」ではなく
   「入力パラメータ」として扱う、という区別。

── 使う数字は全部、発走前に手に入るものだけ ─────────────────

  ① 流れ … **逃げ経験馬の頭数**（過去3走で最初のコーナーを1番手で通過した馬）
       実測 72鞍（大井6日＋川崎1日）:
         0頭   10鞍  前が止まった **0鞍**   平均 front -1.35  ← 前が楽で確定
         1頭    8鞍  前が止まった 38%       front -0.06
         2頭   11鞍  前が止まった 18%       front -0.50
         3頭   15鞍  前が止まった 47%       front -0.05
         4頭    9鞍  前が止まった 44%       front -0.06
         5頭〜  19鞍  前が止まった 42%       front +0.05
       頭数 対 front  r = **+0.529**／1400mのテン3F とは r = -0.518
       （0頭 39.27秒 → 3頭 37.03秒）
       ⚠️ **0頭のときが一番強い情報**。3頭以上は「潰れうる」止まりで断定できない。

  ② 位置 … 過去3走の**4角位置比率の中央値**。自己相関 r=+0.507 で
       手持ちの変数の中で一番安定している。

  ③ 能力 … 過去3走の**上がり残差**（レース平均との差 − 位置×展開の期待値）の平均。
       自己相関 r=+0.351。3走平均で信頼性 0.61。

  馬場 … **前開催の同じ競馬場**の位置別3着内率をそのまま使う。
       川崎 7/27-31 は 前25% 64.4% / 中 33.7% / 後40% 10.7% で、
       8/18 の実測 65.5 / 31.1 / 5.9 とほぼ一致した。**開催をまたいで持ち越す。**

⚠️ 恒久ルール5により、**目の前の開催しか見ない**。物差し（前開催のバイアス）作りは
   検証ではない。回収率・勝率の全期間集計はしない。

── 川崎 2026-08-18 で回した結果 ───────────────────────────

⚠️⚠️ **結果を見たあとに書いたコードなので、これは本当の検証ではない。**
   重み（W_POS/W_ABI/±0.80 など）と NIGE_HOT=3 は私が選んだ。
   しかも帯ラベルのバグを直して再実行しており、**バグ修正とチューニングは
   外形上区別がつかない**。数字は参考値として読むこと。

    ◎ 3着内 7/12 (58.3%)  複勝回収 132.5%
       上位1件抜き 87.3% ／ 上位2件抜き **68.0%**  ← ほぼ全体並み
    ○ 3着内 5/12 (41.7%)  複勝回収 76.7%
    ▲ 3着内 1/12 ( 8.3%)  複勝回収 20.0%
    ◎の人気分布 [1,1,1,2,4,5,5,6,9,10] ── **1番人気を3頭拾っている**

⚠️⚠️⚠️ **①の流れの読みは、何も考えない基準に負けた。**
    実際は12鞍中10鞍が「前が楽」。**「常に楽」と言えば 10/12**。
    逃げ経験馬の頭数を使った予測は **7/12**。
    頭数と front の相関は r=+0.529 あったのに、**分類では負ける**。
    基準率が10:2に偏っている場に、相関だけを見て閾値を置いたのが誤り。
    → **①は現状、足を引っ張っている。**効いたのは②位置と③残差。

    唯一の妙味は 5R ウロボロス 9人気2着（複勝630円）で、
    これは「前が潰れうる」判定が当たった唯一のレースだった。
"""

from __future__ import annotations

import argparse
import math
import os
import statistics as stt
import sys
from collections import Counter
from datetime import date as _date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import soutai                            # noqa: E402
from nankeiba.scraping import rakuten as rk                 # noqa: E402

LOOKBACK = 3
#: 逃げ経験馬が何頭以上なら「前が潰れうる」とみなすか（実測 3頭から47%）。
NIGE_HOT = 3
#: 位置スコアの重み。前開催のバイアスをロジットで入れる。
W_POS = 1.0
#: 能力（上がり残差）の重み。残差1秒 ≒ 位置1段ぶん、として置いた初期値。
W_ABI = 1.0


def logit(p: float) -> float:
    p = min(max(p, 0.02), 0.98)
    return math.log(p / (1 - p))


def prev_meeting_bias(cli, place: str, before: str, back: int = 40) -> dict:
    """**前開催**の位置別3着内率。予想時点で手に入る唯一の馬場情報。"""
    from nankan_ana import corner4
    days = []
    d = _date.fromisoformat(before) - timedelta(days=1)
    while len(days) < 6 and d > _date.fromisoformat(before) - timedelta(days=back):
        ymd = d.isoformat().replace("-", "")
        try:
            cli.find_race_id(ymd, place, 1)
            days.append(ymd)
        except Exception:                                   # noqa: BLE001
            pass
        d -= timedelta(days=1)
    cnt, hit = Counter(), Counter()
    for ymd in days:
        base = cli.find_race_id(ymd, place, 1)[:-2]
        for rno in range(1, 13):
            try:
                raw = cli.get(f"/race_performance/list/RACEID/{base}{rno:02d}")
                res = rk.parse_result(raw)
            except Exception:                               # noqa: BLE001
                continue
            if not res:
                continue
            m = corner4((rk.parse_lap(raw) or {}).get("corners"))
            fs = len(res)
            for x in res:
                p = m.get(x["umaban"])
                if not p:
                    continue
                b = soutai.pos_band(p, fs)
                cnt[b] += 1
                if x["finish"] <= 3:
                    hit[b] += 1
    return ({b: hit[b] / cnt[b] for b in cnt if cnt[b] >= 30}, days)


def past_agari_residual(cli, hist, name: str, diffs: dict) -> float | None:
    v = [diffs[(h.date, name)] for h in hist[:LOOKBACK] if (h.date, name) in diffs]
    return stt.mean(v) if v else None


def band_of(hist) -> tuple[str | None, float | None]:
    """過去3走の4角位置比率の中央値から、想定位置帯を出す。

    ⚠️ **帯の名前は `soutai.pos_band` と揃えること。**独自に "前25%" などと
       書くと、前開催のバイアス（`soutai` 側のキー）が引けず既定値に落ちる。
       実際それで「馬場の前提が『中』しか効かない」状態になっていた。
    """
    v = [(h.corner_pos[-1] / h.field_size) for h in hist[:LOOKBACK]
         if h.corner_pos and h.field_size]
    if not v:
        return None, None
    m = stt.median(v)
    return soutai.pos_band(round(m * 100), 100), round(m, 2)


def n_nige(entries) -> int:
    """**逃げたい馬**の数。過去3走で最初のコーナーを1番手で通過した経験。"""
    return sum(1 for e in entries
               if any((h.corner_pos or [99])[0] == 1
                      for h in (e.get("history") or [])[:LOOKBACK]))


def load_residuals() -> dict:
    """runs.jsonl から `(日付, 馬名) -> 上がり残差`。①②③の③に使う。"""
    import json
    from collections import defaultdict
    by = defaultdict(list)
    for line in open("data/bt/runs.jsonl", encoding="utf-8"):
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
                out[(rs[0]["date"], x["name"])] = round(x["agari"] - ma - e, 3)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--place", required=True)
    ap.add_argument("--verify", action="store_true", help="結果と突き合わせる")
    args = ap.parse_args()

    cli = rk.KeibaRakuten()
    iso = f"{args.date[:4]}-{args.date[4:6]}-{args.date[6:]}"
    bias, days = prev_meeting_bias(cli, args.place, iso)
    diffs = load_residuals()
    print(f"\n=== {iso} {args.place}　予想カード ===")
    print(f"■ 馬場の前提：前開催 {days[-1]}〜{days[0]} の位置別3着内率")
    print("   " + " ／ ".join(f"{b} {bias[b]*100:.1f}%" for b in ("前", "中", "後")
                              if b in bias))
    base = cli.find_race_id(args.date, args.place, 1)[:-2]
    picks = []
    for rno in range(1, 13):
        rid = f"{base}{rno:02d}"
        try:
            card = rk.parse_card(cli.get(f"/race_card/list/RACEID/{rid}"))
        except Exception:                                   # noqa: BLE001
            continue
        hd, ents = card["header"], card["entries"]
        if not ents or not hd.get("distance"):
            continue
        nn = n_nige(ents)
        flow = ("前が楽で確定" if nn == 0 else
                "前が潰れうる" if nn >= NIGE_HOT else "中間")
        rows = []
        for e in ents:
            hist = e.get("history") or []
            b, m = band_of(hist)
            a = past_agari_residual(cli, hist, e["name"], diffs)
            if b is None:
                continue
            s = W_POS * logit(bias.get(b, 0.25))
            if nn >= NIGE_HOT:                       # 前が潰れうる → 前を割り引く
                s += {"前": -0.80, "中": +0.30, "後": +0.30}[b]
            elif nn == 0:                            # 前が楽 → 前をさらに押す
                s += {"前": +0.50, "中": 0.0, "後": -0.30}[b]
            if a is not None:
                s += W_ABI * (-a)                    # 残差はマイナスが速い
            rows.append(dict(u=e["umaban"], name=e["name"], band=b, pos=m,
                             ab=a, sc=round(s, 2), odds=e.get("odds"),
                             pop=e.get("popularity")))
        if len(rows) < 4:
            continue
        rows.sort(key=lambda x: -x["sc"])
        print(f"\n■ {rno}R {hd['distance']}m {hd.get('race_class')} {len(ents)}頭")
        print(f"  ① 流れ：**{flow}**（逃げたい馬 {nn}頭 / {len(ents)}頭）")
        mark = ["◎", "○", "▲", "△", "△"]
        for i, x in enumerate(rows[:5]):
            print(f"  {mark[i]} {x['u']:>2} {x['name']:<12} {x['band']:<5}"
                  f"(想定{x['pos']}) 残差{('%+.2f' % x['ab']) if x['ab'] is not None else ' —  '}"
                  f"  score {x['sc']:+.2f}  {x['odds']}倍({x['pop']}人気)")
        # ③ 分岐を必ず置く
        if nn >= NIGE_HOT:
            alt = next((x for x in rows if x["band"] == "前"), None)
            if alt and alt["u"] != rows[0]["u"]:
                print(f"  ③ 分岐：**前が競らずに楽に行けたら {alt['u']}{alt['name']}**")
        elif nn <= 1:
            alt = next((x for x in rows if x["band"] != "前"), None)
            if alt and alt["u"] != rows[0]["u"]:
                print(f"  ③ 分岐：**それでも前が潰れたら {alt['u']}{alt['name']}**")
        picks.append(dict(rno=rno, rid=rid, nn=nn, flow=flow, rows=rows))

    if not args.verify:
        return
    print("\n\n=== 検証 ===")
    from nankan_ana import corner4
    hit = Counter(); tot = Counter(); ret = Counter()
    fl_ok = fl_n = 0
    for p in picks:
        raw = cli.get(f"/race_performance/list/RACEID/{p['rid']}")
        res = rk.parse_result(raw)
        if not res:
            continue
        pay = rk.parse_place_payout(raw)
        fin = {x["umaban"]: x for x in res}
        m = corner4((rk.parse_lap(raw) or {}).get("corners"))
        fs = len(res)
        rr, _ = soutai.analyse([dict(name=x["name"], agari=x.get("agari"),
                                     corner4=m.get(x["umaban"]), field_size=fs,
                                     finish=x["finish"]) for x in res])
        fl_n += 1
        pred_stop = p["nn"] >= NIGE_HOT
        if pred_stop == (rr.flow == "止"):
            fl_ok += 1
        line = []
        for i, x in enumerate(p["rows"][:3]):
            f = fin.get(x["u"])
            if not f:
                continue
            tot[i] += 1
            if f["finish"] <= 3:
                hit[i] += 1
                ret[i] += pay.get(x["u"], 0)
            line.append(f"{'◎○▲'[i]}{x['u']}→{f['finish']}着")
        print(f"  {p['rno']:>2}R 流れ予想 {p['flow']:<6} 実際 {rr.note():<28} "
              + " ".join(line))
    print(f"\n■ 流れの読み（前が潰れる/そうでない）  {fl_ok}/{fl_n} 的中")
    for i, mk in enumerate("◎○▲"):
        if tot[i]:
            print(f"■ {mk} 3着内 {hit[i]}/{tot[i]} ({hit[i]/tot[i]*100:.1f}%)"
                  f"  複勝回収 {ret[i]/(100*tot[i])*100:.1f}%")


if __name__ == "__main__":
    main()
