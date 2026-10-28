# -*- coding: utf-8 -*-
"""南関（浦和・船橋・川崎・大井）の着順表・通過順位・ラップを1年ぶん取る。

  python3 scripts/ana/fetch_nankan_year.py <開始YYYYMMDD> <終了YYYYMMDD> <out.jsonl>

楽天のレースIDは  日付(8) + 場(4) + 開催回(2) + 開催日(2) + R(2)。
回と日は日によって変わるので、まず その日のページ から拾う。
成績ページ1枚に 着順表・通過順位・ハロンタイム が全部あるので、
1鞍1回で足りる（着順と通過順位を別々に取る必要はない）。

取得済みは飛ばすので、止めても続きから走る。1.2秒あける。
"""
import datetime as dt
import json, os, re, sys, time, urllib.request

A, B, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36')
BASE = 'https://keiba.rakuten.co.jp'
# 場コードは日程ページで実際に確かめたもの（船橋は1920ではなく1914）
BA = {'1813': '浦和', '1914': '船橋', '2015': '大井', '2135': '川崎'}
SX = re.compile(r'^(牡|牝|セ)\d')


def get(u):
    for i in range(3):
        try:
            b = urllib.request.urlopen(urllib.request.Request(
                u, headers={'User-Agent': UA}), timeout=30).read()
            time.sleep(1.2)
            for enc in ('utf-8', 'euc_jp', 'cp932'):
                try:
                    return b.decode(enc)
                except Exception:
                    pass
            return b.decode('utf-8', 'replace')
        except Exception:
            time.sleep(3 * (i + 1))
    return None


def clean(h):
    h = re.sub(r'<[^>]+>', '\n', h).replace('&nbsp;', ' ')
    return [x.strip() for x in h.split('\n') if x.strip()]


def parse_race(p):
    """成績ページから 着順表・通過順位・ラップ をまとめて取る"""
    L = clean(p)
    head = ' '.join(L[:160])
    dm = re.search(r'[ダ芝]\s*([\d,]{3,5})\s*m', head)
    bm = re.search(r'[ダ芝]\s*[：:]\s*(良|稍重|重|不良)', head)
    tm = re.search(r'天候\s*[：:]\s*(\S+?)\s', head)
    d = {'dist': int(dm.group(1).replace(',', '')) if dm else None,
         'baba': bm.group(1) if bm else None,
         'tenki': tm.group(1) if tm else None}

    j = next((j for j, x in enumerate(L) if 'コーナー通過順位' in x), None)
    if j is not None:
        seg = L[j:j + 14]            # 1600m以上は1角〜4角の4つが並ぶ
        for k, lab in (('１角', 'c1'), ('２角', 'c2'),
                       ('３角', 'c3'), ('４角', 'c4')):
            m = next((m for m, x in enumerate(seg) if x == k), None)
            if m is not None and m + 1 < len(seg):
                d[lab] = [int(x) for x in re.findall(r'\d+', seg[m + 1])]
    i = next((i for i, x in enumerate(L) if x == 'ハロンタイム'), None)
    if i is not None and i + 1 < len(L):
        d['lap'] = [float(x) for x in re.findall(r'\d{1,2}\.\d', L[i + 1])]

    rows = []
    for tb in re.findall(r'<table.*?</table>', p, re.S):
        for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', tb, re.S):
            cs = [clean(x) for x in
                  re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, re.S)]
            if len(cs) < 13:
                continue
            k = next((i for i, c in enumerate(cs)
                      if c and SX.match(c[0].replace(' ', ''))), None)
            if k != 4:               # 着順,枠,馬番,馬名,性齢 の並びだけ採る
                continue
            g = lambda i: (cs[i][0] if i < len(cs) and cs[i] else '')
            rows.append(dict(f=g(0), waku=g(1), u=g(2), nm=g(3), sx=g(4),
                             kin=g(5), wt=g(6), dw=(cs[6][1] if len(cs) > 6
                                                    and len(cs[6]) > 1 else ''),
                             jk=g(7), tm=g(8), mgn=g(9), ag=g(10),
                             tr=g(11), pop=g(12)))
    d['e'] = rows
    d['n'] = len(rows)
    return d


done = set()
if os.path.exists(OUT):
    for l in open(OUT, encoding='utf-8'):
        try:
            done.add(json.loads(l)['rid'])
        except Exception:
            pass
d0 = dt.date(int(A[:4]), int(A[4:6]), int(A[6:]))
d1 = dt.date(int(B[:4]), int(B[4:6]), int(B[6:]))
print(f'{(d1-d0).days+1}日ぶん / 取得済み {len(done)}鞍', flush=True)

f = open(OUT, 'a', encoding='utf-8', buffering=1)
nday = nrace = 0
day = d0
while day <= d1:
    ymd = day.strftime('%Y%m%d')
    day += dt.timedelta(days=1)
    p = get(f'{BASE}/race_card/list/RACEID/{ymd}0000000000')
    if not p:
        continue
    # その日に開催がある南関の 場+回+日 を拾う
    kai = sorted({m[8:16] for m in
                  re.findall(rf'RACEID/({ymd}\d{{10}})', p)
                  if m[8:12] in BA})
    if not kai:
        continue
    nday += 1
    for k in kai:
        for R in range(1, 13):
            rid = f'{ymd}{k}{R:02d}'
            if rid in done:
                continue
            q = get(f'{BASE}/race_performance/list/RACEID/{rid}')
            if not q:
                continue
            d = parse_race(q)
            if not d['e']:
                continue
            d.update(rid=rid, ymd=ymd, ba=BA[k[:4]], R=R)
            f.write(json.dumps(d, ensure_ascii=False) + '\n')
            nrace += 1
    print(f'  {ymd}  {"・".join(BA[x[:4]] for x in kai)}  '
          f'ここまで {nrace}鞍', flush=True)
print(f'完了 {nday}日 {nrace}鞍', flush=True)
