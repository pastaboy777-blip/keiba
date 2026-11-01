# -*- coding: utf-8 -*-
"""大井の「休み明け」と「転入初戦」を測る。

  python3 scripts/ana/ooi_gap.py

直感と逆だった。詰めて使っている馬がいちばん走らない。

大井ぜんぶ 11,208頭（層25.4%・複勝の回収69%）
  中14日以内      21.5%・回収64%（-3.9pt）
  中15〜35日      22.8%・回収69%（-2.6pt） ← ふつうの間隔がいちばん下
  中36〜70日      33.5%・回収75%（+8.1pt）
  中71〜120日     33.3%・回収85%（+7.9pt）
  中121日以上     32.0%・回収81%（+6.6pt）
  転入初戦        32.0%・回収67%（+6.6pt）

人気上位（1〜3番人気）2,834頭（層59.1%・回収82%）
  中71〜120日 62.1%・回収88% ／ 中121日以上 63.5%・回収102%
  転入初戦 62.2%・回収84%
長い休み明けは減点ではなく加点。ただし回収は84〜88%で、控除率から見た
基準75%は上回るが100%には届かない。市場もこのパターンを知っている。

人気薄（6番人気以降）6,483頭（層9.0%・回収61%）
  中71〜120日 11.2%・回収78%（+2.2pt）が最良だが160頭と少ない。
  人気薄では効き目が小さい。
"""
import datetime as dt
import json

SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
R = [json.loads(l) for l in open(f'{SP}/nankan_2026.jsonl', encoding='utf-8')]
R.sort(key=lambda r: (r['ymd'], r['rid']))
DIV = json.load(open(f'{SP}/div_year.json', encoding='utf-8'))

LAST, P = {}, []
for r in R:
    fk = dict((DIV.get(r['ymd'], {}).get(str(r['R']), {})).get('複勝', [])) \
        if r['ba'] == '大井' else {}
    for e in r['e']:
        if not e.get('f', '').isdigit():
            continue
        nm = e['nm']
        pv = LAST.get(nm)
        gap = None
        if pv:
            a = dt.date(int(pv[:4]), int(pv[4:6]), int(pv[6:]))
            b = dt.date(int(r['ymd'][:4]), int(r['ymd'][4:6]),
                        int(r['ymd'][6:]))
            gap = (b - a).days
        if r['ba'] == '大井':
            pop = e.get('pop', '')
            P.append(dict(hit=int(e['f']) <= 3,
                          pop=int(pop) if pop.isdigit() else None, gap=gap,
                          fuku=fk.get(str(int(e['u'])), 0), has=bool(fk)))
        LAST[nm] = r['ymd']


def blk(lab, S):
    base = 100 * sum(x['hit'] for x in S) / len(S)
    d = [x for x in S if x['has']]
    print(f'\n■ {lab}　{len(S)}頭　3着内 {base:.1f}%　'
          f'複勝の回収 {sum(x["fuku"] for x in d)/len(d) if d else 0:.0f}%')

    def sh(t, f, mn=60):
        v = [x for x in S if f(x)]
        if len(v) < mn:
            print(f'    {t:<26} 材料不足({len(v)})')
            return
        i = sum(x['hit'] for x in v)
        dd = [x for x in v if x['has']]
        print(f'    {t:<26}{len(v):>5}頭 {100*i/len(v):5.1f}%'
              f'  回収{sum(x["fuku"] for x in dd)/len(dd) if dd else 0:5.0f}%'
              f' {100*i/len(v)-base:+5.1f}pt')

    sh('南関での走りなし（転入初戦）', lambda x: x['gap'] is None)
    for lo, hi, t in ((0, 14, '中14日以内'), (15, 35, '中15〜35日'),
                      (36, 70, '中36〜70日'), (71, 120, '中71〜120日'),
                      (121, 999, '中121日以上')):
        sh(t, lambda x, A=lo, B=hi: x['gap'] is not None and A <= x['gap'] <= B)


blk('大井ぜんぶ', P)
blk('大井の人気薄（6番人気以降）', [x for x in P if x['pop'] and x['pop'] >= 6])
blk('大井の人気上位（1〜3番人気）', [x for x in P if x['pop'] and x['pop'] <= 3])
