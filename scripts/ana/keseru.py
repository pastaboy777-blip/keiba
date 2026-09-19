#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""【消せない馬を数える】── 1着を当てにいかない。候補を絞るだけの道具。

なぜ印を出さないのか（2026-09-14〜16の実測）:
    3日間・12鞍に印を打った結果が ◎ 1着0回 / ▲ 1着3回・3着内6/7 だった。
    順位付けは当たっていないが、**候補の抽出は当たっている**。
    だから「この馬が勝つ」ではなく「**この馬は消せない**」を数える形にする。
    WIN5のように点数を絞る買い方とは、こちらのほうが相性がいい。

★貫く原則：条件は【そのレースの中で希少】でなければ信号にならない
    最初 B を「同距離帯に勝ち鞍がある」で書いたら 12頭中11頭に立った。
    A を「当条件で3着内がある」で書いたら 1200m戦で 16頭中14頭に立った。
    クラス戦の出走馬は、その条件で走れるから今のクラスにいる。当たり前のことを
    数えても絞れない。**絶対値の条件は全部、レース内で相対化する。**
    （2026-09-15 に効いたのも「18頭中14頭が8月以降＝間隔が希少」という形だった）

消せない理由（1つでもあれば残す）:
    A 当条件      同じ場・同じ距離・同じ馬場種別の好走率が**その鞍の上位1/3**（2走以上）
    B 同距離帯     同じ距離帯・同じ馬場種別（全場）の好走率が**その鞍の上位1/3**（3走以上）
    C 間隔        そのレースで間隔が長いほう2頭
    D 履歴なし     履歴が引けない・行が壊れた
                  ※2026-09-14/15/16 と3日連続で、ここを切って勝たれている
    E 前走1着      直前の1走が1着（「3着内」では希少でないので勝ちに限る）
    F 重い         馬体重がレース平均+15kg以上（発表後のみ）
    G 格          その鞍の条件より**上の格**で3着内がある（中央のみ）

    ★Gが無いと中央では害になる。好走率だけの条件は、G1を使われている馬の
      好走率を低く見積もる。2026-09-20 オールカマーで、有馬記念・エリザベス
      女王杯・前年オールカマーの勝ち馬レガレイラを「消す」側に置いた。

    ★重みは置かない。理由の「数」も順位にしない。**ゼロの馬だけを消す。**
    ★絞れない鞍は絞れないと出す。無理に削らない。

使い方:
    # 中央（rid 12桁）
    python3 scripts/ana/keseru.py --rids 202604050609 202604010610 202604050610 \\
                                          202604010611 202604050611 --base 2026-09-20
    # 地方（rid 16桁）も同じ関数で読める
    python3 scripts/ana/keseru.py --date 20260917 --place 大井 --races 10-12
