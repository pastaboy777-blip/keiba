#!/usr/bin/env python3
"""馬ごとの"見抜きにくい穴の芽"を体系検出する。

穴検出の盲点＝(a)道悪適性が粗い (b)変わり身(初条件/叩き/短縮)が短評頼り、を潰す。
1レースの各馬に、道悪適性(馬場程度別)・血統タグ・変わり身フラグを機械付与する。

使い方:
  python3 scripts/horse_edge.py --date 2026-07-17 --place 浦和 --race 5

出力: 各馬に [道悪x-y] [血統] [初距離/初コース/休明/叩2/短縮N/体増減] 等のタグ。
人気薄×好フラグ＝隠れ穴の候補。
"""
import sys, argparse, datetime
sys.path.insert(0, "src")
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}"
# 南関ダートで"道悪(渋った馬場)巧者"を出しやすい主な種牡馬（経験薄馬の代替判断用・随時追記）
WET_SIRES = {"パイロ", "サウスヴィグラス", "ヘニーヒューズ", "クロフネ", "ゴールドアリュール",
             "エスポワールシチー", "シニスターミニスター", "マジェスティックウォリアー",
             "ドレフォン", "サンダースノー", "コパノリッキー", "ホッコータルマエ"}
BAD = ("稍", "重", "不")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--place", required=True)
    ap.add_argument("--race", type=int, required=True)
    a = ap.parse_args()
    c = PoliteClient()
    ymd = a.date.replace("-", "")
    today = datetime.date.fromisoformat(a.date)
    idx = c.get(CARD.format(r=day_index_race_id(ymd, a.place)), use_cache=True)
    races = dict(P.parse_race_links(idx, date_yyyymmdd=ymd, jyo_code=ALL_CODES[a.place]))
    pc = P.parse_card_page(c.get(CARD.format(r=races[a.race]), use_cache=True), races[a.race])
    dist = getattr(pc, "distance", None)
    print(f"=== {a.date} {a.place} {a.race}R (ダ{dist}m) 馬ごとエッジ検出 ===")
    for e in sorted(pc.entries, key=lambda x: x.umaban or 99):
        if not e.umaban:
            continue
        recs = e.recent_runs or []
        tags = []
        # --- 道悪適性(馬場程度別) ---
        lv = {"稍": [0, 0], "重": [0, 0], "不": [0, 0]}
        for pr in recs:
            b = pr.baba or ""
            for k in lv:
                if k in b:
                    lv[k][0] += 1
                    if pr.finish_pos and pr.finish_pos <= 3:
                        lv[k][1] += 1
        run = sum(v[0] for v in lv.values()); good = sum(v[1] for v in lv.values())
        if run:
            det = ",".join(f"{k}{v[1]}/{v[0]}" for k, v in lv.items() if v[0])
            mark = "★巧者" if good >= 1 and good >= run * 0.5 else ("✗苦手" if run >= 2 and good == 0 else "")
            tags.append(f"道悪{good}/{run}({det}){mark}")
        else:
            tags.append("道悪未経験")
        # --- 血統(道悪の代替判断) ---
        sire = (e.sire or "").strip()
        if sire:
            wet = "◎湿" if any(s in sire for s in WET_SIRES) else ""
            tags.append(f"父{sire}{wet}")
        # --- 変わり身フラグ ---
        dists = [pr.distance for pr in recs if pr.distance]
        places = [pr.place for pr in recs if pr.place]
        if dist and dists and dist not in dists:
            tags.append("初距離")
        if dists and dist and dists[0] and dists[0] > dist:
            tags.append(f"短縮{dists[0]-dist}")
        elif dists and dist and dists[0] and dists[0] < dist:
            tags.append("延長")
        if places and a.place not in places:
            tags.append("初コース/転入")
        # 休み明け / 叩き2走目
        if recs and recs[0].date:
            try:
                d1 = datetime.date.fromisoformat(recs[0].date)
                gap1 = (today - d1).days
                if gap1 >= 60:
                    tags.append(f"休明({gap1}日)")
                elif len(recs) >= 2 and recs[1].date:
                    d2 = datetime.date.fromisoformat(recs[1].date)
                    if (d1 - d2).days >= 60:
                        tags.append("叩2走目↑")
            except Exception:
                pass
        # 馬体重トレンド(直近3走)
        ws = [pr.horse_weight for pr in recs[:3] if pr.horse_weight]
        if len(ws) >= 2:
            if ws[0] - ws[-1] >= 8:
                tags.append(f"馬体増{ws[0]-ws[-1]}")
            elif ws[-1] - ws[0] >= 8:
                tags.append(f"馬体減{ws[-1]-ws[0]}")
        cw = e.horse_weight or (ws[0] if ws else None)
        size = "★小" if (cw and cw <= 458) else ("大" if (cw and cw >= 478) else "")
        print(f"  {e.umaban:>2} {(e.horse_name or '')[:10]:10s} {('体'+str(cw)+size) if cw else '体?':8s} | " + " ".join(tags))


if __name__ == "__main__":
    main()
