#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""【雨の日に穴をあける形】── 小型・ブリンカー・高齢・上がりが一定

元ネタは 2026-09-19 にユーザーからもらった記事（中山7R ブレイクザアイス 18.9倍）:
    「雨になると ①小型馬 ②ブリンカー（チーク） ③高齢馬 ④毎回同じ上り
      の馬が穴になることが多いので狙いました」

★このリポジトリの原則に合わせて、**4条件すべてをレース内で相対化している。**
    記事のままだと「462kgだから小型」「7歳だから高齢」という絶対値になる。
    絶対値の条件は、そのレースの出走馬の構成しだいで意味が変わる。
    462kgでも、全馬が450kg台の鞍なら小型ではない。7歳も、7歳が6頭いれば希少でない。
    → 小型・高齢・上がり一定は **その鞍で下位/上位1/3** に入るかで判定する。
    （ブリンカーだけは相対化しない。装着自体がもともと少数だから希少性が自然に立つ）

④「毎回同じ上り」がいちばん筋がいい。理屈はこう:
    道悪になると出走馬全体の上がりが落ちる。そこで**上がりが変わらない馬**は、
    自分が速くなったわけではないのに、相対的に前へ出る。
    ＝「条件はレース内で相対化しないと信号にならない」の、時間方向の言い換え。
    上がり順位（CLAUDE.mdルール7）と違い、**順位ではなく絶対値のばらつき**を見るので、
    差した馬を拾い前で粘った馬を落とす、という偏りが入らない。

★④の落とし穴（必ず一緒に見ること）
    上がり3Fは距離とペースで動く。**毎回同じ距離しか使っていない馬は、
    それだけで上がりが揃う。** ばらつきが小さいのが「脚の質」なのか
    「同じ条件しか使っていないだけ」なのかは区別できない。
    → 走った距離の種類数（dv）と、走った馬場の種類数（bv）を横に出す。
      **bv が 1（良しか走っていない）なら、④は道悪の根拠にならない。**

★馬体重について（CLAUDE.mdルール3）
    中央は発走30〜50分前まで出馬表が空欄。だから**近走の馬体重の中央値**で代用する。
    当日 --force で取り直せば今回の値が入る。そのときは実測を優先すること。

使い方:
    python3 scripts/ana/ame.py --date 20260920 --place 中山          # その日の全鞍
    python3 scripts/ana/ame.py --rids 202604050609 202604050610      # 鞍を指定
    python3 scripts/ana/ame.py --date 20260920 --place 中山 --min 3  # 3条件以上だけ
