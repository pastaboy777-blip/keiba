# -*- coding: utf-8 -*-
"""楽天競馬の当日結果をまとめて取る。
  python3 res.py 20261007 20 out.json
着順・人気・馬体重・上り3F・4角通過順・ハロンタイム・クラス・内外を拾う。
"""
import json, re, sys, time

sys.path.insert(0, '/home/user/keiba/src')
from nankeiba.scraping.client import PoliteClient  # noqa: E402

YMD, PLACE = sys.argv[1], sys.argv[2]
OUT = sys.argv[3]
ROW = re.compile(
    r'\|(\d+)\|+(\d+)\|+(\d+)\|+([^|]+?)\|+([牡牝セ])(\d)\s*/[^|]*\|+([\d.]+)\|+'
    r'(\d+)\|([+-]?\d+|-)?\|+([^|]+?)\|\([^)]*\)\|+(\d:\d\d\.\d)\|+([^|]*?)\|+'
    r'([\d.]+)\|+([^|]+?)\|+(\d+)\|')
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


def order4(s):
    """'1,10,7,9,(2,11),(8,6),3,(5,4)-12' → {馬番: 通過順}"""
    pos, n = {}, 1
    for g in re.findall(r'\(([\d, ]+)\)|(\d+)', s.replace('=', ',').replace('-', ',')):
        if g[0]:
            us = [int(x) for x in g[0].split(',') if x.strip()]
            for u in us:
                pos[u] = n
            n += len(us)
        elif g[1]:
            pos[int(g[1])] = n
            n += 1
    return pos


idx = get('https://keiba.rakuten.co.jp/race_card/list/RACEID/%s%s00000000' % (YMD, PLACE))
rids = sorted({x for x in re.findall(r'RACEID/(%s%s\d{8})' % (YMD, PLACE), idx)
               if not x.endswith('00000000')})
time.sleep(0.8)
out = {}
for rid in rids:
    R = int(rid[-2:])
    raw = get('https://keiba.rakuten.co.jp/race_performance/list/RACEID/%s' % rid)
    if raw is None:
        print('%2dR 取得NG' % R)
        continue
    t = flat(raw)
    tc = re.sub(r'\|+', '|', t)   # メタ情報はこちらから拾う
    rows = list(ROW.finditer(t))
    if not rows:
        print('%2dR 未確定' % R)
        continue
    dm = re.search(r'ダ([\d,]+)m\(([内外])\)', tc)
    bm = re.search(r'ダ：\|([良稍重不]+)', tc)
    wm = re.search(r'天候：\|([^|]+)\|', tc)
    cm = re.search(r'発走時刻\|\d\d:\d\d\|([^|]+)\|', tc)
    pm = re.search(r'1着([\d,]+)円', tc)
    lm = re.search(r'ハロンタイム\|([\d.\-]+)\|', tc)
    am = re.search(r'上がり\|4F ([\d.]+) - 3F ([\d.]+)', tc)
    c4m = re.search(r'４角\|([^|]+)\|', tc)
    c4 = order4(c4m.group(1)) if c4m else {}
    es = []
    for m in rows:
        u = int(m.group(3))
        es.append(dict(f=m.group(1), waku=int(m.group(2)), u=u, nm=m.group(4).strip(),
                       sx=m.group(5), age=int(m.group(6)), kin=float(m.group(7)),
                       wt=int(m.group(8)), dw=(m.group(9) or ''), jk=m.group(10).strip(),
                       tm=m.group(11), margin=m.group(12).strip(),
                       ag=float(m.group(13)), tr=m.group(14).strip(),
                       pop=int(m.group(15)), c4=c4.get(u)))
    out[str(R)] = dict(rid=rid, dist=int(dm.group(1).replace(',', '')) if dm else 0,
                       course=dm.group(2) if dm else '', baba=bm.group(1) if bm else '',
                       weather=wm.group(1).strip() if wm else '',
                       cls=cm.group(1).strip() if cm else '',
                       p1=int(pm.group(1).replace(',', '')) if pm else 0,
                       lap=lm.group(1) if lm else '',
                       ag4=float(am.group(1)) if am else None,
                       ag3=float(am.group(2)) if am else None,
                       n=len(es), e=es)
    w = es[0]
    print('%2dR ダ%d%s %s %2d頭 %-10s %s ／ 1着 %2d %-14s %2d人気 4角%s 上%.1f'
          % (R, out[str(R)]['dist'], out[str(R)]['course'], out[str(R)]['baba'],
             len(es), out[str(R)]['cls'][:10], out[str(R)]['lap'],
             w['u'], w['nm'][:14], w['pop'], w['c4'], w['ag']))
    time.sleep(0.5)
json.dump(out, open(OUT, 'w'), ensure_ascii=False)
print('→ %s %d鞍' % (OUT, len(out)))
