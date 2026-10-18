# -*- coding: utf-8 -*-
"""浦和の大穴候補を、検証で残ったファクターだけで拾う。

  python3 scripts/urawa_ana_pick.py <past5.json> <出力txt>

使うもの（すべて人気薄で上振れが出たもの）
  ① 前走が8着以下 かつ 前走の1角が鞍内上位25%   … 大敗したのにテンは取れていた（+1.7pt／10着以下なら+6.9pt）
  ② 近5走の1角位置（頭数比）の中央値が鞍内上位25% … 先行力（+5.3pt）
  ③ 近5走の3角→4角の押し上げが鞍内上位1/3        … コーナー押上（+7.8pt）
     かつ 直線では順位を上げていない
切るもの
  ・近5走で3角→4角を一度も上げていない（角0走）
  ・前走から75日以上あいている
  ・近5走で4角の順位を下げ続けている
"""
import json, sys, statistics, datetime

SRC, OUT = sys.argv[1], sys.argv[2]
d = json.load(open(SRC, encoding='utf-8'))
TODAY = datetime.date(2026, 10, 19)


def ten(run):
    c = (run.get('cor') or '').split('-')
    if not c or not c[0].isdigit() or not run.get('fs'):
        return None
    return int(c[0]) / float(run['fs'])


def cgain(run):
    c = (run.get('cor') or '').split('-')
    if len(c) < 2 or not run.get('fs'):
        return None
    return (int(c[-2]) - int(c[-1])) / float(run['fs'])


def sgain(run):
    if not run.get('fs') or not run.get('c4'):
        return None
    return (run['c4'] - run['fin']) / float(run['fs'])


def days(run):
    try:
        y, m, dd = [int(x) for x in run['date'].split('/')]
        return (TODAY - datetime.date(2000 + y, m, dd)).days
    except Exception:
        return None


O, HON = [], []
P = O.append
P('# 10/19(月) 浦和 ── 大穴の準備')
P('')
P('検証で人気薄の上振れが出たファクターだけで拾っている。印は当日のオッズで7番人気以下に')
P('落ちた馬だけ買う。人気側では同じ箱でも上振れが出ない。')
P('')
P('  ◎ 大敗したのにテンは取れていた（前走8着以下 × 前走1角が鞍内上位25%）')
P('  ○ 先行力（近5走の1角位置の中央値が鞍内上位25%）')
P('  ▲ コーナー押上（近5走の3角→4角の押し上げが鞍内上位1/3・直線では上げない）')
P('  ×  切り（角0走／間隔75日以上／4角で下げ続け）')
P('')

for Rs in sorted(d, key=int):
    r = d[Rs]
    es = r['e']
    for e in es:
        rs = e['runs']
        e['tenm'] = statistics.median([t for t in (ten(x) for x in rs) if t is not None]) \
            if any(ten(x) is not None for x in rs) else None
        cg = [c for c in (cgain(x) for x in rs) if c is not None]
        e['cg'] = statistics.median(cg) if cg else None
        sg = [s for s in (sgain(x) for x in rs) if s is not None]
        e['sg'] = statistics.median(sg) if sg else None
        e['zero'] = bool(cg) and all(c <= 0 for c in cg)
        e['gap'] = days(rs[0]) if rs else None
        p = rs[0] if rs else None
        e['prev'] = p
        e['prevten'] = ten(p) if p else None
        e['big'] = bool(p and p['fin'] >= 8 and e['prevten'] is not None and e['prevten'] < 0.25)
        e['big10'] = bool(p and p['fin'] >= 10 and e['prevten'] is not None and e['prevten'] < 0.25)
    ok = [e for e in es if e['tenm'] is not None]
    if ok:
        q = sorted(e['tenm'] for e in ok)[max(0, len(ok) // 4 - 1)]
        for e in es:
            e['sen'] = e['tenm'] is not None and e['tenm'] <= q
    okc = [e for e in es if e['cg'] is not None]
    if okc:
        qc = sorted((e['cg'] for e in okc), reverse=True)[max(0, len(okc) // 3 - 1)]
        for e in es:
            e['push'] = (e['cg'] is not None and e['cg'] >= qc and e['cg'] > 0
                         and (e['sg'] or 0) <= 0 and not e['zero'])
    P('── %sR ダ%d %d頭 ──' % (Rs, r['dist'], r['n']))
    rows = []
    for e in es:
        mk = ''
        if e.get('big'):
            mk += '◎'
        if e.get('sen'):
            mk += '○'
        if e.get('push'):
            mk += '▲'
        cut = []
        if e['zero']:
            cut.append('角0走')
        if e['gap'] is not None and e['gap'] >= 75:
            cut.append('間隔%d日' % e['gap'])
        if not e['runs']:
            cut.append('近走なし')
        if cut and not mk:
            mk = '×'
        rows.append((mk, e, cut))
    pri = lambda m: (0 if '◎' in m else 1 if '○' in m else 2 if '▲' in m else 3 if m != '×' else 4)
    rows.sort(key=lambda z: (pri(z[0]), z[1]['u']))
    for mk, e, cut in rows:
        if '◎' in mk:
            HON.append((int(Rs), r['dist'], mk, e, cut))
        p = e['prev']
        pv = ('前走 %s%s %d着/%d頭 1角%s' %
              (p['place'], p['date'][3:], p['fin'], p['fs'], (p['cor'] or '').split('-')[0])) if p else '近走なし'
        P('  %-4s %2d %-14s %s%s%s'
          % (mk or '', e['u'], e['nm'][:14], pv,
             ('　テン%.2f' % e['tenm']) if e['tenm'] is not None else '',
             ('　／ ' + '・'.join(cut)) if cut else ''))
    P('')
S = ['## 本線 ── 大敗したのにテンは取れていた馬', '']
for R, dist, mk, e, cut in sorted(HON, key=lambda z: (z[0], z[3]['u'])):
    p0 = e['prev']
    S.append('  %-4s %2dR ダ%d  %2d %-13s  前走 %s%s %d着/%d頭 1角%s（%.2f）%s'
             % (mk, R, dist, e['u'], e['nm'][:13], p0['place'], p0['date'][3:], p0['fin'],
                p0['fs'], (p0['cor'] or '').split('-')[0], e['prevten'],
                ('　／ ' + '・'.join(cut)) if cut else ''))
S += ['', '  ◎○ は先行力も鞍内上位25%。この4頭が本線。', '']
O = O[:10] + S + O[10:]
open(OUT, 'w', encoding='utf-8').write('\n'.join(O))
print(OUT)
