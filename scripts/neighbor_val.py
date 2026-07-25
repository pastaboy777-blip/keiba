#!/usr/bin/env python3
"""【変態ファクター⑥】隣の馬効果＝ゲートの"ご近所さん"。
自分の枠でなく「隣の枠にどんな脚質の馬がいるか」で道中(＝折り合い)が決まる、という
エルツ理論(折り合い→直線脚)の構造的先読み版。誰も隣の馬を見ていない。

理屈:
 ・差し馬の隣に逃げ馬 → 前が空いて揉まれず折り合える = 買い
 ・逃げ馬の隣に逃げ馬 → ハナ争いで潰し合う = 消し
 ・逃げ馬の周りが差しばかり → 楽にハナ = 買い
内隣(umaban-1)と外隣(umaban+1)は意味が違うので分けて検証する。

使い方: python3 scripts/neighbor_val.py --from 2026-04-01 --to 2026-07-24
"""
import sys, argparse, datetime
sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}"
PERF = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{r}"
TRACKS = ["浦和", "船橋", "大井", "川崎"]


def style(e, n=4):
    """脚質を過去n走のコーナー初期位置の相対値から判定。逃/先/差/追/?"""
    rs = []
    for pr in (e.recent_runs or [])[:n]:
        co = [x for x in (pr.corner or []) if isinstance(x, (int, float))]
        fs = pr.field_size
        if co and fs:
            rs.append(co[0] / fs)
    if not rs:
        return "?"
    a = sum(rs) / len(rs)
    return "逃" if a <= 0.20 else ("先" if a <= 0.45 else ("差" if a <= 0.72 else "追"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", required=True)
    ap.add_argument("--to", dest="to", required=True)
    ap.add_argument("--usui", type=int, default=6)
    a = ap.parse_args()
    c = PoliteClient()
    d0 = datetime.date.fromisoformat(a.frm); d1 = datetime.date.fromisoformat(a.to)
    base = [0, 0]
    # セル: 説明 -> [good, n]
    C = {}
    def add(k, g):
        cc = C.setdefault(k, [0, 0]); cc[0] += g; cc[1] += 1

    day = d0
    while day <= d1:
        ymd = day.strftime("%Y%m%d")
        for tr in TRACKS:
            try:
                idx = c.get(CARD.format(r=day_index_race_id(ymd, tr)), use_cache=True)
                races = dict(P.parse_race_links(idx, date_yyyymmdd=ymd, jyo_code=ALL_CODES[tr]))
            except Exception:
                races = {}
            for R, rid in sorted(races.items()):
                try:
                    pc = P.parse_card_page(c.get(CARD.format(r=rid), use_cache=True), rid)
                    rr = P.parse_result_page(c.get(PERF.format(r=rid), use_cache=True), rid)
                except Exception:
                    continue
                if not rr.rows or not rr.rows[0].finish_pos:
                    continue
                ent = {e.umaban: e for e in pc.entries if e.umaban}
                if len(ent) < 6:
                    continue
                st = {um: style(e) for um, e in ent.items()}
                n_nige = sum(1 for v in st.values() if v == "逃")
                for row in rr.rows:
                    if not (row.umaban and row.finish_pos and row.popularity):
                        continue
                    if row.popularity < a.usui:      # 人気薄のみ
                        continue
                    um = row.umaban
                    me = st.get(um, "?")
                    if me == "?":
                        continue
                    g = 1 if row.finish_pos <= 3 else 0
                    base[0] += g; base[1] += 1
                    inner = st.get(um - 1)           # 内隣
                    outer = st.get(um + 1)           # 外隣
                    nb = [x for x in (inner, outer) if x and x != "?"]
                    has_nige_nb = any(x == "逃" for x in nb)
                    has_oisho_nb = any(x in ("差", "追") for x in nb)
                    # --- 主要な組合せ ---
                    add(f"自{me}・全体", g)
                    if has_nige_nb:
                        add(f"自{me}×隣に逃げ", g)
                    else:
                        add(f"自{me}×隣に逃げ無", g)
                    if inner == "逃":
                        add(f"自{me}×内隣が逃げ", g)
                    if outer == "逃":
                        add(f"自{me}×外隣が逃げ", g)
                    if nb and all(x in ("差", "追") for x in nb):
                        add(f"自{me}×両隣とも差追", g)
                    # 逃げ馬限定: レース全体の逃げ頭数
                    if me == "逃":
                        add(f"逃げ馬・同型{n_nige-1}頭", g)
        day += datetime.timedelta(days=1)

    b = base[0] / base[1] if base[1] else 0
    print(f"=== 隣の馬効果(ゲートのご近所さん) {a.frm}〜{a.to} 人気薄≥{a.usui} ===")
    print(f" [ベース] 複勝{b:.1%}({base[0]}/{base[1]})  ※脚質判定できた馬のみ\n")
    def show(prefix, minn=15):
        rows = [(k, v) for k, v in C.items() if k.startswith(prefix) and v[1] >= minn]
        rows.sort(key=lambda kv: -(kv[1][0] / kv[1][1]))
        for k, v in rows:
            r = v[0] / v[1]
            print(f" {k:24s} {r:5.1%}({v[0]:>3}/{v[1]:>4}) lift{(r/b if b else 0):4.2f}")
    for me in ["逃", "先", "差", "追"]:
        print(f"--- 自分={me} ---")
        show(f"自{me}")
        print()
    print("--- 逃げ馬×レース内の同型数 ---")
    show("逃げ馬・同型")


if __name__ == "__main__":
    main()
