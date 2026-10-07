# -*- coding: utf-8 -*-
"""穴で来た馬だけ、近走の実ラップを楽天から取って今日のラップと並べる。"""
import json, re, sys, time

sys.path.insert(0, '/home/user/keiba/src')
from nankeiba.scraping.client import PoliteClient  # noqa: E402

S = '/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/scratchpad/'
res = json.load(open('/home/user/keiba/notes/live/2026-10-07/results.json', encoding='utf-8'))
p5 = json.load(open(S + 'past5_20261007_20.json', encoding='utf-8'))
CODE = {'大井': '20', '船橋': '19', '浦和': '18', '川崎': '21'}
c = PoliteClient(use_cache=False)


def get(u, n=3):
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
    t = re.sub(r'\s*\|', '|', t)
    return re.sub(r'\|+', '|', t)


def shape(lap):
    v = [float(x) for x in lap.split('-') if x]
    if len(v) < 4:
        return None
    b = v[1:] if v[0] < 10 else v
    h = len(b) // 2
    return sum(b[h:]) / (len(b) - h) - sum(b[:h]) / h


# ── 穴で来た馬（7番人気以下で3着内） ─────────────────────
targets = []
for Rs in sorted(res, key=lambda x: int(x)):
    r = res[Rs]
    for e in r['e']:
        f = str(e.get('f', ''))
        if f.isdigit() and int(f) <= 3 and int(e['pop']) >= 7:
            pr = {x['u']: x for x in (p5.get(Rs, {}).get('e') or [])}
            targets.append((int(Rs), r, e, pr.get(e['u'], {})))
print('■ 穴で来た馬 %d頭' % len(targets))

cache = {}
for Rn, r, e, c5 in targets:
    today = shape(r['lap'])
    print()
    print('=' * 92)
    print('■ %dR ダ%d%s %s ／ %d着 %s（%s人気） 4角%s 上%.1f %sk(%s)'
          % (Rn, r['dist'], r['course'], r['cls'][:18], int(e['f']), e['nm'],
             e['pop'], e['c4'], e['ag'], e['wt'], e.get('dw', '')))
    print('   今日  %-46s  形 %+.2f 秒/F' % (r['lap'], today))
    print('   ' + '-' * 86)
    for x in (c5.get('runs') or []):
        pl = x['place']
        if pl not in CODE:
            print('   %s %s%s%dm %s %2d着/%2d頭 上%.1f  ── %sはラップを取れない'
                  % (x['date'], pl, x['course'], x['dist'], x['baba'], x['fin'], x['fs'], x['ag'], pl))
            continue
        ymd = '20' + x['date'].replace('/', '')
        key = (ymd, pl)
        if key not in cache:
            idx = get('https://keiba.rakuten.co.jp/race_card/list/RACEID/%s%s00000000'
                      % (ymd, CODE[pl]))
            ids = sorted({z for z in re.findall(r'RACEID/(%s%s\d{8})' % (ymd, CODE[pl]), idx or '')
                          if not z.endswith('00000000')})
            cache[key] = ids
            time.sleep(0.4)
        hit = None
        for rid in cache[key]:
            kk = rid
            if kk not in cache:
                raw = get('https://keiba.rakuten.co.jp/race_performance/list/RACEID/%s' % rid)
                time.sleep(0.4)
                t = flat(raw) if raw else ''
                dm = re.search(r'ダ([\d,]+)m\(([内外])\)', t)
                lm = re.search(r'ハロンタイム\|([\d.\-]+)\|', t)
                fs = len(re.findall(r'\|\d{1,2}\|\d+\|\d+\|[^|]+?\|[牡牝セ]\d', t))
                cache[kk] = dict(dist=int(dm.group(1).replace(',', '')) if dm else 0,
                                 course=dm.group(2) if dm else '',
                                 lap=lm.group(1) if lm else '', fs=fs,
                                 hit=(e['nm'] in t))
            v = cache[kk]
            if v['dist'] == x['dist'] and v['fs'] == x['fs'] and v['lap']:
                hit = v
                break
        if hit:
            sp = shape(hit['lap'])
            print('   %s %s%s%dm %s %2d着/%2d頭 上%.1f'
                  % (x['date'], pl, hit['course'], x['dist'], x['baba'], x['fin'], x['fs'], x['ag']))
            print('         %-46s  形 %+.2f  （今日との差 %.2f）'
                  % (hit['lap'], sp, abs(sp - today)))
        else:
            print('   %s %s%dm %s %2d着/%2d頭 上%.1f  ── 該当鞍を特定できず'
                  % (x['date'], pl, x['dist'], x['baba'], x['fin'], x['fs'], x['ag']))
