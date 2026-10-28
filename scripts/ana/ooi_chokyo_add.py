# -*- coding: utf-8 -*-
"""調教が、いま持っている3条件に何か足すのかを大井で測る。

  python3 scripts/ana/ooi_chokyo_add.py

材料は data/samples/keibabook_chokyo_ooi_*.jsonl（有料サイト。gitignore）。
個々の数値は出さず、まとめた割合だけを見る。

見るのは4つ。
  追切なし / 最終追いが直前（3日以内）/ 終いの脚色 / 本数
それぞれ単独と、3条件（上がりがそろう・ふだん前め・下げない）に
足したときの3着内率と複勝の回収率。
"""
import glob, json, os, re, statistics as st
from collections import defaultdict

SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
WET = ('重', '不良')


def band(d):
    return 'S' if d <= 1300 else 'M' if d <= 1700 else 'L'


# ── 調教を 馬名＋日付 で引けるようにする ─────────────────────
CH = {}
for fn in sorted(glob.glob('data/samples/keibabook_chokyo_ooi_*.jsonl')):
    for l in open(fn, encoding='utf-8'):
        r = json.loads(l)
        for h in r.get('horses') or []:
            oi = h.get('追切') or []
            # 追日は MM/DD。レース日との差（日数）のいちばん小さいもの
            gap = None
            for o in oi:
                m = re.match(r'^(\d\d)/(\d\d)$', o.get('追日') or '')
                if not m:
                    continue
                y = int(r['date'][:4])
                mm, dd = int(m.group(1)), int(m.group(2))
                import datetime as dt
                try:
                    d0 = dt.date(y, mm, dd)
                    d1 = dt.date(int(r['date'][:4]), int(r['date'][4:6]),
                                 int(r['date'][6:]))
                except ValueError:
                    continue
                g = (d1 - d0).days
                if 0 <= g <= 30 and (gap is None or g < gap):
                    gap = g
            last = oi[0] if oi else None
            CH[(r['date'], h['馬名'])] = dict(
                n=len(oi), gap=gap,
                ashi=(last or {}).get('脚色') or '',
                shiagari=h.get('仕上がり'))

print(f'調教が取れている {len(CH)}頭ぶん '
      f'（{len(set(k[0] for k in CH))}日）')

# ── 結果と、3条件 ───────────────────────────────────
DIV = json.load(open(f'{SP}/div_year.json', encoding='utf-8'))
CN = {}
for l in open(f'{SP}/corners_2026.jsonl', encoding='utf-8'):
    v = json.loads(l)
    CN[v['rid']] = v
R2 = []
for l in open(f'{SP}/ooi_2026_runs.jsonl', encoding='utf-8'):
    r = json.loads(l)
    if r.get('dist') and r.get('e'):
        R2.append(r)
R2.sort(key=lambda r: (r.get('ymd') or '', r['rid']))

AG, POS, GAIN = defaultdict(list), defaultdict(list), defaultdict(list)
ROWS = []
for r in R2:
    d = r['dist']
    cn = CN.get(r['rid']) or {}
    c3, c4 = cn.get('c3') or [], cn.get('c4') or []
    i3 = {u: i + 1 for i, u in enumerate(c3)}
    i4 = {u: i + 1 for i, u in enumerate(c4)}
    fuku = dict((DIV.get(r['ymd'], {}).get(str(int(r['rid'][-2:])), {})
                 ).get('複勝', []))
    for e in r['e']:
        if not e.get('f', '').isdigit():
            continue
        nm = e['nm']
        ch = CH.get((r['ymd'], nm))
        if ch:
            pa = [a for dd, a in AG[nm] if band(dd) == band(d)][-5:]
            pp, pg = POS[nm][-5:], GAIN[nm][-5:]
            pop = e.get('pop', '')
            ROWS.append(dict(
                hit=int(e['f']) <= 3, fuku=fuku.get(str(int(e['u'])), 0),
                pop=int(pop) if pop.isdigit() else None,
                sd=st.pstdev(pa) if len(pa) >= 4 else None,
                pos=st.median(pp) if len(pp) >= 3 else None,
                gain=st.median(pg) if len(pg) >= 3 else None,
                wet=r.get('baba') in WET, **ch))
    for e in r['e']:
        nm = e['nm']
        if re.match(r'^\d+\.\d$', e.get('ag') or ''):
            AG[nm].append((d, float(e['ag'])))
        p4, p3 = i4.get(int(e['u'])), i3.get(int(e['u']))
        if p4 and len(c4):
            POS[nm].append(p4)
        if p4 and p3:
            GAIN[nm].append(p3 - p4)

