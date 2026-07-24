#!/usr/bin/env python3
"""馬の個性=条件シグネチャ検出。各馬の過去走から"ベスト条件(得意距離帯・得意場)"を抽出し、
今日それが揃う馬を炙る＝「馬の個性が今日ハマる穴」候補。人気薄でこれが立つ馬が本線。
使い方: python3 scripts/horse_profile.py --date 2026-07-24 --place 大井 --race 7
"""
import sys, argparse
from collections import defaultdict
sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}"


def band(d):
    return "短" if d <= 1200 else ("マ" if d <= 1600 else ("中" if d <= 1900 else "長"))


def _good(pr):
    return bool(pr.finish_pos and (pr.finish_pos <= 3 or (pr.field_size and pr.finish_pos <= pr.field_size * 0.3)))


def profile(e, n=8):
    """(ベスト距離帯, ベスト場, 距離stat, 場stat)。stat=cond->好走率(2走以上)。"""
    recs = (e.recent_runs or [])[:n]
    ds, ps = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    for pr in recs:
        g = _good(pr)
        if pr.distance:
            b = band(pr.distance); ds[b][1] += 1; ds[b][0] += 1 if g else 0
        if pr.place:
            ps[pr.place][1] += 1; ps[pr.place][0] += 1 if g else 0
    best_d = max([(v[0] / v[1], k) for k, v in ds.items() if v[1] >= 2], default=(0, None))[1]
    best_p = max([(v[0] / v[1], k) for k, v in ps.items() if v[1] >= 2], default=(0, None))[1]
    return best_d, best_p, ds, ps


def signature(e, today_band, today_dist, n=8):
    """検証済み(§19)の"効く"シグネチャ判定を返すdict。
    ◎距=今日=ベスト距離帯 かつ その帯が本物の得意(好走率≥40%・2走以上)→lift1.62。
    さらに前走からの距離短縮なら◎距×短縮→lift1.79(既存短縮lift1.86と整合)。
    得意帯じゃない人気薄は4%(lift0.57)に沈む＝◎距不在は消し候補。
    ※場は南関の単独開催では全馬が当該場ベストになり死ぬ(lift0.98)→採用しない。"""
    bd, bp, ds, _ = profile(e, n)
    is_best = bool(bd and bd == today_band)
    cell = ds.get(today_band, [0, 0])
    real = bool(is_best and cell[1] >= 2 and cell[0] / cell[1] >= 0.40)  # 本物の得意帯
    dists = [pr.distance for pr in (e.recent_runs or []) if pr.distance]
    tan = bool(real and dists and dists[0] and today_dist and dists[0] > today_dist)
    return {"best_d": bd, "is_best": is_best, "real": real, "tan": tan, "cell": cell}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True); ap.add_argument("--place", required=True)
    ap.add_argument("--race", type=int, required=True)
    a = ap.parse_args()
    c = PoliteClient(); ymd = a.date.replace("-", "")
    idx = c.get(CARD.format(r=day_index_race_id(ymd, a.place)), use_cache=True)
    races = dict(P.parse_race_links(idx, date_yyyymmdd=ymd, jyo_code=ALL_CODES[a.place]))
    pc = P.parse_card_page(c.get(CARD.format(r=races[a.race]), use_cache=True), races[a.race])
    dist = getattr(pc, "distance", None); tb = band(dist) if dist else None
    print(f"=== {a.date} {a.place} {a.race}R (ダ{dist}m={tb}帯) 条件シグネチャ(§19検証済) ===")
    print(" ◎距★=今日が本物の得意帯(好走率≥40%)lift1.62 / +短縮=×短縮 lift1.79 / 消=得意帯不在(人気薄4%)")
    for e in sorted(pc.entries, key=lambda x: x.umaban or 99):
        if not e.umaban:
            continue
        sg = signature(e, tb, dist)
        _, _, ds, _ = profile(e)
        if sg["tan"]:
            mk = "★◎距×短縮"
        elif sg["real"]:
            mk = "★◎距(本物の得意)"
        elif sg["is_best"]:
            mk = "△距(得意薄)"
        else:
            mk = "消(得意帯不在)"
        c = sg["cell"]; cr = f"{c[0]}/{c[1]}" if c[1] else "0"
        dsr = ",".join(f"{k}{v[0]}/{v[1]}" for k, v in ds.items())
        print(f"  {e.umaban:>2} {(e.horse_name or '')[:9]:9s} ベスト距離={sg['best_d'] or '-'}(今帯{cr}) [{mk}]  (距離別 {dsr})")


if __name__ == "__main__":
    main()
