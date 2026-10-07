# -*- coding: utf-8 -*-
"""楽天の出馬表から各馬の近5走を取る（場・日付・内外・距離・馬場・着順・上り・馬体重）。

  python3 past5.py 20261006 20 6 12      # 日付 / 場コード / 開始R / 終了R
"""
import json, re, sys, time

sys.path.insert(0, '/home/user/keiba/src')
from nankeiba.scraping.client import PoliteClient  # noqa: E402

S = '/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/scratchpad/'
YMD, PLACE = sys.argv[1], sys.argv[2]
R0, R1 = int(sys.argv[3]), int(sys.argv[4])
PLACES = ('浦和', '川崎', '船橋', '大井', '門別', '盛岡', '水沢', '金沢', '笠松', '名古屋',
          '園田', '姫路', '高知', '佐賀', '札幌', '函館', '福島', '新潟', '東京', '中山',
          '中京', '京都', '阪神', '小倉', '帯広')
HEAD = re.compile(r'\|*([^|]+?)\|+([^|]+?)\|+([^|]+?)\|\(([^)]*)\)\|+([\d.-]+)\|*'
                  r'\s*\n?\s*（([\d-]+)人気）')
# 1走ぶん：着順｜馬場｜頭数頭 … 場 YY.MM.DD … 内/外+距離+右左+ダ … 時計 (着差)｜上り 馬体重k
RUN = re.compile(
    r'\|(\d{1,2})\|+([良稍重不])\|+(\d{1,2})頭\|.*?(' + '|'.join(PLACES) +
    r') (\d\d)\.(\d\d)\.(\d\d)\|.*?(内|外)?(\d{3,4})(?:右|左|直)ダ.*?'
    r'\|(\d:\d\d\.\d) \(([\d.]+)\)\|([\d.]+) (\d{3})k[^|]*\|((?:\d+-)+\d+)\|', re.S)
c = PoliteClient(use_cache=False)


def get(u, n=4):
    for i in range(n):
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


idx = get('https://keiba.rakuten.co.jp/race_card/list/RACEID/%s%s00000000' % (YMD, PLACE))
rids = sorted({x for x in re.findall(r'RACEID/(%s%s\d{8})' % (YMD, PLACE), idx)
               if not x.endswith('00000000')})
time.sleep(0.8)
out = {}
for rid in rids:
    R = int(rid[-2:])
    if not (R0 <= R <= R1):
        continue
    raw = get('https://keiba.rakuten.co.jp/race_card/list/RACEID/%s' % rid)
    if raw is None:
        print('%2dR 取得NG' % R)
        continue
    t = flat(raw)
    dm = re.search(r'ダ([\d,]+)m', t)
    dist = int(dm.group(1).replace(',', '')) if dm else 0
    es = []
    for ch in t.split('|消|')[1:]:
        m = HEAD.match(ch)
        if not m:
            continue
        runs = []
        for g in RUN.findall(ch):
            runs.append(dict(fin=int(g[0]), baba=g[1], fs=int(g[2]), place=g[3],
                             date='%s/%s/%s' % (g[4], g[5], g[6]),
                             course=g[7] or '', dist=int(g[8]),
                             time=g[9], margin=float(g[10]),
                             ag=float(g[11]), wt=int(g[12]),
                             cor=g[13], c4=int(g[13].split('-')[-1])))
        es.append(dict(nm=m.group(2).strip(), sire=m.group(1).strip(),
                       pop=(int(m.group(6)) if m.group(6).isdigit() else None),
                       runs=runs[:5]))
    for j, e in enumerate(es, 1):
        e['u'] = j
    out[str(R)] = dict(dist=dist, n=len(es), e=es)
    print('%2dR ダ%d %2d頭 ／ 近走を拾えた馬 %d'
          % (R, dist, len(es), sum(1 for e in es if e['runs'])))
    time.sleep(0.6)
json.dump(out, open(S + 'past5_%s_%s.json' % (YMD, PLACE), 'w'), ensure_ascii=False)
print('→ past5_%s_%s.json' % (YMD, PLACE))
