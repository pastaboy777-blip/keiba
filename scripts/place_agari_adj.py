# -*- coding: utf-8 -*-
"""場×距離帯の上がり補正値を実測する。

399フィルター①「馬場を揃える」の弱点(=川崎未経験の遠征馬を全消しする)を埋めるため、
他場の上がりを川崎基準に引き直す補正値を、南関の実データから作る。

方法: 同一馬が異なる場を走った実績をペアにして、同一距離帯での上がり差の中央値を取る。
これなら「速い馬ばかりが集まる場」というバイアスを馬固定で除ける。
"""
from __future__ import annotations
import json, glob, statistics
from collections import defaultdict

BANDS = [(0, 1000, '900'), (1001, 1400, '1400'), (1401, 1600, '1600'), (1601, 9999, '2000')]


def band(d):
    if not d:
        return None
    for lo, hi, name in BANDS:
        if lo <= d <= hi:
            return name
    return None


def main():
    # horse_id -> [(place, band, baba, agari)]
    runs = defaultdict(list)
    seen = set()
    for f in sorted(glob.glob('/home/user/keiba/data/samples/nankan_*.jsonl')):
        for line in open(f):
            d = json.loads(line)
            for h in d.get('horses', []):
                hid = h.get('horse_id')
                if not hid:
                    continue
                for p in (h.get('recent_runs') or []):
                    ag, pl, dist = p.get('agari'), p.get('place'), p.get('distance')
                    b = band(dist)
                    if not (ag and pl and b):
                        continue
                    key = (hid, p.get('date'), pl, dist)
                    if key in seen:
                        continue
                    seen.add(key)
                    runs[hid].append((pl, b, p.get('baba'), ag))

    # 同一馬・同一距離帯で 川崎 と 他場 の両方を走っている組から差を取る
    diffs = defaultdict(list)
    for hid, rs in runs.items():
        by = defaultdict(lambda: defaultdict(list))
        for pl, b, baba, ag in rs:
            by[b][pl].append(ag)
        for b, m in by.items():
            if '川崎' not in m:
                continue
            base = statistics.median(m['川崎'])
            for pl, ags in m.items():
                if pl == '川崎':
                    continue
                diffs[(pl, b)].append(statistics.median(ags) - base)

    print('■ 上がり補正（他場の上がり − 川崎の上がり／同一馬・同一距離帯の中央値）')
    print('  正の値 = その場のほうが上がりが掛かる（遅い）／負 = その場のほうが速く出る')
    print(f"  {'場':<5}{'帯':<7}{'n':>6}{'補正':>9}")
    out = {}
    for (pl, b), v in sorted(diffs.items(), key=lambda x: (x[0][0], x[0][1])):
        if len(v) < 30:
            continue
        med = statistics.median(v)
        out[f'{pl}|{b}'] = round(med, 2)
        print(f'  {pl:<5}{b:<7}{len(v):>6}{med:>+9.2f}')
    json.dump(out, open('/home/user/keiba/data/samples/place_agari_adj.json', 'w'), ensure_ascii=False, indent=1)
    print('\n→ data/samples/place_agari_adj.json に保存')
    print('  使い方: 川崎換算の上がり = 他場の上がり − 補正値')


if __name__ == '__main__':
    main()


def band_adj():
    """川崎内で、距離帯どうしの上がり差を同一馬で測る（1400を基準）。"""
    runs = defaultdict(list)
    seen = set()
    for f in sorted(glob.glob('/home/user/keiba/data/samples/nankan_*.jsonl')):
        for line in open(f):
            d = json.loads(line)
            for h in d.get('horses', []):
                hid = h.get('horse_id')
                if not hid:
                    continue
                for p in (h.get('recent_runs') or []):
                    ag, pl, dist = p.get('agari'), p.get('place'), p.get('distance')
                    b = band(dist)
                    if not (ag and pl == '川崎' and b):
                        continue
                    key = (hid, p.get('date'))
                    if key in seen:
                        continue
                    seen.add(key)
                    runs[hid].append((b, ag))
    diffs = defaultdict(list)
    for hid, rs in runs.items():
        by = defaultdict(list)
        for b, ag in rs:
            by[b].append(ag)
        if '1400' not in by:
            continue
        base = statistics.median(by['1400'])
        for b, ags in by.items():
            if b == '1400':
                continue
            diffs[b].append(statistics.median(ags) - base)
    print('\n■ 距離帯補正（川崎内・1400基準／同一馬の中央値）')
    out = {'1400': 0.0}
    for b, v in sorted(diffs.items()):
        if len(v) < 30:
            continue
        out[b] = round(statistics.median(v), 2)
        print(f'  {b:<7}{len(v):>6}{out[b]:>+9.2f}')
    json.dump(out, open('/home/user/keiba/data/samples/band_agari_adj.json', 'w'), ensure_ascii=False, indent=1)
    print('→ data/samples/band_agari_adj.json に保存')
