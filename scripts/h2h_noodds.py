#!/usr/bin/env python3
"""【H2Hアラート・オッズ無し版の検証】
§32のH2Hアラートは「今日の上位"人気"に1戦勝ち」でオッズ必須。
"上位人気"を客観指標(オッズ不要)で代替できるかを測る。

代替候補：
 ①ボス度上位3頭   = 今日の出走馬内での対戦勝率上位(対戦グラフのみ・完全にオッズ不要)
 ②近走成績上位3頭 = 直近5走の3着内率上位(カードのみ・オッズ不要)
比較対象：
 ⓪人気上位3頭     = §32の本家(オッズ必須・lift1.55前後)

さらに「人気薄フィルタ」自体もオッズ必須なので、
 ・人気薄限定(オッズ有り運用＝前日に候補を作り当日フィルタ)
 ・全馬(完全オッズ無し運用)
の両方で出す。

使い方: python3 scripts/h2h_noodds.py --from 2026-01-01 --warmup 2026-07-01 --to 2026-07-24
"""
import sys, argparse, datetime
from collections import defaultdict
sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}"
PERF = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{r}"
TRACKS = ["浦和", "船橋", "大井", "川崎"]


def form_score(e, n=5):
    """近走成績スコア＝直近n走の3着内率(オッズ不要)。走が無ければ None。"""
    rs = [pr.finish_pos for pr in (e.recent_runs or [])[:n] if pr.finish_pos]
    if not rs:
        return None
    return sum(1 for f in rs if f <= 3) / len(rs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", required=True)
    ap.add_argument("--warmup", required=True)
    ap.add_argument("--to", dest="to", required=True)
    ap.add_argument("--usui", type=int, default=6)
    a = ap.parse_args()
    c = PoliteClient()
    d0 = datetime.date.fromisoformat(a.frm); d1 = datetime.date.fromisoformat(a.to)
    warm = datetime.date.fromisoformat(a.warmup)
    hist = defaultdict(list)
    base_u = [0, 0]     # 人気薄ベース
    base_a = [0, 0]     # 全馬ベース
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
                    rr = P.parse_result_page(c.get(PERF.format(r=rid), use_cache=True), rid)
                except Exception:
                    continue
                rows = [(x.horse_name.strip(), x.finish_pos, x.popularity or 0, x.umaban)
                        for x in rr.rows if x.horse_name and x.finish_pos]
                if len(rows) < 6:
                    continue
                names = [n for n, f, p, u in rows]
                if day >= warm:
                    # --- 3つの「上位3頭」を作る ---
                    top_pop = {n for n, f, p, u in rows if p and 1 <= p <= 3}
                    # ①ボス度上位3
                    bs = []
                    for nm in names:
                        w = l = 0
                        for o in names:
                            if o == nm:
                                continue
                            h = hist[(nm, o)]
                            if h:
                                wi = sum(1 for _, r_ in h if r_ == 1)
                                w += wi; l += len(h) - wi
                        if w + l >= 2:
                            bs.append((w / (w + l), w + l, nm))
                    bs.sort(reverse=True)
                    top_boss = {nm for _, _, nm in bs[:3]}
                    # ②近走成績上位3
                    try:
                        pc = P.parse_card_page(c.get(CARD.format(r=rid), use_cache=True), rid)
                        emap = {(e.horse_name or "").strip(): e for e in pc.entries if e.horse_name}
                    except Exception:
                        emap = {}
                    fs = []
                    for nm in names:
                        e = emap.get(nm)
                        if e:
                            v = form_score(e)
                            if v is not None:
                                fs.append((v, nm))
                    fs.sort(reverse=True)
                    top_form = {nm for _, nm in fs[:3]}

                    for name, fin, pop, um in rows:
                        g = 1 if fin <= 3 else 0
                        usui = pop >= a.usui
                        base_a[0] += g; base_a[1] += 1
                        if usui:
                            base_u[0] += g; base_u[1] += 1
                        def beat_any(targets):
                            return any(hist[(name, o)] and any(r_ == 1 for _, r_ in hist[(name, o)])
                                       for o in targets if o != name)
                        hp, hb, hf = beat_any(top_pop), beat_any(top_boss), beat_any(top_form)
                        if usui:
                            if hp: add("U ⓪人気上位に勝利(本家/オッズ要)", g)
                            if hb: add("U ①ボス度上位に勝利(オッズ不要)", g)
                            if hf: add("U ②近走上位に勝利(オッズ不要)", g)
                            if hb and hp: add("U ①∩⓪(両方)", g)
                            if hb and not hp: add("U ①のみ(人気上位には勝ってない)", g)
                        if hb: add("A ①ボス度上位に勝利(全馬)", g)
                        if hf: add("A ②近走上位に勝利(全馬)", g)
                for i in range(len(rows)):
                    for j in range(i + 1, len(rows)):
                        n1, f1 = rows[i][0], rows[i][1]; n2, f2 = rows[j][0], rows[j][1]
                        if f1 < f2:
                            hist[(n1, n2)].append((day, 1)); hist[(n2, n1)].append((day, 0))
                        elif f2 < f1:
                            hist[(n2, n1)].append((day, 1)); hist[(n1, n2)].append((day, 0))
        day += datetime.timedelta(days=1)

    bu = base_u[0] / base_u[1] if base_u[1] else 0
    ba = base_a[0] / base_a[1] if base_a[1] else 0
    print(f"=== H2Hアラート オッズ無し版の検証 {a.warmup}〜{a.to}（南関）===")
    print(f" 人気薄ベース{bu:.1%}(n{base_u[1]}) / 全馬ベース{ba:.1%}(n{base_a[1]})\n")
    print("--- 人気薄限定（＝前日に候補を作り、当日オッズでフィルタする運用）---")
    for k in ["U ⓪人気上位に勝利(本家/オッズ要)", "U ①ボス度上位に勝利(オッズ不要)",
              "U ②近走上位に勝利(オッズ不要)", "U ①∩⓪(両方)", "U ①のみ(人気上位には勝ってない)"]:
        v = C.get(k)
        if not v or not v[1]:
            print(f" {k:34s} n0"); continue
        r = v[0] / v[1]
        print(f" {k:34s} {r:5.1%}({v[0]:>3}/{v[1]:>4}) lift{(r/bu if bu else 0):4.2f}")
    print("\n--- 全馬（＝完全オッズ無し運用）---")
    for k in ["A ①ボス度上位に勝利(全馬)", "A ②近走上位に勝利(全馬)"]:
        v = C.get(k)
        if not v or not v[1]:
            print(f" {k:34s} n0"); continue
        r = v[0] / v[1]
        print(f" {k:34s} {r:5.1%}({v[0]:>3}/{v[1]:>4}) lift{(r/ba if ba else 0):4.2f}")


if __name__ == "__main__":
    main()
