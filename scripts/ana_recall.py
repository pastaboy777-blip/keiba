#!/usr/bin/env python3
"""穴のrecall検証 ── 実際に来た穴を、うちのファクターで"事前に拾えたか"を採点する。

穴検出の自己評価が無い(=何を見落としたか分からない)課題を潰す。指定日の各レースで
好走した穴(6番人気以下で3着内)を列挙し、各馬が持っていたエッジ(小型/道悪巧者/短縮/差し/
血統湿)を数える。エッジ2つ以上=「拾えた」、0-1=「見落とし」として recall を算出。

使い方:
  python3 scripts/ana_recall.py --date 2026-07-17 --place 浦和 [--pop 6]

出力: 来た穴ごとに持っていたエッジと 拾/見落とし、開催の recall%、見落とし穴の特徴。
"""
import sys, argparse
sys.path.insert(0, "src")
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}"
PERF = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{r}"
BAD = ("稍", "重", "不")
WET_SIRES = {"パイロ", "サウスヴィグラス", "ヘニーヒューズ", "クロフネ", "ゴールドアリュール",
             "エスポワールシチー", "シニスターミニスター", "マジェスティックウォリアー",
             "ドレフォン", "サンダースノー", "コパノリッキー", "ホッコータルマエ", "ゴールドドリーム"}


def edges_for(e, today_dist, small_bias=True):
    """馬のエッジ集合を返す（穴ファクター）。"""
    recs = e.recent_runs or []
    tags = set()
    cw = e.horse_weight or (recs[0].horse_weight if recs and recs[0].horse_weight else None)
    if cw and cw <= 458:
        tags.add("小型")
    elif cw and cw <= 466:
        tags.add("準小型")  # 459-466＝境界。小型バイアス日は拾う
    run = good = 0
    for pr in recs:
        if any(x in (pr.baba or "") for x in BAD):
            run += 1
            if pr.finish_pos and pr.finish_pos <= 3:
                good += 1
    if run and good >= 1 and good >= run * 0.5:
        tags.add("道悪巧者")
    dists = [pr.distance for pr in recs if pr.distance]
    if dists and today_dist and dists[0] and dists[0] > today_dist:
        tags.add("距離短縮")
    if recs and recs[0].corner:
        co = [x for x in recs[0].corner if isinstance(x, (int, float))]
        fs = recs[0].field_size or 12
        if co and (co[0] > fs * 0.55 or co[-1] > fs * 0.55):
            tags.add("差し")
    sire = (e.sire or "")
    if any(s in sire for s in WET_SIRES):
        tags.add("血統湿")
    return tags, cw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--place", required=True)
    ap.add_argument("--pop", type=int, default=6, help="この人気以下を穴とする")
    ap.add_argument("--small-bias", action="store_true",
                    help="小型有利が確定した日用＝小型1つで拾える(bias_forecastが小型[信頼高]の時に付ける)")
    a = ap.parse_args()
    c = PoliteClient()
    ymd = a.date.replace("-", "")
    idx = c.get(CARD.format(r=day_index_race_id(ymd, a.place)), use_cache=True)
    races = dict(P.parse_race_links(idx, date_yyyymmdd=ymd, jyo_code=ALL_CODES[a.place]))
    caught = missed = 0
    miss_detail = []
    print(f"=== 穴recall検証: {a.date} {a.place} (穴={a.pop}番人気以下で3着内) ===")
    for R in sorted(races):
        try:
            rr = P.parse_result_page(c.get(PERF.format(r=races[R]), use_cache=True), races[R])
            if not rr.rows or not rr.rows[0].finish_pos:
                continue
            pc = P.parse_card_page(c.get(CARD.format(r=races[R]), use_cache=True), races[R])
        except Exception:
            continue
        emap = {e.umaban: e for e in pc.entries}
        dist = getattr(pc, "distance", None)
        for row in rr.rows:
            if row.finish_pos and row.finish_pos <= 3 and row.popularity and row.popularity >= a.pop:
                e = emap.get(row.umaban)
                if not e:
                    continue
                tags, cw = edges_for(e, dist)
                # 小型バイアス日は「小型」単独でも拾える（①が小型[信頼高]の時）
                ok = len(tags) >= 2 or (a.small_bias and "小型" in tags)
                mark = "拾✓" if ok else "見✗"
                if ok:
                    caught += 1
                else:
                    missed += 1
                    miss_detail.append((R, row.horse_name, row.popularity, tags))
                print(f"  {R:>2}R {row.finish_pos}着 {row.horse_name[:9]:9s} {row.popularity:>2}人気 体{cw} [{mark}] {'/'.join(sorted(tags)) or 'エッジ無'}")
    tot = caught + missed
    print(f"\n--- recall = {caught}/{tot} = {caught/tot:.0%} (穴のうちエッジ2つ以上で拾えた割合) ---" if tot else "対象穴なし")
    if miss_detail:
        print("見落とし穴（次に強化すべき盲点）:")
        for R, nm, pop, tags in miss_detail:
            print(f"  {R}R {nm[:9]} {pop}人気 : 保有エッジ={'/'.join(sorted(tags)) or 'なし'}")


if __name__ == "__main__":
    main()
