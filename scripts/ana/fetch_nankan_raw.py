# -*- coding: utf-8 -*-
"""南関の着順表と、通過順位を「記号を落とさず」取る。

  python3 scripts/ana/fetch_nankan_raw.py <開始YYYYMMDD> <終了YYYYMMDD> <out.jsonl>

fetch_nankan_year.py は通過順位を re.findall(r'\\d+') で数字だけ抜いていて、
括弧を捨てている。括弧には内外が入っているので、生のまま残す版を別に作る。
（既存ファイルは消さず別名で追加する）

括弧の意味（実データで確かめた。楽天のページに凡例はない）
  - 船橋24鞍221個の括弧のうち、馬番の昇順どおりは81.4%。残り18.6%は
    順番が入れ替わっているので、馬番順に並べているのではない
  - 括弧の中の順番と馬番の相関は 1角+0.58・2角+0.62・3角+0.52・4角+0.38。
    ゲート直後に強く、進むほど弱まる＝位置そのもの。内枠の馬が先に来る
  → netkeiba と同じく「内側から外へ」

楽天のレースページは utf-8（2026/11時点。euc_jp ではない）。
取得済みの rid は飛ばすので、止めても続きから走る。1.2秒あける。
"""
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time

A, B, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36')
BASE = 'https://keiba.rakuten.co.jp'
BA = {'1813': '浦和', '1914': '船橋', '2015': '大井', '2135': '川崎'}
SX = re.compile(r'^(牡|牝|セ)\d')


def get(u):
    for i in range(3):
        try:
            b = subprocess.run(['curl', '-sS', '-A', UA, '-H', 'Accept-Language: ja',
                                '--compressed', u], capture_output=True, timeout=40).stdout
            time.sleep(1.2)
            if len(b) > 6000:
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


def parse(p):
    L = clean(p)
    head = ' '.join(L[:160])
    dm = re.search(r'[ダ芝]\s*([\d,]{3,5})\s*m', head)
    bm = re.search(r'[ダ芝]\s*[：:]\s*(良|稍重|重|不良)', head)
    d = {'dist': int(dm.group(1).replace(',', '')) if dm else None,
         'surf': ('芝' if '芝' in (dm.group(0) if dm else '') else 'ダ'),
         'baba': bm.group(1) if bm else None}

    i = p.find('コーナー通過順位')
    if i > 0:
        seg = re.sub(r'\s+', '', re.sub(r'<[^>]+>', '|', p[i:i + 1400]))
        for lab, key in (('１角', 'c1'), ('２角', 'c2'),
                         ('３角', 'c3'), ('４角', 'c4')):
            m = re.search(re.escape(lab) + r'\|+([0-9,\-=()*|]+?)\|', seg)
            if m:
                d[key] = m.group(1).replace('|', '')      # 記号ごと残す
    j = next((j for j, x in enumerate(L) if x == 'ハロンタイム'), None)
    if j is not None and j + 1 < len(L):
        d['lap'] = [float(x) for x in re.findall(r'\d{1,2}\.\d', L[j + 1])]

    rows = []
    for tb in re.findall(r'<table.*?</table>', p, re.S):
        for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', tb, re.S):
            cs = [clean(x) for x in
                  re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, re.S)]
            if len(cs) < 13:
                continue
            k = next((i for i, c in enumerate(cs)
                      if c and SX.match(c[0].replace(' ', ''))), None)
            if k != 4:
                continue
            g = lambda i: (cs[i][0] if i < len(cs) and cs[i] else '')
            rows.append(dict(f=g(0), waku=g(1), u=g(2), nm=g(3), sx=g(4),
                             kin=g(5), wt=g(6), jk=g(7), tm=g(8), mgn=g(9),
                             ag=g(10), tr=g(11), pop=g(12)))
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
nd = nr = 0
day = d0
while day <= d1:
    ymd = day.strftime('%Y%m%d')
    day += dt.timedelta(days=1)
    p = get(f'{BASE}/race_card/list/RACEID/{ymd}0000000000')
    if not p:
        continue
    kai = sorted({m[8:16] for m in re.findall(rf'RACEID/({ymd}\d{{10}})', p)
                  if m[8:12] in BA})
    if not kai:
        continue
    nd += 1
    for k in kai:
        for R in range(1, 13):
            rid = f'{ymd}{k}{R:02d}'
            if rid in done:
                continue
            q = get(f'{BASE}/race_performance/list/RACEID/{rid}')
            if not q:
                continue
            d = parse(q)
            if not d['e']:
                continue
            d.update(rid=rid, ymd=ymd, ba=BA[k[:4]], R=R)
            f.write(json.dumps(d, ensure_ascii=False) + '\n')
            nr += 1
    print(f'  {ymd} {"・".join(BA[x[:4]] for x in kai)}　累計 {nr}鞍', flush=True)
print(f'完了　{nd}日 {nr}鞍', flush=True)
