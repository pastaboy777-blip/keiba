#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""南関の出馬表から馬名を探す。出走してきたら拾えるようにするための道具。

  python3 scripts/find_horse.py トゥーナウィッシュ --days 7
  python3 scripts/find_horse.py トゥーナウィッシュ --date 20261004

出馬表が未掲載の日は「まだ」と出る。楽天は開催の1〜2日前に出ることが多い。
"""
from __future__ import annotations
import argparse, datetime, re, sys, time

sys.path.insert(0, '/home/user/keiba/src')
from nankeiba.scraping.client import PoliteClient  # noqa: E402

PLACE = {'浦和': '18', '船橋': '19', '大井': '20', '川崎': '21'}
IDX = 'https://keiba.rakuten.co.jp/race_card/list/RACEID/{}{}00000000'
CARD = 'https://keiba.rakuten.co.jp/race_card/list/RACEID/{}'
HEAD = re.compile(r'\|*([^|]+?)\|+([^|]+?)\|+([^|]+?)\|\(([^)]*)\)\|+([\d.-]+)\|*'
                  r'\s*\n?\s*（([\d-]+)人気）')
c = PoliteClient(use_cache=False)


def get(u, tries=3):
    for i in range(tries):
        try:
            return c.get(u)
        except Exception:
            time.sleep(2 * (i + 1))
    return None


def flat(t):
    t = re.sub(r'<[^>]+>', '|', t)
    t = re.sub(r'\|+', '|', t)
    t = re.sub(r'[ \t]+', ' ', t)
    t = re.sub(r'\|\s*', '|', t)
    return re.sub(r'\s*\|', '|', t)


def scan_day(ymd: str, names: list[str], quiet: bool = False):
    found = []
    for pl, code in PLACE.items():
        idx = get(IDX.format(ymd, code))
        if idx is None:
            continue
        rids = sorted({x for x in re.findall(r'RACEID/(%s%s\d{8})' % (ymd, code), idx)
                       if not x.endswith('00000000')})
        if not rids:
            continue
        hit_place = False
        for rid in rids:
            raw = get(CARD.format(rid))
            if raw is None:
                continue
            if not any(n in raw for n in names):
                time.sleep(0.4)
                continue
            t = flat(raw)
            dm = re.search(r'ダ([\d,]+)m', t)
            dist = int(dm.group(1).replace(',', '')) if dm else 0
            R = int(rid[-2:])
            for u, ch in enumerate(t.split('|消|')[1:], 1):
                m = HEAD.match(ch)
                if not m:
                    continue
                nm = m.group(2).strip()
                if not any(n in nm for n in names):
                    continue
                g = re.search(r'\|(牡|牝|セ)(\d)\|', ch)
                found.append(dict(date=ymd, place=pl, R=R, u=u, nm=nm, dist=dist,
                                  sire=m.group(1).strip(), bms=m.group(4).strip(),
                                  sex=(g.group(1) + g.group(2)) if g else '',
                                  pop=m.group(6), od=m.group(5), rid=rid))
                hit_place = True
            time.sleep(0.4)
        if not quiet and not hit_place:
            print('  %s %s ── いない（%d鞍）' % (ymd, pl, len(rids)))
    return found


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('names', nargs='+', help='探す馬名（部分一致）')
    ap.add_argument('--date', help='YYYYMMDD。指定するとその日だけ')
    ap.add_argument('--days', type=int, default=3, help='今日から何日ぶん見るか')
    ap.add_argument('--quiet', action='store_true', help='見つからなかった場を出さない')
    a = ap.parse_args()
    days = [a.date] if a.date else [
        (datetime.date.today() + datetime.timedelta(days=i)).strftime('%Y%m%d')
        for i in range(a.days)]
    print('■ 探す馬: %s' % '／'.join(a.names))
    all_found = []
    for ymd in days:
        all_found += scan_day(ymd, a.names, a.quiet)
    if not all_found:
        print('\n→ 見つからなかった。出馬表が未掲載の日もある（楽天は開催の1〜2日前）。')
        return
    print('\n★ 出走を見つけた')
    for f in all_found:
        print('  %s %s %dR ダ%dm ／ %d番 %s %s ／ 父%s 母父%s ／ %s人気 %s倍'
              % (f['date'], f['place'], f['R'], f['dist'], f['u'], f['nm'], f['sex'],
                 f['sire'], f['bms'], f['pop'], f['od']))
        print('     出馬表 https://keiba.rakuten.co.jp/race_card/list/RACEID/%s' % f['rid'])


if __name__ == '__main__':
    main()