"""
from __future__ import annotations

import argparse
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kb

STAR_N = 2          # 間隔が長いほうから何頭に★を立てるか
HEAVY = 15          # レース平均から何kg重ければ F を立てるか


def leg(rid: str, base, place_hint: str | None = None, force: bool = False):
    """1鞍ぶん。rid は中央12桁／地方16桁のどちらでもよい。"""
    m, runners = kb.syutuba(rid, force=force)
    if not runners:
        return m, []
    td, sfc = m["dist"], m["surface"]
    place = place_hint or (kb.text(kb.get(f"/{kb.area(rid)}/syutuba/{rid}",
                                          f"syu_{rid}.html")) and "")
    # 会場名はタイトルから拾う（"2026年9月20日中山09R松戸特別"）
    import re
    mm = re.search(r"日([^\d]{2,4})\d+R", m["title"])
    place = mm.group(1) if mm else (place_hint or "")

    rec = []
    for x in runners:
        h = kb.uma(x["umacd"]) if x["umacd"] else []
        last = kb.last_run(h, base)
        na, wa, ta = kb.at(h, place, td, base, surface=sfc)          # A 当条件
        nz, wz, tz = kb.at_zone(h, td, base, surface=sfc)            # B 同距離帯・全場（あとで相対化）
        rec.append(dict(x=x, h=h, gap=kb.interval(h, base), last=last,
                        cond=(na, wa, ta), zone=(nz, wz, tz),
                        bg=kb.best_grade(h, base),
                        pd=kb.dist_of(last["dist"]) if last else None,
                        unknown=(not h) or bool(x.get("partial"))))

    g = sorted((r for r in rec if r["gap"]), key=lambda r: -r["gap"])
    star = {id(r) for r in g[:STAR_N]}
    ws = [int(r["x"]["w"]) for r in rec
          if (r["x"]["w"] or "").isdigit() and int(r["x"]["w"]) > 100]
    avg = st.mean(ws) if ws else None

    # A も B も「その鞍の中で上位1/3の好走率」に相対化する
    cut_n = max(1, len(rec) // 3)

    def top(key, minrun):
        v = [(r, r[key][2] / r[key][0]) for r in rec if r[key][0] >= minrun]
        v.sort(key=lambda t: -t[1])
        return {id(t[0]): t[1] for t in v[:cut_n] if t[1] > 0}

    topa = top("cond", 2)
    topz = top("zone", 3)
    # このレース自身の格（タイトルから拾えないので出馬表の条件欄を使う）
    here = m.get("grade") if kb.area(rid) == "cyuou" else None

    for r in rec:
        why = []
        if id(r) in topa:
            why.append(f"A当条件{topa[id(r)]*100:.0f}%({r['cond'][0]}走)")
        if id(r) in topz:
            why.append(f"B同距離帯{topz[id(r)]*100:.0f}%({r['zone'][0]}走)")
        if id(r) in star:
            why.append(f"C間隔{r['gap']}日")
        if r["unknown"]:
            why.append("D履歴なし")
        if r["last"] and r["last"]["chaku"] == "1":
            why.append("E前走1着")
        if r["bg"] and (here is None or r["bg"][0] >= here):
            why.append(f"G{kb.GRADE[r['bg'][0]]}{r['bg'][1]}着"
                       f"({r['bg'][2][2:7].replace('/','.')})")
        w = r["x"]["w"]
        if avg and (w or "").isdigit() and int(w) - avg >= HEAVY:
            why.append(f"F{int(w)-avg:+.0f}kg")
        r["why"] = why
        r["avg"] = avg
    return m, rec


def show(rid, m, rec, tag=""):
    keep = [r for r in rec if r["why"]]
    cut = [r for r in rec if not r["why"]]
    print("=" * 96)
    print(f"■ {tag}{m['title'].split('|')[1].strip() if '|' in m['title'] else m['title']}"
          f"   {m['surface']}{m['dist']}m {m['course']}  発走{m['start']}  馬場{m['baba']}"
          f"  {len(rec)}頭")
    if not any(r["x"]["w"] for r in rec):
        print("  ※馬体重が未発表。発走30〜50分前に --force で取り直すこと（Fが立てられない）")
    note = "" if len(cut) >= max(2, len(rec) // 4) else "   ★この鞍は絞れていない"
    print(f"  ▸ 消せない {len(keep)}頭 / 消せる {len(cut)}頭{note}")
    print()
    print(f"  {'番':>3} {'馬名':<17}{'騎手':<8}{'単勝':>7}{'体重':>6}{'差':>7}  消せない理由")
    for r in sorted(keep, key=lambda z: kb.fnum(z["x"]["odds"]) or 999):
        x = r["x"]
        d = (f"{int(x['w'])-r['avg']:+.0f}kg"
             if r["avg"] and (x["w"] or "").isdigit() else "—")
        print(f"  {x['ub']:>3} {x['name']:<17}{(x['jk'] or ''):<8}{(x['odds'] or '-'):>7}"
              f"{(x['w'] or '-'):>6}{d:>7}  " + " / ".join(r["why"]))
    if cut:
        print(f"\n  ── 理由ゼロ（消す） ──")
        for r in sorted(cut, key=lambda z: kb.fnum(z["x"]["odds"]) or 999):
            x = r["x"]
            print(f"  {x['ub']:>3} {x['name']:<17}{(x['jk'] or ''):<8}{(x['odds'] or '-'):>7}")
    print()


def main():
    ap = argparse.ArgumentParser(description="消せない馬を数える（順位は付けない）")
    ap.add_argument("--rids", nargs="*", default=[])
    ap.add_argument("--date", help="地方のとき YYYYMMDD")
    ap.add_argument("--place", default="大井")
    ap.add_argument("--races", help="地方のとき 10-12 のように")
    ap.add_argument("--base", required=True, help="基準日 YYYY-MM-DD（当日）")
    ap.add_argument("--force", action="store_true", help="出馬表を取り直す（馬体重）")
    a = ap.parse_args()

    base = kb.to_date(a.base.replace("-", "/"))
    rids = list(a.rids)
    if a.date and a.races:
        pre = kb.prefix(a.date, a.place)
        lo, _, hi = a.races.partition("-")
        rids += [kb.rid_of(pre, r, a.date) for r in range(int(lo), int(hi or lo) + 1)]

    for i, rid in enumerate(rids, 1):
        m, rec = leg(rid, base, force=a.force)
        if not rec:
            print(f"× 出馬表が取れません（{rid}）")
            continue
        show(rid, m, rec, tag=f"脚{i}  " if len(rids) == 5 else "")

    print("※ 理由の数は順位ではありません。**ゼロの馬だけを消す**ための表です。")
    print("  順位付けは3日間の実測で当たっていません（◎1着0回／▲1着3回）。")


if __name__ == "__main__":
    main()
