# -*- coding: utf-8 -*-
"""大井の開催前の準備シート。

  python3 scripts/ana/ooi_prep.py <card.json> <out.md>

前開催（10/4〜10/9・64鞍712頭）の実測から出た材料だけを当てはめる。
  位置 … 4角1〜3番手は人気薄でも +9〜15pt、5番手以降で落ち、10番手以降は全滅
  母父 … 浦和と大井で向きが揃ったものだけ
  父  … AEI/CPI（能力）と上振れ（市場との差）がズレている銘柄
印は材料の有無だけで、買えという意味ではない。
"""
import html, json, glob, sys, collections

CARD, OUT = sys.argv[1], sys.argv[2]
SP = '/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/scratchpad'

# 浦和と大井で向きが揃った母父（notes/pedigree_nankan.md §10・§11）
BMS_BUY = {'ハーツクライ': '+12.6/+8.3', 'ブライアンズタイム': '+9.0/+18.0',
           'マンハッタンカフェ': '+13/+14', 'サウスヴィグラス': '+5/+15',
           'フレンチデピュティ': '+5/+14', 'ロードカナロア': '+11/+7',
           'ネオユニヴァース': '+7.2'}
BMS_CUT = {'ゼンノロブロイ': '-19.2/-15.5', 'クロフネ': '-11.0/-10.9',
           'フジキセキ': '-15.2/-11.9', 'スペシャルウィーク': '-14/-10',
           'ダイワメジャー': '-19/-5', 'エンパイアメーカー': '-6/-8',
           'アグネスタキオン': '-8.6', 'ジャングルポケット': '-11/-3'}
# AEI/CPI（能力）と南関の上振れ（市場との差）がズレている父
SIRE_BUY = {'キンシャサノキセキ': '+12.9', 'バンブーエール': '+9.3', 'モーニン': '+9.1',
            'ゴールドドリーム': '+4.4', 'ヘニーヒューズ': '+3.7', 'コパノリッキー': '+13/+16',
            'アジアエクスプレス': '+14/+10', 'ダノンレジェンド': '+5/+9'}
SIRE_CUT = {'リアルスティール': '-12.4', 'スワーヴリチャード': '-5.9', 'ドレフォン': '-5.2',
            'ミスターメロディ': '-5.0', 'シニスターミニスター': '-2.9',
            'オルフェーヴル': '-23', 'シルバーステート': '-13'}

ped = {}
import os
for _f in ('ped2026.jsonl', 'ped_extra.jsonl'):   # 前開催ぶん＋前走日から足したぶん
  if not os.path.exists(SP + '/' + _f):
    continue
  for l in open(SP + '/' + _f, encoding='utf-8'):
    x = json.loads(l)
    ped[html.unescape(x['nm'])] = {k: (html.unescape(v) if isinstance(v, str) else v)
                                   for k, v in x.items()}

# 前開催の大井（10/4〜10/9）
prev = {}
for p in sorted(glob.glob('notes/live/2026-10-0*/results.json')):
    d = p.split('/')[2]
    for Rs, r in json.load(open(p, encoding='utf-8')).items():
        if str(r.get('rid', ''))[8:10] != '20':
            continue
        for e in r['e']:
            if not str(e.get('f', '')).isdigit():
                continue
            prev[e['nm']] = dict(d=d[5:], R=int(Rs), dist=r['dist'], f=int(e['f']),
                                 pop=int(e['pop']), c4=e.get('c4'))

C = json.load(open(CARD, encoding='utf-8'))
o = []
o.append('# 大井 2026/10/26 ── 準備シート\n')
o.append('前開催（10/4〜10/9・64鞍712頭）の実測から出た材料だけを当てはめたもの。')
o.append('印は材料の有無で、買い推奨ではない。母父が取れていない馬は空欄。\n')
o.append('**位置** … 4角1番手 57%(+14.7pt)／2番手 53%／4番手 48%／5番手 24%／10番手以降 2/115。')
o.append('7番人気以下でも 1番手 24%(+15.1pt)・2番手 20%・3番手 15%(+9.2pt)。\n')

cnt = collections.Counter()
for R in sorted(C, key=int):
    r = C[R]
    o.append(f"\n## {R}R　{r['dist']}m　{r['n']}頭\n")
    o.append('| 馬番 | 馬名 | 父 | 母父 | 前走（大井） | 材料 |')
    o.append('|---|---|---|---|---|---|')
    for e in sorted(r['e'], key=lambda z: z['u']):
        p3 = ped.get(e['nm'])
        bms = p3['bms'] if p3 else ''
        sire = e['sire'] or (p3['sire'] if p3 else '')
        pv = prev.get(e['nm'])
        pvs = ''
        if pv:
            c4 = pv['c4']
            pvs = f"{pv['d']} {pv['R']}R {pv['dist']}m {pv['pop']}人{pv['f']}着"
            if c4:
                pvs += f" 4角{c4}番手"
        mark = []
        if pv and pv.get('c4') and int(pv['c4']) <= 3:
            mark.append(f"前走4角{pv['c4']}番手")
            cnt['位置'] += 1
        if pv and pv.get('c4') and int(pv['c4']) >= 10:
            mark.append('前走10番手以降')
        if bms in BMS_BUY:
            mark.append(f'母父◯({BMS_BUY[bms]})')
            cnt['母父買'] += 1
        if bms in BMS_CUT:
            mark.append(f'母父×({BMS_CUT[bms]})')
            cnt['母父消'] += 1
        if sire in SIRE_BUY:
            mark.append(f'父◯({SIRE_BUY[sire]})')
            cnt['父買'] += 1
        if sire in SIRE_CUT:
            mark.append(f'父×({SIRE_CUT[sire]})')
            cnt['父消'] += 1
        o.append(f"| {e['u']} | {e['nm']} | {sire} | {bms} | {pvs} | {'／'.join(mark)} |")
o.append('\n---\n')
o.append('材料の数 … ' + '／'.join(f'{k}{v}' for k, v in cnt.items()))
open(OUT, 'w', encoding='utf-8').write('\n'.join(o))
print('書き出し', OUT, dict(cnt))
