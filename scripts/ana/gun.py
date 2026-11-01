# -*- coding: utf-8 -*-
"""板の「群」の定義を測る。

  python3 scripts/ana/gun.py [場名...]

ユーザーの板の組み方
  STEP1 「4角で前にいる群」を決める
        前半速度が鞍内の中央値以上 かつ 近走の4角位置が前め
  STEP2 その群の中だけで、終い速度の高い順に印
  STEP3 群の外は、終い速度が鞍内1位でも上に置かない

測るのは3つ。
  ① 群に入ること自体が効くか
  ② 群の中で終い1位が効くか
  ③ 群の外の終い1位は本当に買えないか（STEP3の主張）

4角位置は括弧を同順位にして (順位−1)÷(頭数−1)。0が先頭。
同じ距離帯の走だけ使う版と、全部使う版を並べる。

【最初の版は漏れていた】
「終い鞍内1位」を今日のレースの上がり3Fから計算していた。レースが
終わらないと分からない数字。39.0%・回収230%という数字が出たのはこれ。
CLAUDE.md の「そのレースでの動きと過去走の動きを混同しない」を踏んだ。
前半・終い・4角のすべてを過去走から取り、終いの順位は今日の出走馬の
中でつけるのが正しい。板のほうは過去走の速度を使っていて正しかった。

【直したあとの結果】人気薄3,262頭（層9.8%・複勝の回収66%）
  ① 群に入る                    676頭 11.7%・回収74%（+1.9pt）
     群の外                   2,586頭  9.3%・回収64%
  ② 群の中 × 終い鞍内1位             6頭 … 構造的にほとんど起きない
  ③ 群の外 × 終い鞍内1位（STEP3）    257頭 16.0%・回収65%（+6.2pt）
     終い鞍内1位ぜんぶ              263頭 15.6%・回収64%

STEP3（群の外は終い1位でも上に置かない）は的中率では逆を向く。
群の11.7%に対して、群の外の終い1位は16.0%。
ただし回収は群74%・終い1位65%で逆。
  群に入る馬   当たりにくいが配当がつく（人気が落ちている）
  終いが速い馬  当たるが配当が薄い（市場が知っている）
STEP3は的中率を捨てて回収率を取る設計になっている。

②が6頭しかないのは、前に行く馬が同時に終い最速になることが構造的に
ほとんどないから。板の◎は「群の中での終い1位」で、これとは別物。
"""
import json, random, re, statistics as st, sys
from collections import defaultdict

BA = sys.argv[1:] or ['船橋', '大井']
SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
DIVF = {'船橋': 'div_funabashi.json', '大井': 'div_year.json'}
CM = {}
for l in open(f'{SP}/corners_margin.jsonl', encoding='utf-8'):
    v = json.loads(l)
    CM[v['rid']] = v


def tied(s):
    if not s:
        return None
    out, k = {}, 0
    for t in re.findall(r'\((?:\d+,?)+\)|\d+', s):
        k += 1
        for u in re.findall(r'\d+', t):
            out[int(u)] = k
    return out or None


def sec(t):
    m = re.match(r'^(?:(\d+):)?(\d+)\.(\d)$', t.strip()) if t else None
    return None if not m else int(m.group(1) or 0) * 60 + int(m.group(2)) \
        + int(m.group(3)) / 10


def band(d):
    return '短' if d and d <= 1400 else '長'


R = [json.loads(l) for l in open(f'{SP}/nankan_2026.jsonl', encoding='utf-8')]
R.sort(key=lambda r: (r['ymd'], r['rid']))
D = {}
for ba, fn in DIVF.items():
    try:
        D[ba] = json.load(open(f'{SP}/{fn}', encoding='utf-8'))
    except Exception:
        pass

