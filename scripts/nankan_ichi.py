#!/usr/bin/env python3
"""「濃い脚 × 着外」に、**位置が上がる材料**を掛け合わせて測る。

`nankan_heikinsa.py` で、「過去3走に 上がりのレース平均差 -1.0以下 かつ 着外
の走りがある馬」は**棄却された**（3着内 19.7% / 複勝回収 58.3%、全体は 26.0% /
68.1%）。一方で、同じ群を**今回の4角位置が上がったかどうか**で割ると方向が出た。

    位置が大きく上がった  3着内 38.1% ／ 位置が下がった 17.6%

しかし「今回の位置」は**レース後にしか分からない**。そこでこの道具は、
**事前に分かる材料**で「位置が上がりそうか」を代理する。

    延長      … 今回距離 > 前走距離
    内枠替わり … 今回の枠位置が前走より内   （ジューンアカデミー 8枠→2枠）
    先行手薄  … メンバーの先行型が少ない    （`mhousoku.field_stress` の pressure）

さらに、**「濃い脚 × 着外」群を、その走りの道中の位置変動で割る**。

    ⚠️⚠️ **「濃い脚で着外」には2種類が混ざっている。**
       (a) 追走で苦しんで**後退**し、前が止まったから届いただけ ← 余力ではない
       (b) 楽に追走して**最後に伸びた**                      ← これが余力
       平均差も残差も、この2つを区別しない。区別するのは**道中で位置を下げたか**。
       力まずに追走できていれば位置は下がらない、という読み（ユーザー提示・
       「ウィリーしながら脚を溜める」＝腰仙関節で後肢を入れて前肢荷重を抜く形）。
       **前走の通過順から事前に分かる。**

⚠️ **対照群を必ず取ること。**材料だけで効くなら「濃い脚×着外」は要らない。
   材料 単体の群と、掛け合わせた群を並べて出す。

    python3 scripts/nankan_ichi.py --place 大井 --from 2026-08-12 --to 2026-08-16

⚠️ 恒久ルール5により、**目の前の開催しか見ない**。

── 実測（大井 2026-08-12〜08-16・548頭）────────────────────────

⚠️⚠️ **材料を掛けても救えなかった。位置変動でも割れなかった。両方残す。**

    全体                          3着内 24.8%  複勝回収 65.9%
    ★ 濃い脚 × 着外               3着内 18.4%  複勝回収 53.8%
      × 延長        n=22          3着内 13.6%  複勝回収 16.4%   ← 一番悪い
      × 内枠替わり   n=30          3着内 26.7%  複勝回収 54.7%
      × 先行手薄     n=18          3着内 22.2%  複勝回収 41.7%
      × 材料2つ以上  n=17          3着内 29.4%  複勝回収 44.1%
    どれも全体の複勝回収 65.9% を超えない。

  **位置変動での分割も失敗**:
      位置を下げていない n=62（群の82%）3着内 19.4%  ← 分散が無い
      下げた             n= 5

    ⚠️ **通過順は順位。**「楽に追走できたか」ではなく「**他が垂れたか**」を
       測っている。濃い脚を使う馬はほぼ全員 move ≤ 0 になる。
       「力まずに追走できていれば位置は下がらない」という読みは、
       このデータでは**確かめられない**（分散が無いので割れない）。

── 副産物：騎手効果は、馬を固定しないと測れない ──────────────────

    上がり残差（位置×展開を補正）の騎手間ばらつき（標準偏差）
        馬を固定しない            0.183秒
        馬を固定する              0.089秒   ← **半分は馬の質だった**
        さらに斤量も引く           0.088秒   ← 減量では説明されない

    斤量の実測：上がり残差に対して **+0.0196秒/kg**。通説「1kg=0.2秒」の1/10。
    （BT値で測った SEC_PER_KG_1000M=0.0227 と整合）

    例）中山遥  生 56/106位(+0.055) → 馬を固定 18/105位(-0.075)
        減量騎手は弱い馬に乗るので、**生の騎手成績は下振れする**。
    ⚠️ ただし -0.05〜-0.08秒は小さい。1走の残差 -1.39 の4%程度しか説明しない。
"""

