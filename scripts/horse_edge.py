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
sys.path.insert(0,'scripts')
from ana_recall import is_hyperion, _HYPERION_SIRES, _GRIP_SIRES, pace_aptitude, agari_pattern
from tataki_val import tataki_n

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}"
# 南関ダートで"道悪(渋った馬場)巧者"を出しやすい主な種牡馬（経験薄馬の代替判断用・随時追記）
WET_SIRES = {"パイロ", "サウスヴィグラス", "ヘニーヒューズ", "クロフネ", "ゴールドアリュール",
             "エスポワールシチー", "シニスターミニスター", "マジェスティックウォリアー",
             "ドレフォン", "サンダースノー", "コパノリッキー", "ホッコータルマエ", "ゴールドドリーム"}
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
    _chtml = c.get(CARD.format(r=races[a.race]), use_cache=True)
    pc = P.parse_card_page(_chtml, races[a.race])
    from rakuten_ped import attach as _attach_ped
    _attach_ped(_chtml, pc.entries)   # 楽天カードから母父をインライン抽出して付与(グリップ/中山型が母父込みで発火)
    dist = getattr(pc, "distance", None)
    apct = agari_pattern(pc.entries)  # 上がりP(当日出走馬内の終い順位0〜100・小さいほど上位)
    print(f"=== {a.date} {a.place} {a.race}R (ダ{dist}m) 馬ごとエッジ検出 ===")
    for e in sorted(pc.entries, key=lambda x: x.umaban or 99):
        if not e.umaban:
            continue
        recs = e.recent_runs or []
        tags = []
        # --- ペース適性 S/H/F/U (TARGET指数の分類をデータ再現・持続巡航の速度分解より) ---
        _apt = pace_aptitude(e)
        if _apt != "U":
            _lab = {"S": "瞬発S(スロー向)", "H": "持続H(ハイ向)", "F": "自在F"}[_apt]
            tags.append(f"ペース{_lab}")
        # --- 上がりP(亀谷式・当日出走馬内の終い順位) ＋ 差し穴フィルター ---
        _ap = apct.get(e.umaban)
        _dists = [pr.distance for pr in recs if pr.distance]
        _tan = bool(_dists and dist and _dists[0] and _dists[0] > dist)  # 短縮
        if _ap is not None and _ap <= 40:
            tags.append(f"上P上位{_ap}" + ("×短縮◎差穴" if (_ap <= 50 and _tan) else ""))
        elif _ap is not None and _ap <= 50 and _tan:
            tags.append(f"上P{_ap}×短縮◎差穴")
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
        # 持続巡航(Hyperion)型＝垂れない高速巡航(lift1.71の過小評価穴)
        if recs and is_hyperion(recs[0]):
            tags.append("★持続巡航")
        sire = (e.sire or "").strip()
        ds = getattr(e, "dam_sire", "") or ""
        if any(s in sire for s in _GRIP_SIRES) or any(s in ds for s in _GRIP_SIRES):
            tags.append("★グリップ穴")  # 中山パワー×道悪グリップ=夏NAR白砂の大波乱の穴ヒモ(人気薄で)
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
        # 休み明け / 叩きN戦目(§20検証済:人気薄で叩き1=lift0.54,叩き2=0.00の罠,叩き3以降=lift2.02の穴)
        if recs and recs[0].date:
            try:
                d1 = datetime.date.fromisoformat(recs[0].date)
                gap1 = (today - d1).days
                if gap1 >= 60:
                    tags.append(f"休明({gap1}日)✗薄")   # 復帰戦は人気薄で危険(lift0.54)
            except Exception:
                pass
        _tn = tataki_n(e, today)
        if isinstance(_tn, int) and _tn >= 3:
            tags.append(f"★叩き{_tn}戦目(夏穴lift2.0)")  # 疲れ抜けた3戦目以降=夏の人気薄穴
        elif _tn == 2:
            tags.append("叩き2戦目✗(罠0/11)")           # 2戦目は上乗せ無し=消し材料
        # 斤量減(別定の恩恵で軽くなった＝過小評価穴・大井lift1.43)
        if e.weight_carried and recs and recs[0].weight_carried:
            dk = e.weight_carried - recs[0].weight_carried
            if dk <= -1:
                tags.append(f"斤量減{dk:.0f}")
            elif dk >= 2:
                tags.append(f"斤量増+{dk:.0f}")
        # 馬体重トレンド(直近3走)
        ws = [pr.horse_weight for pr in recs[:3] if pr.horse_weight]
        if len(ws) >= 2:
            if ws[0] - ws[-1] >= 8:
                tags.append(f"馬体増{ws[0]-ws[-1]}")
            elif ws[-1] - ws[0] >= 8:
                tags.append(f"馬体減{ws[-1]-ws[0]}")
        cw = e.horse_weight or (ws[0] if ws else None)
        size = "★小" if (cw and cw <= 458) else ("準小" if (cw and cw <= 466) else ("大" if (cw and cw >= 478) else ""))
        print(f"  {e.umaban:>2} {(e.horse_name or '')[:10]:10s} {('体'+str(cw)+size) if cw else '体?':8s} | " + " ".join(tags))


if __name__ == "__main__":
    main()
