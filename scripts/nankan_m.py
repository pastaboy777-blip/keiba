#!/usr/bin/env python3
"""Mの法則の3次元で出馬表を見る。

    python3 scripts/nankan_m.py --date 20260814 --place 大井
    python3 scripts/nankan_m.py --date 20260814 --place 大井 --result

    時間軸  鮮度（ショックの合計） − 硬直（前走の反動）
    横軸    異端性（メンバーの中で浮いているか）＋ ペース圧力
    中心点  M3タイプ S／C／L の推定

**買う材料と消す材料を両方持つ**のが要点。こちらが自力で作った点火指数
（`shigeki.py`）には消す側が無かった。

⚠️ 今井雅宏氏の理論そのものではない。公開情報からの独自解釈（`core/mhousoku.py`）。
⚠️ 未検証。重みは初期値。
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import mhousoku as M                  # noqa: E402
from nankeiba.scraping import rakuten as rk              # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--place", required=True)
    ap.add_argument("--race", type=int)
    ap.add_argument("--result", action="store_true")
    ap.add_argument("--all", action="store_true", help="材料の無い馬も出す")
    args = ap.parse_args()

    cli = rk.KeibaRakuten()
    base = cli.find_race_id(args.date, args.place, 1)[:-2]
    d = f"{args.date[:4]}-{args.date[4:6]}-{args.date[6:]}"

    print(f"\n=== {args.date} {args.place}　Mの法則（3次元）===")
    print("  時間軸=鮮度−硬直＋リズム ／ 横軸=異端性・疲労 ／ 中心点=M3")
    print("  ★=定義のある型（短縮ショッカー／延長ライダー／逃げられなかった逃げ馬 ほか）\n")
    for rno in ([args.race] if args.race else range(1, 13)):
        rid = f"{base}{rno:02d}"
        try:
            card = rk.fetch_card(cli, rid)
        except Exception:                                # noqa: BLE001
            continue
        hd = card["header"]
        if not hd.get("distance"):
            continue
        fin = {}
        if args.result:
            try:
                for x in rk.fetch_result(cli, rid):
                    fin[x["name"]] = (x.get("finish"), x.get("popularity"))
            except Exception:                            # noqa: BLE001
                pass
        hist = {e["name"]: [r for r in (e.get("history") or [])
                            if r.date and r.date < d] for e in card["entries"]}
        fs = M.field_stress(hist, d, hd["place"], hd["distance"])
        n = len(card["entries"])
        rows = []
        for e in card["entries"]:
            h = hist[e["name"]]
            st = M.state(hd["place"], hd["distance"], e.get("jockey"),
                         e.get("umaban"), n, hd.get("race_class"), d, h,
                         kinryo=e.get("kinryo"))
            t3 = M.m3(h)
            f_ = fs[e["name"]]
            named = []
            tag, got, miss = M.tanshuku_shocker(hd["distance"], "ダ", d, h)
            if tag:
                named.append((3.0, tag))
            ok, g2, m2 = M.enchou_rider(hd["distance"], d, h)
            if ok:
                named.append((3.0, "延長ライダー"))
            sd, sdnote = M.same_distance_shock(hd["distance"], h)
            if sd:
                named.append((1.5, f"{sd}（{sdnote}）"))
            ni, ninote = M.nigerarenakatta(h, f_.pressure)
            if ni:
                named.append((2.5, ninote))
            up, upnote = M.atypical_upgrade(h, hd.get("race_class"))
            if up:
                named.append((2.0, upnote))
            stv, sttags = M.stress(h)
            bonus = sum(w for w, _ in named)
            rows.append((st.score + f_.ihen + bonus - stv, st, f_, t3, e,
                         [x for _, x in named], sttags, stv,
                         M.rhythm(h, d)))
        rows.sort(key=lambda t: -t[0])
        head = rows[0][2]
        print(f"■ {rno}R ダ{hd['distance']}m {hd.get('race_class') or ''}"
              f"　先行型{head.pressure}頭")
        for tot, st, f, t3, e, named, sttags, stv, rhy in rows:
            if not args.all and abs(tot) < 1.5 and not st.risks:
                continue
            fi, pop = fin.get(e["name"], (None, None))
            res = f"{fi:>2}着{pop or '?'}人気 " if fi else ""
            mark = "◎" if (fi and fi <= 3) else ("×" if fi else " ")
            od = f"{e['odds']}倍" if e.get("odds") else ""
            print(f" {mark}{tot:>+5.1f} [{t3.label():>6}] "
                  f"{e['umaban']:>2} {e['name'][:13]:<14}{od:>8} {res}"
                  f"{st.label()}")
            det = []
            for x in named:
                det.append(f"★ {x}")
            if st.shocks:
                det.append("ショック: " + " / ".join(st.shocks))
            if rhy[0] not in ("―", "一定"):
                det.append(f"リズム: {rhy[1]}")
            if sttags:
                det.append(f"ストレス{stv:.1f}: " + " / ".join(sttags))
            if f.tags:
                det.append("異端: " + " / ".join(f.tags))
            if f.note():
                det.append(f.note())
            if st.risks:
                det.append("**硬直**: " + " / ".join(st.risks))
            for x in det:
                print(f"        {x}")
        print()
    print("  ⚠️ 未検証。本家の理論そのものではない（公開情報からの独自解釈）。")


if __name__ == "__main__":
    main()
