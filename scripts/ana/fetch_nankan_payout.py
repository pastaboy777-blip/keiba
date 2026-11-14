# -*- coding: utf-8 -*-
"""南関の単勝・複勝払戻を取る。回収率を出すために要る。

  python3 scripts/ana/fetch_nankan_payout.py <nankan_raw.jsonl> <out.jsonl>

ここまで測ってきたのは全部3着内率だった。3着内15.7%が儲かるかどうかは
そのとき何倍だったかで決まるのに、南関の生データにオッズが入っていない。

ただオッズは要らない。外れた馬の払戻は0なので、
**3着内に来た馬の複勝払戻だけあれば回収率は正確に出る。**

  複勝回収率 = Σ(3着内だった該当馬の複勝払戻) ÷ (100円 × 該当馬の数)
  単勝回収率 = Σ(1着だった該当馬の単勝払戻) ÷ (100円 × 該当馬の数)

払戻ページは1日分の全レースが1ページに載っている。
  https://keiba.rakuten.co.jp/race_dividend/list/RACEID/{rid}
だから1,778鞍でも151回の取得で足りる。CLAUDE.md のとおり1.0〜1.8秒あける。

出す形（1行1鞍）
  {"rid":..., "ymd":..., "ba":..., "R":5,
   "tan":{"8":8570}, "fuku":{"8":820,"12":120,"3":250}}
"""
import gzip
import io
import json
import random
import re
import sys
import time
import urllib.request
from collections import defaultdict

SRC, OUT = sys.argv[1], sys.argv[2]
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36'


def get(url):
    rq = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Encoding': 'gzip'})
    b = urllib.request.urlopen(rq, timeout=40).read()
    if b[:2] == b'\x1f\x8b':
        b = gzip.GzipFile(fileobj=io.BytesIO(b)).read()
    return b.decode('utf-8', 'replace')


def yen(s):
    s = re.sub(r'[^\d]', '', s or '')
    return int(s) if s else None


ROW = re.compile(
    r'<th[^>]*>\s*(単勝|複勝)\s*</th>\s*'
    r'<td class="number"[^>]*>(.*?)</td>\s*'
    r'<td class="money"[^>]*>(.*?)</td>', re.S)


def cell(s):
    """'8<br>12<br>3' → ['8','12','3']"""
    return [re.sub(r'<[^>]+>', '', p).replace('&nbsp;', ' ').strip()
            for p in re.split(r'<br\s*/?>', s)]


def parse(html):
    """1ページから {R: {'tan':{馬番:円}, 'fuku':{馬番:円}}} を作る

    式ごとに <th>単勝</th><td class=number>8</td><td class=money>8,570 円</td>。
    複勝は1つのtdの中を <br> で区切っている。
    """
    out = {}
    # レースの切れ目は <h3 class="headline"><span>■</span>1R&nbsp;…
    parts = re.split(r'<h3 class="headline">\s*<span>■</span>\s*(\d{1,2})R', html)
    for i in range(1, len(parts) - 1, 2):
        R, got = int(parts[i]), {}
        for tag, nums, moneys in ROW.findall(parts[i + 1]):
            us, ys = cell(nums), [yen(y) for y in cell(moneys)]
            if len(us) != len(ys):
                continue
            d = {u: y for u, y in zip(us, ys)
                 if y and re.fullmatch(r'\d{1,2}', u)}
            if d:
                got['tan' if tag == '単勝' else 'fuku'] = d
        if got:
            out[R] = got
    return out


# ── どの日を取るか ────────────────────────────────────────
day = defaultdict(lambda: {'rid': None, 'R': set()})
meta = {}
for l in open(SRC, encoding='utf-8'):
    r = json.loads(l)
    k = (r['ymd'], r['rid'][:12])
    day[k]['rid'] = day[k]['rid'] or r['rid']
    day[k]['R'].add(r['R'])
    meta[(r['ymd'], r['rid'][:12], r['R'])] = (r['rid'], r['ba'])

done = set()
try:
    for l in open(OUT, encoding='utf-8'):
        done.add(json.loads(l)['rid'])
except FileNotFoundError:
    pass
print(f'開催日×場 {len(day)}件　すでに取れている {len(done)}鞍')

f = open(OUT, 'a', encoding='utf-8')
ok = ng = 0
for n, (k, v) in enumerate(sorted(day.items()), 1):
    if all(meta[(k[0], k[1], R)][0] in done for R in v['R']):
        continue
    try:
        P = parse(get(f"https://keiba.rakuten.co.jp/race_dividend/list/RACEID/{v['rid']}"))
    except Exception as e:
        print(f'  {k[0]} {k[1]} 取得できず: {e}', file=sys.stderr)
        ng += 1
        time.sleep(2)
        continue
    for R in sorted(v['R']):
        rid, ba = meta[(k[0], k[1], R)]
        if rid in done or R not in P:
            continue
        f.write(json.dumps(dict(rid=rid, ymd=k[0], ba=ba, R=R,
                                tan=P[R].get('tan', {}), fuku=P[R].get('fuku', {})),
                           ensure_ascii=False) + '\n')
        ok += 1
    f.flush()
    if n % 20 == 0:
        print(f'  {n}/{len(day)}件　{ok}鞍')
    time.sleep(random.uniform(1.0, 1.8))
f.close()
print(f'取れた {ok}鞍　取れなかった日 {ng}件　→ {OUT}')