"""
from __future__ import annotations

import argparse
import re
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kb

N_RUNS = 6          # 近走を何走見るか
MIN_AGARI = 3       # ④を判定するのに必要な上がりの本数


def agari(h):
    """近走の上がり3Fを取る。uma() の pace 欄が 'M 36.9' の形。"""
    out = []
    for r in h[-N_RUNS:]:
        m = re.search(r"([\d]{2}\.[\d])", r.get("pace") or "")
        if m:
            out.append((float(m.group(1)), r.get("dist") or "", r.get("baba") or ""))
    return out


def odds(x):
    """単勝の表示。★keibabookは大穴を『☆』で伏せる。未発表ではない（穴11）。

    各鞍で数字が出ている上限を見ると 43〜48倍どまりで、それ以上が全部☆になる。
    ＝**☆は「50倍以上」。** これを「オッズ未発表」と読むと、
    いちばん人気のない馬＝いちばん穴の馬を、検討から落としてしまう。
    """
    v = x.get("odds")
    return "50倍超" if (v or "").strip() in ("☆", "★") else (v or "-")


def wet_rec(h, base=None):
    """道悪（稍を除く 重・不）の (走数, 勝, 3着内)。★略記の「不」を落とさない（kb.WET）。"""
    rs = [r for r in h if r["baba"] in kb.HEAVY
          and (base is None or kb.to_date(r["date"]) < base)]
    w = sum(1 for r in rs if r["chaku"] == "1")
    t = sum(1 for r in rs if r["chaku"].isdigit() and int(r["chaku"]) <= 3)
    return len(rs), w, t


def leg(rid, base, force=False):
    m, runners = kb.syutuba(rid, force=force)
    if not runners:
        return m, []
    rec = []
    for x in runners:
        h = kb.uma(x["umacd"]) if x["umacd"] else []
        ws = [int(r["w"]) for r in h[-N_RUNS:] if (r["w"] or "").isdigit() and int(r["w"]) > 100]
        # 当日の実測があればそちらを優先する（--force で取れたとき）
        now = int(x["w"]) if (x["w"] or "").isdigit() and int(x["w"]) > 100 else None
        ag = agari(h)
        a = [v for v, _, _ in ag]
        age = int(mm.group(1)) if (mm := re.search(r"(\d+)", x["sex"] or "")) else None
        rec.append(dict(x=x, h=h, age=age,
                        w=now or (st.median(ws) if ws else None), wnow=now, nw=len(ws),
                        ag=a, sd=(st.pstdev(a) if len(a) >= MIN_AGARI else None),
                        dv=len({d for _, d, _ in ag}), bv=len({b for _, _, b in ag}),
                        wet=wet_rec(h, base)))
    n = len(rec)
    cut = max(1, n // 3)

    # ①小型：近走馬体重が軽いほう1/3。
    # ★体重が団子の鞍では立てない（全馬±10kg以内なら「小型」という区別が成立しない）。
    ws = sorted((r for r in rec if r["w"]), key=lambda r: r["w"])
    small = ({id(r) for r in ws[:cut]}
             if len(ws) >= 3 and ws[-1]["w"] - ws[0]["w"] >= 20 else set())
    # ③高齢：年齢が高いほう1/3。
    # ★全馬が同い年の鞍（2歳戦など）では**発火させない**。
    #   2歳未勝利で「高齢2歳」と出た。相対化しても、散らばりがゼロなら希少性は生まれない。
    #   相対化は「順位を付ける」ことであって、「差があること」までは保証しない。
    need = sorted((r["age"] for r in rec if r["age"]), reverse=True)
    thr = need[min(cut - 1, len(need) - 1)] if need else None
    lo_age = min(need) if need else None
    old = ({id(r) for r in rec if r["age"] and thr and r["age"] >= thr > lo_age}
           if need and max(need) > lo_age else set())
    # ④上がりが一定：ばらつきが小さいほう1/3（3本以上ある馬の中で）
    sds = sorted((r for r in rec if r["sd"] is not None), key=lambda r: r["sd"])
    flat = {id(r) for r in sds[:cut]}

    for r in rec:
        hit = []
        if id(r) in small:
            hit.append("小型")
        if r["x"].get("bli"):
            hit.append("ブリンカー")
        if id(r) in old:
            hit.append(f"高齢{r['age']}歳")
        if id(r) in flat:
            hit.append(f"上がり一定±{r['sd']:.2f}")
        r["hit"] = hit
    return m, rec


def show(m, rec, minhit):
    print("=" * 100)
    ttl = m["title"].split("|")[1].strip() if "|" in m["title"] else m["title"]
    print(f"■ {ttl}  {m['surface']}{m['dist']}m {m['course']}  発走{m['start']}  馬場{m['baba']}  {len(rec)}頭")
    if not any(r["wnow"] for r in rec):
        print("  ※馬体重は未発表。近走の中央値で代用している（当日 --force で取り直すこと）")
    hits = [r for r in rec if len(r["hit"]) >= minhit]
    if not hits:
        print(f"  ▸ {minhit}条件以上に当てはまる馬はいません\n")
        return
    print(f"  ▸ {minhit}条件以上 … {len(hits)}頭\n")
    print(f"  {'番':>3} {'馬名':<17}{'単勝':>7}{'体重':>6}{'齢':>4}{'上がり幅':>9}{'距':>3}{'馬場':>4}  当てはまった形")
    for r in sorted(hits, key=lambda z: -len(z["hit"])):
        x = r["x"]
        sd = f"±{r['sd']:.2f}" if r["sd"] is not None else "—"
        print(f"  {x['ub']:>3} {x['name']:<17}{odds(x):>7}"
              f"{(str(r['w']) if r['w'] else '—'):>6}{(str(r['age']) if r['age'] else '—'):>4}"
              f"{sd:>9}{r['dv']:>3}{r['bv']:>4}  " + " / ".join(r["hit"])
              + (f"   道悪{r['wet'][0]}走{r['wet'][1]}勝{r['wet'][2]}好走" if r["wet"][0] else "   道悪未経験"))
        if r["bv"] <= 1:
            print(f"      ※良しか走っていない。**この馬の「上がり一定」は道悪の根拠にならない**")
    print()


def main():
    ap = argparse.ArgumentParser(description="雨の日に穴をあける形を数える")
    ap.add_argument("--rids", nargs="*", default=[])
    ap.add_argument("--date")
    ap.add_argument("--place", default="中山")
    ap.add_argument("--races", default="1-12")
    ap.add_argument("--pre", help="中央の開催コード10桁（例 2026040506＝4回中山6日目）")
    ap.add_argument("--base", default=None, help="基準日 YYYY-MM-DD")
    ap.add_argument("--min", type=int, default=2, help="いくつ当てはまったら出すか")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    base = kb.to_date(a.base.replace("-", "/")) if a.base else None
    rids = list(a.rids)
    lo, _, hi = a.races.partition("-")
    rng = range(int(lo), int(hi or lo) + 1)
    if a.pre and not rids:
        # ★中央は 開催コード10桁＋R2桁＝12桁。地方の rid_of（日付が付く）とは別物。
        rids = [f"{a.pre}{r:02d}" for r in rng]
    elif a.date and not rids:
        pre = kb.prefix(a.date, a.place)
        if not pre:
            print(f"× {a.date} の{a.place}が日程ページに見つかりません。"
                  f"中央なら --pre で開催コード10桁を渡すこと（例 2026040506＝4回中山6日目）")
            return
        rids = [kb.rid_of(pre, r, a.date) for r in rng]

    for rid in rids:
        try:
            m, rec = leg(rid, base, force=a.force)
        except Exception as e:
            print(f"× {rid}: {e}")
            continue
        if not rec:
            print(f"× 出馬表が取れません（{rid}）")
            continue
        show(m, rec, a.min)

    print("※ 4条件はすべて**そのレースの中で**相対化しています（ブリンカーを除く）。")
    print("  「上がり一定」は、走った馬場の種類が1つだけの馬では道悪の根拠になりません。")


if __name__ == "__main__":
    main()
