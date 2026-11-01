# -*- coding: utf-8 -*-
"""展開上の立ち位置 ── 自分より前に行く馬が何頭いるか。

  python3 scripts/ana/shape_rel.py [場名]

能力の絶対値はもう値段に入っている（今日のレーティングが3着内率を層の
2.3倍にしても回収75%で止まった。南関の払戻率と同じ）。
効くとすれば、そのレースのメンバー構成でしか決まらないもの。

同じ「ふだん4角3番手の馬」でも
  前に行く馬が自分だけの鞍
  前に行く馬が5頭いる鞍
ではまったく別の競馬になる。能力は同じでも結果が変わる。
世間は「逃げ馬が1頭」くらいは見るが、馬ごとに「自分より前に行く馬が
何頭か」を数えてはいない。

  その馬のふだんの4角位置 ＝ 近5走の4角位置（頭数で割った割合）の中央値
  前にいる馬の数         ＝ 今日の出走馬のうち、それが自分より小さい馬の数
  相対の立ち位置         ＝ 前にいる馬の数 ÷（出走頭数 − 1）

すべて前日に分かる。同点は乱数で崩す（着順が漏れるのを防ぐ）。
前半で見つけて後半で確かめる。

【結果：期間を分けても残った】人気薄（近3走以上そろう馬）
  前に行く馬の数   前半（層10.4%・回収72%）   後半（層9.4%・63%）
    0頭          13.3%・回収77%            7.5%・回収35%
    1頭          16.2%・回収96%           16.8%・回収113%
    2頭          13.8%・83%               12.2%・51%
    3頭以上        9.2%・68%                8.7%・62%
最先頭になる馬は良くない。2番手につける馬が良い。
さらに「ふだん前に行くタイプ × 前に1頭」で 前半15.4%・95%／後半21.7%・150%。

【場ごと】3場で出る。浦和だけ出ない。
  船橋 19.3%（層11.4%）回収111%（幅76〜153%）
  大井 14.9%（層 9.1%）回収102%（幅68〜134%）
  川崎 16.1%（層11.3%）
  浦和 11.7%（層12.2%）… 効かない
回収の幅が広いので100%超えは言い切れない。3着内率のほうは残る。

【1着率では逆になる】
  前に0頭  1着2.5%・3着内11.6%
  前に1頭  1着1.6%・3着内15.5%
  前に3頭以上 1着1.9%・3着内 9.9%
最先頭は勝つか沈むか。2番手は勝ち切らないが堅実に3着内に来る。
複勝なら2番手、単勝なら最先頭という使い分けになる。

【なぜ能力では出てこないか】
同じ「ふだん4角3番手の馬」でも、前に行く馬が自分だけの鞍と5頭いる鞍では
別の競馬になる。メンバー構成でしか決まらないので、能力の絶対値を
いくら磨いても出てこない。今日のレーティングが3着内率を層の2.3倍まで
上げても回収75%で止まったのと対になる結果。
"""
import json, random, statistics as st, sys
from collections import defaultdict

BA = sys.argv[1] if len(sys.argv) > 1 else None
SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
CUT = '20260701'
DIVF = {'船橋': 'div_funabashi.json', '大井': 'div_year.json'}

R = [json.loads(l) for l in open(f'{SP}/nankan_2026.jsonl', encoding='utf-8')]
R.sort(key=lambda r: (r['ymd'], r['rid']))
D = {}
for ba, fn in DIVF.items():
    try:
        D[ba] = json.load(open(f'{SP}/{fn}', encoding='utf-8'))
    except Exception:
        pass

HIST = defaultdict(list)
ROWS = []
rnd = random.Random(3)
for r in R:
    n = len([e for e in r['e'] if e.get('f', '').isdigit()])
    fk = dict((D.get(r['ba'], {}).get(r['ymd'], {})
               .get(str(r['R']), {})).get('複勝', []))
    # 出走馬それぞれの「ふだんの4角位置」
    cur = {}
    for e in r['e']:
        v = [p for y, p in HIST.get(e['nm'], []) if y < r['ymd']][-5:]
        if len(v) >= 3:
            cur[e['nm']] = st.median(v)
    if len(cur) >= 6 and fk:
        vals = sorted(cur.values())
        for e in r['e']:
            nm = e['nm']
            if not e.get('f', '').isdigit() or nm not in cur:
                continue
            me = cur[nm]
            ahead = sum(1 for x in cur.values() if x < me)
            pop = e.get('pop', '')
            ROWS.append(dict(
                ba=r['ba'], ymd=r['ymd'], dist=r['dist'], n=n,
                hit=int(e['f']) <= 3,
                pop=int(pop) if pop.isdigit() else None,
                me=me, ahead=ahead, k=len(cur),
                rel=ahead / max(1, len(cur) - 1),
                fuku=fk.get(str(int(e['u'])), 0)))
    i4 = {u: (i + 1) / len(r.get('c4') or [1])
          for i, u in enumerate(r.get('c4') or [])}
    for e in r['e']:
        if int(e['u']) in i4:
            HIST[e['nm']].append((r['ymd'], i4[int(e['u'])]))

P = [x for x in ROWS if x['pop'] and x['pop'] >= 6 and (not BA or x['ba'] == BA)]
print(f'人気薄で近3走以上そろう {len(P)}頭\n')


def blk(lab, S):
    if len(S) < 400:
        print(f'■ {lab} 材料不足（{len(S)}頭）\n')
        return
    base = 100 * sum(x['hit'] for x in S) / len(S)
    print(f'■ {lab}　{len(S)}頭　3着内 {base:.1f}%　'
          f'複勝の回収 {sum(x["fuku"] for x in S)/len(S):.0f}%')

    def sh(t, f, mn=60):
        v = [x for x in S if f(x)]
        if len(v) < mn:
            print(f'    {t:<26} 材料不足({len(v)})')
            return
        i = sum(x['hit'] for x in v)
        print(f'    {t:<26}{len(v):>5}頭 {100*i/len(v):5.1f}%'
              f'  回収{sum(x["fuku"] for x in v)/len(v):5.0f}%'
              f' {100*i/len(v)-base:+5.1f}pt')
    print('  〈自分より前に行く馬が何頭いるか〉')
    for a in (0, 1, 2, 3):
        sh(f'{a}頭' if a < 3 else '3頭以上',
           lambda x, A=a: x['ahead'] == A if A < 3 else x['ahead'] >= A)
    print('  〈ふだんの位置と組み合わせる〉')
    sh('前に行く馬（ふだん前1/3）× 前に0頭',
       lambda x: x['me'] <= 1/3 and x['ahead'] == 0)
    sh('前に行く馬 × 前に1頭',
       lambda x: x['me'] <= 1/3 and x['ahead'] == 1)
    sh('前に行く馬 × 前に3頭以上',
       lambda x: x['me'] <= 1/3 and x['ahead'] >= 3)
    sh('後ろの馬（ふだん後1/3）× 前が多い(5頭以上)',
       lambda x: x['me'] > 2/3 and x['ahead'] >= 5)
    sh('後ろの馬 × 前が少ない(2頭以下)',
       lambda x: x['me'] > 2/3 and x['ahead'] <= 2)
    print()


blk('ぜんぶ', P)
blk('前半（7月より前）', [x for x in P if x['ymd'] < CUT])
blk('後半（7月以降）', [x for x in P if x['ymd'] >= CUT])