from __future__ import annotations

import argparse
import json
import os
import statistics as stt
import sys
from collections import defaultdict
from datetime import date as _date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import mhousoku as M                     # noqa: E402
from nankeiba.scraping import rakuten as rk                 # noqa: E402

RUNS = "data/bt/runs.jsonl"
#: 「濃い脚」とみなすレース平均差[秒]。
KOI = -1.0
#: 着外とみなす着順。
KENGAI = 4
#: 過去何走を見るか。
LOOKBACK = 3
#: 枠位置が「内に替わった」とみなす正規化差。ノイズを踏まないよう幅を持たせる。
INNER = 0.10
#: 「先行手薄」とみなす、先行型の頭数比。
THIN = 0.20
#: 道中で「下げた」とみなす正規化位置変動。頭数で割るので 0.10 = 14頭なら1.4番手。
DROP = 0.10
UNPOP = 7


def load_diffs() -> dict:
    """runs.jsonl から `(date,place,distance,馬名) -> (平均差, 着順)`。"""
    by: dict = defaultdict(list)
    for line in open(RUNS, encoding="utf-8"):
        r = json.loads(line)
        by[r["rid"]].append(r)
    out: dict = {}
    for rs in by.values():
        ag = [x["agari"] for x in rs if x.get("agari")]
        if len(ag) < 4:
            continue
        ma = stt.mean(ag)
        h = rs[0]
        for x in rs:
            if x.get("agari"):
                out[(h["date"], h["place"], h["distance"], x["name"])] = (
                    round(x["agari"] - ma, 2), x.get("finish"))
    return out


