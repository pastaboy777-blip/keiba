#!/usr/bin/env python3
"""叩き3戦目以降ピックアップ器。指定日・場の全レースから叩き3戦目以降の馬を必ず洗い出す。
川崎開催は固定ルールで全レース確認(§20-E)。相性タグ(§20-C)が乗る馬は◎印で強調。
使い方: python3 scripts/tataki_pick.py --date 2026-08-01 --place 川崎
        python3 scripts/tataki_pick.py --date 2026-08-01 --place 川崎 --race 5
"""
import sys, argparse, datetime
sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P
from ana_recall import tataki_n, edges_for, field_pace, agari_pattern, _TATAKI_SYNERGY


CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}"


def band(d):
    return "短" if d <= 1200 else ("マ" if d <= 1600 else ("中" if d <= 1900 else "長"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--place", required=True)
    ap.add_argument("--race", type=int, default=None)
    a = ap.parse_args()
    c = PoliteClient()
    ymd = a.date.replace("-", ""); today = datetime.date.fromisoformat(a.date)
    idx = c.get(CARD.format(r=day_index_race_id(ymd, a.place)), use_cache=True)
    races = dict(P.parse_race_links(idx, date_yyyymmdd=ymd, jyo_code=ALL_CODES[a.place]))
    Rs = [a.race] if a.race else sorted(races)
    star = "★川崎=叩き3戦目 必ずピックアップ(§20-E)" if a.place == "川崎" else ""
    print(f"=== {a.date} {a.place} 叩き3戦目以降ピック {star} ===")
    print(" 印: ◎相性=叩き3+×相性タグ(§20-C本線ヒモ) / ○=マ〜中距離(効く帯) / ・=短長帯(弱)")
    total = 0
    for R in Rs:
        rid = races[R]
        _ch = c.get(CARD.format(r=rid), use_cache=True)
        pc = P.parse_card_page(_ch, rid)
        try:
            from rakuten_ped import attach as _apd
            _apd(_ch, pc.entries)
        except Exception:
            pass
        dist = getattr(pc, "distance", None)
        if not dist:
            continue
        tb = band(dist)
        pace, _ = field_pace(pc.entries)
        apct = agari_pattern(pc.entries)
        picks = []
        for e in sorted(pc.entries, key=lambda x: x.umaban or 99):
            if not e.umaban:
                continue
            n = tataki_n(e, today)
            if not (isinstance(n, int) and n >= 3):
                continue
            tags, _ = edges_for(e, dist, pace=pace, agari_pct=apct.get(e.umaban), today=today)
            syn = sorted(tags & _TATAKI_SYNERGY)
            mk = "◎相性" if syn else ("○" if 1300 <= dist <= 1900 else "・")
            pop = getattr(e, "exp_pop", None)
            pops = f"{pop}人気予" if pop else "人気?"
            picks.append((e.umaban, (e.horse_name or "")[:9], n, mk, pops, syn))
        if not picks:
            continue
        print(f"\n {R:>2}R ダ{dist}({tb}帯) 叩き3+該当{len(picks)}頭")
        for um, nm, n, mk, pops, syn in picks:
            total += 1
            syns = ("+" + "/".join(syn)) if syn else ""
            print(f"   {mk:6s} {um:>2} {nm:9s} 叩き{n}戦目 {pops} {syns}")
    print(f"\n --- 計{total}頭ピックアップ{'(川崎は全レース必須)' if a.place=='川崎' else ''} ---")


if __name__ == "__main__":
    main()
