# -*- coding: utf-8 -*-
"""調教を測る ── 総評の文字と、その日の追い切り順位。

  python3 scripts/ana/chokyo_rank.py

手元の調教は大井(10/4〜9)と浦和(10/19〜23)の124鞍・1,375頭だけ。
競馬ブックから取ったもので、数値はカードに転載しない。

【① 総評の文字】ほぼ人気の言い換えだった
全馬1,359頭（層27.2%・複勝の回収70%）
  仕上がり良好 50.0%（28頭）／ 好調持続 39.5%（38頭）
  平凡な動き 14.7%（34頭）／ 上がりに重点置く 16.0%（25頭）
大きく割れて見えるが、平均人気を並べると理由が分かる。
  仕上がり良好 2.8番人気 ／ 好調持続 4.0 ／ 平凡な動き 8.9
人気薄だけにすると消える。
  追切り手控え +0.8pt ／ 平凡な動き +1.2pt ／ 連闘のため軽め -1.5pt

【② その日の追い切り順位】場をまたいで再現しない
最後の追い切りの上がり時計を、同じ日・同じコース・同じ馬場・同じ
本数の馬の中で順位にする（同点は乱数で崩す）。
  大井 全馬527頭（層29.4%）上位1/3 35.4%・回収83% ／ 下位1/3 25.3%・60%
  浦和 全馬353頭（層28.3%）上位1/3 29.5% ／ 中1/3 30.8% ／ 下位1/3 24.8%
大井できれいに出た勾配が、浦和では +1.1pt に落ちて順序も崩れる。

人気薄ではどちらも立たない。
  大井 277頭 上位1/3 11.1%・中1/3 10.0%・下位1/3 11.3%（層10.8%）
  浦和 179頭 上位1/3 18.2%・中1/3  5.9%・下位1/3 11.3%（層12.3%・66頭）
帯ごとの平均人気はそろっている（大井 9.1／8.7／9.0）ので、構成の差ではなく
単に効いていない。

【結論】
全馬で見ると見栄えがするが、それは平均人気5.9の層で人気馬を当てている
だけ。人気薄に絞ると消える。買う材料としては使えない。
"""
import glob
import json
import random
import statistics as st
from collections import Counter, defaultdict

SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
CH = {}
for f in sorted(glob.glob('data/samples/keibabook_chokyo_*.jsonl')):
    for l in open(f, encoding='utf-8'):
        v = json.loads(l)
        for h in v['horses']:
            CH[(v['date'], v['place'], v['race_no'], h['馬名'])] = h
R = [json.loads(l) for l in open(f'{SP}/nankan_2026.jsonl', encoding='utf-8')]
DIV = json.load(open(f'{SP}/div_year.json', encoding='utf-8'))

# その日の追い切り順位（同じ日・コース・馬場・本数の中で）
day = defaultdict(list)
for (d, pl, rn, nm), h in CH.items():
    f = next((a for a in (h.get('追切') or []) if a.get('時計')), None)
    if not f:
        continue
    try:
        ag = float(f['時計'][-1])
    except Exception:
        continue
    day[(d, pl, f.get('コース', ''), f.get('馬場', ''), len(f['時計']))].append(
        (nm, rn, ag))
rnd = random.Random(3)
rk = {}
for k, v in day.items():
    if len(v) < 5:
        continue
    w = rnd.sample(v, len(v))
    w.sort(key=lambda x: x[2])
    for i, (nm, rn, ag) in enumerate(w):
        rk[(k[0], k[1], rn, nm)] = (i + 1, len(w))

rows = []
for r in R:
    fk = dict((DIV.get(r['ymd'], {}).get(str(r['R']), {})).get('複勝', [])) \
        if r['ba'] == '大井' else {}
    for e in r['e']:
        k = (r['ymd'], r['ba'], r['R'], e['nm'])
        if k not in CH or not e.get('f', '').isdigit():
            continue
        pop = e.get('pop', '')
        i, n = rk.get(k, (None, None))
        rows.append(dict(ba=r['ba'], hit=int(e['f']) <= 3,
                         s=CH[k].get('総評', '') or '',
                         rel=(i - 1) / max(1, n - 1) if i else None,
                         pop=int(pop) if pop.isdigit() else None,
                         fuku=fk.get(str(int(e['u'])), 0), has=bool(fk)))

print('■ 総評の文字（平均人気を並べる）')
g = defaultdict(list)
for x in rows:
    if x['pop']:
        g[x['s']].append(x)
for s, v in sorted(g.items(), key=lambda y: -len(y[1]))[:10]:
    if len(v) < 25:
        continue
    print(f"   {s or '（空）':<14}{len(v):>4}頭  平均人気 "
          f"{st.mean(x['pop'] for x in v):4.1f}"
          f"  3着内 {100*sum(x['hit'] for x in v)/len(v):5.1f}%")


def blk(lab, S):
    S = [x for x in S if x['rel'] is not None]
    if len(S) < 60:
        print(f'\n■ {lab} 材料不足({len(S)})')
        return
    b = 100 * sum(x['hit'] for x in S) / len(S)
    d = [x for x in S if x['has']]
    print(f"\n■ {lab} {len(S)}頭 3着内 {b:.1f}%"
          f"{'  回収'+format(sum(x['fuku'] for x in d)/len(d),'.0f')+'%' if d else ''}")
    for lo, hi, t in ((0, .34, '上位1/3'), (.34, .67, '中1/3'),
                      (.67, 1.01, '下位1/3')):
        v = [x for x in S if lo <= x['rel'] < hi]
        if len(v) < 20:
            print(f'   {t:<10} 材料不足({len(v)})')
            continue
        dd = [x for x in v if x['has']]
        pp = [x['pop'] for x in v if x['pop']]
        print(f"   {t:<10}{len(v):>4}頭 "
              f"{100*sum(x['hit'] for x in v)/len(v):5.1f}%"
              f"  回収{sum(x['fuku'] for x in dd)/len(dd) if dd else 0:5.0f}%"
              f"  平均人気{st.mean(pp):4.1f}"
              f" {100*sum(x['hit'] for x in v)/len(v)-b:+5.1f}pt")


print('\n──── その日の追い切り順位 ────')
blk('大井 全馬', [x for x in rows if x['ba'] == '大井'])
blk('浦和 全馬', [x for x in rows if x['ba'] == '浦和'])
blk('大井 人気薄', [x for x in rows if x['ba'] == '大井'
                 and x['pop'] and x['pop'] >= 6])
blk('浦和 人気薄', [x for x in rows if x['ba'] == '浦和'
                 and x['pop'] and x['pop'] >= 6])
