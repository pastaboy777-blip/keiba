"""買う馬リスト ── 過去走を1頭ぶんの物差しにまとめる（shirushi.py の前段）。

  python3 shirushi_prof.py            # <PREF>_card.json + zen_cache.json -> <PREF>_prof.json

入力は出馬表 JSON（[{R, rid, start, dist, cond, rows:[{ub,name,jk,umacd,...}]}]）と
馬ごとの過去走キャッシュ（{umacd: [{date,venue,dist,n,rel,c1,c4,chaku,lane,w,edge}]}）。

★ここが肝（CLAUDE.md「買う馬リストの組み方」）
  上がりも位置も **今日と同じ距離帯で走ったときの走り** からしか取らない。
  800m の上がりを1400mに持ち込むと逃げ馬が◎になる。
  距離帯の実績がない馬は xband=True を立て、shirushi.py 側で上がりを使わない。
"""
# ★距離帯で切る。上がりも位置も、今日と同じ距離帯の走りからだけ取る。
import json

import os
# 作業ディレクトリと日付の接頭辞は環境変数で差し替える
#   SHIRUSHI_DIR=/path SHIRUSHI_PREF=ura1021 python3 shirushi.py 1,2,3 out
S = os.environ.get('SHIRUSHI_DIR', '.').rstrip('/') + '/'
PREF = os.environ.get('SHIRUSHI_PREF', 'ura')
C = json.load(open(S + PREF + '_card.json'))
Z = json.load(open(S + 'zen_cache.json'))


def mean(v):
    v = [x for x in v if x is not None]
    return sum(v) / len(v) if v else None


def band(runs, d):
    """今日の距離帯。800mは〜1000m、それ以外は±200m。"""
    if d <= 1000:
        return [x for x in runs if x['dist'] <= 1000]
    return [x for x in runs if abs(x['dist'] - d) <= 200]


out = {}
for rc in C:
    D = rc['dist']
    rows = []
    for h in rc['rows']:
        allruns = Z.get(h['umacd']) or []
        d = {'ub': h['ub'], 'name': h['name'], 'jk': h['jk'], 'nrun': len(allruns)}
        if allruns:
            last = allruns[-1]
            b = band(allruns, D)[-6:]          # 距離帯の直近6走
            use = b or allruns[-6:]            # 距離帯の経験がなければ全体で代用
            eg = [x['edge'] for x in use if x.get('edge') is not None]
            top3 = [x for x in use if x.get('chaku') and x['chaku'] <= 3]
            ura = [x for x in allruns if '浦和' in (x.get('venue') or '')]
            d.update(
                nband=len(b),
                xband=not b,                   # 距離帯の実績がない
                prel=mean([x.get('rel') for x in use]),
                # 1角→4角でいくつ前へ出たか（昨日の穴の主役はこの形）
                gain=mean([x['c1'] - x['c4'] for x in use
                           if x.get('c1') and x.get('c4')]),
                edge=mean(eg), bedge=min(eg) if eg else None,
                negd=len(eg),                  # 上がりが取れた走の数
                # 上がりが取れない馬（佐賀・金沢・笠松など）の代わりの物差し
                inrate=len(top3) / len(use) if use else None,
                frontwin=sum(1 for x in use
                             if x.get('c4') and x['c4'] <= 3 and x.get('chaku') and x['chaku'] <= 3),
                nuse=len(use),
                # ラチ沿いを走る馬か（照明が入る9R以降で効く、とユーザー）
                inlane=(sum(1 for x in use if x.get('lane') in ('最内', '内'))
                        / sum(1 for x in use if x.get('lane'))
                        if any(x.get('lane') for x in use) else None),
                nlane=sum(1 for x in use if x.get('lane')),
                pchaku=last.get('chaku'), pn=last.get('n'),
                pw=last.get('w'), pdate=last.get('date'), pdist=last.get('dist'),
                urel=mean([x.get('rel') for x in ura]), un=len(ura))
        rows.append(d)
    out[str(rc['R'])] = dict(dist=D, start=rc['start'], cond=rc['cond'],
                             n=len(rc['rows']), rows=rows)

json.dump(out, open(S + PREF + '_prof.json', 'w'), ensure_ascii=False)
for R in sorted(out, key=int):
    v = out[R]
    hv = [r for r in v['rows'] if r.get('prel') is not None]
    print('%2sR %4dm %2d頭  距離帯の実績あり %2d / 上がりが取れる %2d'
          % (R, v['dist'], v['n'],
             sum(1 for r in hv if not r['xband']),
             sum(1 for r in hv if r.get('edge') is not None)))