P = [x for x in ROWS if x['pop'] and x['pop'] >= 6]
print(f'結果とつながった {len(ROWS)}頭 / 人気薄 {len(P)}頭')
if not P:
    raise SystemExit('つながらなかった')
print(f'この6日の人気薄  3着内 {100*sum(x["hit"] for x in P)/len(P):.1f}%  '
      f'回収 {sum(x["fuku"] for x in P)/len(P):.0f}%\n')


def show(lab, f, base=P, mn=25):
    v = [x for x in base if f(x)]
    if len(v) < mn:
        print(f'  {lab:<26} 材料不足（{len(v)}頭）')
        return
    i = sum(x['hit'] for x in v)
    print(f'  {lab:<26} {100*i/len(v):5.1f}%  回収 {sum(x["fuku"] for x in v)/len(v):5.0f}%  '
          f'({i}/{len(v)})')


print('■ 調教だけで見る（人気薄）')
show('追い切りなし', lambda x: x['n'] == 0)
show('最終追いが3日以内', lambda x: x['gap'] is not None and x['gap'] <= 3)
show('最終追いが4〜7日', lambda x: x['gap'] is not None and 4 <= x['gap'] <= 7)
show('最終追いが8日以上', lambda x: x['gap'] is not None and x['gap'] >= 8)
show('終い 一杯', lambda x: x['ashi'] == '一杯')
show('終い 強め', lambda x: x['ashi'] == '強め')
show('終い 馬なり', lambda x: x['ashi'] == '馬なり')
show('追い 3本以上', lambda x: x['n'] >= 3)

sg = [x['shiagari'] for x in P if x['shiagari'] is not None]
if len(sg) >= 50:
    m = st.median(sg)
    print(f'\n  （競馬ブックの仕上がり指数の中央 {m:.2f}）')
    show('仕上がり 上半分', lambda x: x['shiagari'] is not None and x['shiagari'] > m)
    show('仕上がり 下半分', lambda x: x['shiagari'] is not None and x['shiagari'] <= m)

A = lambda x: x['sd'] is not None and x['sd'] < 0.6
B = lambda x: x['pos'] is not None and x['pos'] <= 7
C = lambda x: x['gain'] is not None and x['gain'] > -0.5
OK = lambda x: A(x) and B(x) and C(x)

print('\n■ 3条件に足すと（人気薄）')
show('3条件だけ', OK, mn=15)
show('3条件 × 追い切りあり', lambda x: OK(x) and x['n'] > 0, mn=15)
show('3条件 × 直前追いでない', lambda x: OK(x) and (x['gap'] is None or x['gap'] >= 4),
     mn=15)
show('3条件 × 終い馬なり', lambda x: OK(x) and x['ashi'] == '馬なり', mn=10)
show('3条件 × 終い追った', lambda x: OK(x) and x['ashi'] in ('一杯', '強め'), mn=10)

print('\n■ 消しに使えるか（3条件を満たさない馬のなかで）')
NG = lambda x: not OK(x)
show('3条件なし × 追い切りなし', lambda x: NG(x) and x['n'] == 0)
show('3条件なし × 直前追い', lambda x: NG(x) and x['gap'] is not None and x['gap'] <= 3)
show('3条件なし × ふつう', lambda x: NG(x) and x['n'] > 0
     and (x['gap'] is None or x['gap'] >= 4))
