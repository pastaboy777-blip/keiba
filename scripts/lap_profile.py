# -*- coding: utf-8 -*-
"""ある鞍の全頭について、過去走のラップを集めて「どういうラップで走るか」を見る。

  python3 lapprof.py <出馬表のRACEID> <出力json>
"""
import json, re, sys, time
sys.path.insert(0, '/home/user/keiba/src')
from nankeiba.scraping.client import PoliteClient  # noqa: E402

RID, OUT = sys.argv[1], sys.argv[2]
ROW = re.compile(
    r'\|(\d+)\|+(\d+)\|+(\d+)\|+([^|]+?)\|+([牡牝セ])(\d)\s*/[^|]*\|+([\d.]+)\|+'
    r'(\d+)\|([+-±]?\d+|-)?\|+([^|]+?)\|+\([^)]*\)\|+((?:\d:)?\d\d\.\d)\|+([^|]*?)\|+'
    r'([\d.]+)\|+([^|]+?)\|+(\d+)\|')
HEAD = re.compile(r'\|*([^|]+?)\|+([^|]+?)\|+([^|]+?)\|\(([^)]*)\)\|+([\d.-]+)\|*'
                  r'\s*\n?\s*（([\d-]+)人気）')
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


def order(s):
    pos, n = {}, 1
    for g in re.findall(r'\(([\d, ]+)\)|(\d+)', s.replace('=', ',').replace('-', ',')):
        if g[0]:
            for u in [int(x) for x in g[0].split(',') if x.strip()]:
                pos[u] = n
            n += len(g[0].split(','))
        elif g[1]:
            pos[int(g[1])] = n
            n += 1
    return pos


raw = get('https://keiba.rakuten.co.jp/race_card/list/RACEID/%s' % RID)
card = flat(raw)
names = []
for ch in card.split('|消|')[1:]:
    m = HEAD.match(ch)
    if m:
        names.append(m.group(2).strip())
# 馬名の位置で生HTMLを切り、その区間に出てくるRACEIDをその馬の過去走とする
pos = []
for j, nm in enumerate(names, 1):
    ps = [m.start() for m in re.finditer(re.escape(nm), raw)]
    pos.append((ps[-1] if len(ps) > 1 else (ps[0] if ps else 0), j, nm))
pos.sort()
ids = [(m.start(), m.group(1)) for m in re.finditer(r'RACEID/(\d{18})', raw)]
horses = []
for i, (st, j, nm) in enumerate(pos):
    en = pos[i + 1][0] if i + 1 < len(pos) else 10 ** 9
    rids = [x for p0, x in ids if st <= p0 < en and not x.startswith(RID[:10])
            and x[8:10] in ('18', '19', '20', '21')]
    horses.append(dict(nm=nm, u=j, rids=sorted(set(rids), reverse=True)[:6]))
horses.sort(key=lambda z: z['u'])
print('%d頭 ／ 過去走 %d鞍' % (len(horses), len({r for h in horses for r in h['rids']})))

cache = {}
def race(rid):
    if rid in cache:
        return cache[rid]
    raw = get('https://keiba.rakuten.co.jp/race_performance/list/RACEID/%s' % rid)
    cache[rid] = None
    if raw is None:
        return None
    t = flat(raw)
    tc = re.sub(r'\|+', '|', t)
    lm = re.search(r'ハロンタイム\|([\d.\-]+)\|', tc)
    dm = re.search(r'ダ([\d,]+)m(?:\((内|外)\))?', tc)
    if not lm or not dm:
        return None
    bm = re.search(r'ダ：\|([良稍重不]+)', tc)
    am = re.search(r'上がり\|4F ([\d.]+) - 3F ([\d.]+)', tc)
    c1a = re.findall(r'１角\|([^|]+)\|', tc)
    c4a = re.findall(r'４角\|([^|]+)\|', tc)
    rows = {}
    for g in ROW.finditer(t):
        rows[g.group(4).strip()] = dict(fin=int(g.group(1)), pop=int(g.group(15)),
                                        tm=g.group(11), ag=float(g.group(13)))
    v = [float(x) for x in lm.group(1).split('-') if x]
    cache[rid] = dict(rid=rid, d='%s/%s/%s' % (rid[2:4], rid[4:6], rid[6:8]),
                      ba={'18': '浦和', '19': '船橋', '20': '大井', '21': '川崎'}.get(rid[8:10], '?'),
                      dist=int(dm.group(1).replace(',', '')), baba=bm.group(1) if bm else '',
                      lap=v, ag3=float(am.group(2)) if am else None, n=len(rows),
                      c1=order(c1a[-1]) if c1a else {}, c4=order(c4a[-1]) if c4a else {},
                      rows=rows)
    time.sleep(0.5)
    return cache[rid]


for h in horses:
    h['past'] = []
    for rid in h['rids']:
        r = race(rid)
        if not r or h['nm'] not in r['rows']:
            continue
        me = r['rows'][h['nm']]
        b = r['lap'][1:] if r['lap'] and r['lap'][0] < 10 else r['lap']
        if len(b) < 4:
            continue
        f3, l3 = sum(b[:3]), sum(b[-3:])
        drops = [(b[i] - b[i - 1], i + 1) for i in range(1, len(b))]
        mx = max(drops)
        h['past'].append(dict(d=r['d'], ba=r['ba'], dist=r['dist'], baba=r['baba'], n=r['n'],
                              fin=me['fin'], pop=me['pop'], ag=me['ag'],
                              c1=None, c4=None, lap='-'.join('%.1f' % x for x in r['lap']),
                              f3=round(f3, 1), l3=round(l3, 1), pace=round(f3 - l3, 1),
                              drop=round(mx[0], 1), dropat=mx[1], ag3=r['ag3']))
    print('%2d %-14s 過去%d鞍' % (h['u'], h['nm'], len(h['past'])))
json.dump(horses, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('→', OUT)