H = defaultdict(list)          # 馬 -> (ymd, 帯, 前半差, 終い速度, 4角位置)
ROWS = []
for r in R:
    t4 = tied((CM.get(r['rid']) or {}).get('c4s'))
    v = []
    for e in r['e']:
        tm, ag = sec(e.get('tm')), sec(e.get('ag') or '')
        if tm is None or ag is None or ag <= 0 or not r.get('dist') or tm <= ag:
            continue
        v.append((e['nm'], int(e['u']), (r['dist'] - 600) / (tm - ag), 600 / ag))
    if r['ba'] in BA and len(v) >= 6 and t4:
        med = st.median([x[2] for x in v])
        fk = dict((D.get(r['ba'], {}).get(r['ymd'], {})
                   .get(str(r['R']), {})).get('複勝', []))
        cur = {}
        for nm, u, ef, el in v:
            p = [x for x in H.get(nm, []) if x[0] < r['ymd']]
            for lab, q in (('all', p[-5:]),
                           ('band', [x for x in p
                                     if x[1] == band(r['dist'])][-5:])):
                if len(q) >= 3:
                    cur.setdefault(nm, {})[lab] = (
                        st.median(x[2] for x in q), st.median(x[4] for x in q))
        if len(cur) >= 6:
            el_rank = {}
            w = sorted(v, key=lambda x: -x[3])
            for i, x in enumerate(w):
                el_rank[x[0]] = i + 1
            for nm, u, ef, el in v:
                e = next((y for y in r['e'] if y['nm'] == nm), None)
                if not e or not e.get('f', '').isdigit() or nm not in cur:
                    continue
                pop = e.get('pop', '')
                row = dict(hit=int(e['f']) <= 3,
                           pop=int(pop) if pop.isdigit() else None,
                           el1=(el_rank[nm] == 1),
                           fuku=fk.get(str(u), 0), has=bool(fk))
                for lab in ('all', 'band'):
                    if lab in cur[nm]:
                        pe, p4 = cur[nm][lab]
                        row[f'gun_{lab}'] = (pe >= 0) and (p4 <= 1 / 3)
                ROWS.append(row)
    # 履歴
    if t4 and v:
        med = st.median([x[2] for x in v])
        mx = max(t4.values())
        for nm, u, ef, el in v:
            if u in t4:
                H[nm].append((r['ymd'], band(r['dist']), ef - med, el,
                              (t4[u] - 1) / max(1, mx - 1)))

P = [x for x in ROWS if x['pop'] and x['pop'] >= 6]
base = 100 * sum(x['hit'] for x in P) / len(P)
d = [x for x in P if x['has']]
print(f'■ 人気薄 {len(P)}頭　3着内 {base:.1f}%　'
      f'複勝の回収 {sum(x["fuku"] for x in d)/len(d):.0f}%\n')


def sh(lab, f, mn=60):
    v = [x for x in P if f(x)]
    if len(v) < mn:
        print(f'    {lab:<34} 材料不足({len(v)})')
        return
    i = sum(x['hit'] for x in v)
    dd = [x for x in v if x['has']]
    print(f'    {lab:<34}{len(v):>5}頭 {100*i/len(v):5.1f}%'
          f'  回収{sum(x["fuku"] for x in dd)/len(dd) if dd else 0:5.0f}%'
          f' {100*i/len(v)-base:+5.1f}pt')


for lab, key in (('近5走ぜんぶ使う', 'gun_all'),
                 ('同じ距離帯の走だけ使う', 'gun_band')):
    print(f'  〈{lab}〉')
    sh('① 群に入る（前半≥中央値 かつ 4角前1/3）',
       lambda x, K=key: x.get(K) is True)
    sh('   群の外', lambda x, K=key: x.get(K) is False)
    sh('② 群の中 × 終い鞍内1位',
       lambda x, K=key: x.get(K) is True and x['el1'], mn=25)
    sh('③ 群の外 × 終い鞍内1位（STEP3）',
       lambda x, K=key: x.get(K) is False and x['el1'], mn=25)
    print()