def collect(cli, place: str, lo: str, hi: str, diffs: dict) -> list:
    """対象開催の全出走馬を、材料つきで1頭1行に落とす。"""
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
                res = rk.parse_result(raw)
                card = rk.parse_card(cli.get(f"/race_card/list/RACEID/{rid}"))
            except Exception:                               # noqa: BLE001
                continue
            if not res or not card["entries"]:
                continue
            hd = card["header"]
            dist = hd.get("distance")
            if not dist:
                continue
            pay = rk.parse_place_payout(raw)
            fs = len(res)
            hist = {e["name"]: (e.get("history") or []) for e in card["entries"]}
            fst = M.field_stress(hist, hd.get("date") or "", place, dist)
            for r in res:
                hs = hist.get(r["name"], [])
                prev = hs[0] if hs else None
                if not prev:
                    continue
                # ⚠️ **None を落としてから zip しないこと。**過去走が引けない走が
                #    あると通過順が別の走にずれる。対応を保ったまま組で持つ。
                pairs = [(diffs.get((h.date, h.place, h.distance, r["name"])), h)
                         for h in hs[:LOOKBACK]]
                ev = [x for x, _ in pairs if x]
                # 条件を満たした走りのうち、**一番濃かったもの**の道中の動きを見る
                koi_runs = [(x[0], x[1], h) for x, h in pairs
                            if x and x[0] <= KOI and x[1] is not None
                            and x[1] >= KENGAI]
                koi = bool(koi_runs)
                move = None
                if koi_runs:
                    src = min(koi_runs, key=lambda t: t[0])[2]
                    cp = src.corner_pos or []
                    if len(cp) >= 2 and src.field_size:
                        move = (cp[-1] - cp[0]) / src.field_size
                # ── 事前に分かる材料 ──
                enchou = bool(prev.distance and prev.distance < dist)
                uchi = None
                if prev.gate and prev.field_size and r.get("umaban"):
                    uchi = (r["umaban"] / fs) < (prev.gate / prev.field_size) - INNER
                st = fst.get(r["name"])
                thin = bool(st and fs and (st.pressure / fs) <= THIN)
                rows.append(dict(
                    name=r["name"], finish=r["finish"], pop=r.get("popularity"),
                    pay=pay.get(r["umaban"], 0), koi=koi, move=move,
                    enchou=enchou, uchi=bool(uchi), thin=thin,
                    nmat=sum([enchou, bool(uchi), thin])))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--place", default="大井")
    ap.add_argument("--from", dest="lo", required=True)
    ap.add_argument("--to", dest="hi", required=True)
    args = ap.parse_args()

    rows = collect(rk.KeibaRakuten(), args.place, args.lo, args.hi, load_diffs())

    def rep(lab, sel):
        n = len(sel)
        if not n:
            print(f"  {lab:<38} n=0")
            return
        hit = sum(1 for x in sel if x["finish"] <= 3)
        top = sorted((x["pay"] for x in sel), reverse=True)[:1]
        ret = sum(x["pay"] for x in sel) / (100 * n) * 100
        ex = ((sum(x["pay"] for x in sel) - sum(top)) / (100 * max(n - 1, 1)) * 100)
        print(f"  {lab:<38} n={n:>4}  3着内 {hit:>3} ({hit/n*100:>5.1f}%)"
              f"  複勝回収 {ret:>6.1f}%  最高配当を1つ抜くと {ex:>6.1f}%")

    print(f"■ {args.place} {args.lo}〜{args.hi}　前走のある出走馬 {len(rows)}頭")
    print("  ※ 複勝回収は**最高配当を1つ抜いた値も併記**する。"
          "1頭で作った数字を見分けるため。\n")
    koi = [x for x in rows if x["koi"]]
    non = [x for x in rows if not x["koi"]]
    rep("全体", rows)
    rep("★ 濃い脚 × 着外（棄却済みの群）", koi)
    print()
    print("── 材料を掛ける ─────────────────────────────────────")
    for lab, key in (("延長", "enchou"), ("内枠替わり", "uchi"), ("先行手薄", "thin")):
        rep(f"★ 濃い脚×着外 × {lab}", [x for x in koi if x[key]])
        rep(f"   （対照）材料だけ・{lab}", [x for x in non if x[key]])
    rep("★ 濃い脚×着外 × 材料1つ以上", [x for x in koi if x["nmat"] >= 1])
    rep("★ 濃い脚×着外 × 材料2つ以上", [x for x in koi if x["nmat"] >= 2])
    rep("   （対照）材料2つ以上だけ", [x for x in non if x["nmat"] >= 2])
    print()
    print("── ★ 濃い脚×着外 を「その走りの道中の動き」で割る ────────────")
    print("   （前走の通過順から**事前に分かる**。今回の位置ではない）")
    kept = [x for x in koi if x["move"] is not None and x["move"] <= 0]
    drop = [x for x in koi if x["move"] is not None and x["move"] > DROP]
    mid = [x for x in koi if x["move"] is not None and 0 < x["move"] <= DROP]
    rep("★ 位置を下げていない（move ≤ 0）", kept)
    rep("   少しだけ下げた", mid)
    rep("   下げた（move > 0.10）", drop)
    rep("   通過順が取れない", [x for x in koi if x["move"] is None])
    print()
    rep("★ 位置を下げていない × 材料1つ以上",
        [x for x in kept if x["nmat"] >= 1])
    rep("★ 位置を下げていない × 7番人気以下",
        [x for x in kept if (x["pop"] or 99) >= UNPOP])
    print()
    print("── 人気薄（7番人気以下）────────────────────────────")
    u = [x for x in rows if (x["pop"] or 99) >= UNPOP]
    rep("全体", u)
    rep("★ 濃い脚×着外", [x for x in u if x["koi"]])
    rep("★ 濃い脚×着外 × 材料1つ以上",
        [x for x in u if x["koi"] and x["nmat"] >= 1])
    rep("★ 濃い脚×着外 × 材料2つ以上",
        [x for x in u if x["koi"] and x["nmat"] >= 2])


if __name__ == "__main__":
    main()
