# -*- coding: utf-8 -*-
"""サンデーサイレンスのクロスが南関で効くかを測る。

吉馬から取れるのは父・母・母父の3代まで。4〜5代は取れないので、
  父がサンデー系 × 母父もサンデー系 → サンデーのクロスがある
という形でしか判定できない。これは3×3〜4×3あたりの近いクロスに当たる。
"""
import json, glob, sys, collections

PED = sys.argv[1]
BA = {'18': '浦和', '19': '船橋', '20': '大井', '21': '川崎'}

# 南関で見かけるサンデーサイレンス系の種牡馬（父系がサンデーに遡るもの）
SS = set("""サンデーサイレンス ディープインパクト ステイゴールド アグネスタキオン フジキセキ
ダイワメジャー ハーツクライ ネオユニヴァース ゼンノロブロイ マンハッタンカフェ スペシャルウィーク
ハットトリック ゴールドアリュール スマートファルコン エスポワールシチー コパノリッキー
オルフェーヴル ゴールドシップ ドリームジャーニー キズナ リアルインパクト ダノンシャンティ
トーセンホマレボシ ヴィクトワールピサ ルーラーシップ エピファネイア ロードカナロア
ディープブリランテ トーセンジョーダン カネヒキリ ヴァーミリアン フサイチホウオー
アドマイヤムーン シニスターミニスター ホッコータルマエ ルヴァンスレーヴ ミッキーアイル
ダノンレジェンド ドゥラメンテ モーリス サトノクラウン キタサンブラック シルバーステート
イスラボニータ ジャスタウェイ リオンディーズ サートゥルナーリア スワーヴリチャード
レイデオロ ブラックタイド マツリダゴッホ メイショウサムソン""".split())
# 上のうち父系がサンデーでないものを除く
NOTSS = set("""シニスターミニスター ホッコータルマエ ロードカナロア アドマイヤムーン
ダノンレジェンド エスポワールシチー ヴァーミリアン カネヒキリ ルヴァンスレーヴ""".split())
SS -= NOTSS


def isss(name):
    return name in SS


ped = {}
for l in open(PED, encoding='utf-8'):
    x = json.loads(l)
    ped[x['nm']] = x
rows = []
for p in sorted(glob.glob('notes/live/*/results.json')):
    d = p.split('/')[2]
    if len(d) != 10:
        continue
    for Rs, r in json.load(open(p, encoding='utf-8')).items():
        ba = BA.get(str(r.get('rid', ''))[8:10])
        if not ba:
            continue
        for e in r['e']:
            if not str(e.get('f', '')).isdigit():
                continue
            q = ped.get(e['nm'])
            if not q:
                continue
            rows.append(dict(ba=ba, dist=r['dist'], f=int(e['f']), pop=int(e['pop']),
                             nm=e['nm'], sire=q['sire'], bms=q['bms'],
                             ss_s=isss(q['sire']), ss_b=isss(q['bms'])))
exp = collections.defaultdict(lambda: [0, 0])
for x in rows:
    exp[x['pop']][0] += 1
    exp[x['pop']][1] += x['f'] <= 3


def rep(sel, lab, mn=25, popmin=0):
    g = [x for x in rows if x['pop'] >= popmin and sel(x) and exp[x['pop']][0] >= 8]
    if len(g) < mn:
        print('%-36s n=%d (少)' % (lab, len(g)))
        return
    h = sum(1 for x in g if x['f'] <= 3)
    w = sum(1 for x in g if x['f'] == 1)
    e = sum(exp[x['pop']][1] / exp[x['pop']][0] for x in g)
    print('%-36s n=%4d 3着内%3d(%5.1f%%) 1着%2d 期待%5.1f%% %+5.1fpt'
          % (lab, len(g), h, 100 * h / len(g), w, 100 * e / len(g),
             100 * (h / len(g) - e / len(g))))


print('%d頭 / 馬 %d頭' % (len(rows), len({x['nm'] for x in rows})))
print('  父がサンデー系 %d頭 ／ 母父がサンデー系 %d頭 ／ 両方 %d頭'
      % (sum(1 for x in rows if x['ss_s']), sum(1 for x in rows if x['ss_b']),
         sum(1 for x in rows if x['ss_s'] and x['ss_b'])))
for popmin, tag in ((0, '全体'), (7, '7番人気以下')):
    print('\n=== %s ───────' % tag)
    rep(lambda x: True, 'ぜんぶ（基準）', 40, popmin)
    rep(lambda x: x['ss_s'] and x['ss_b'], 'サンデーのクロスあり（父も母父もSS系）', 20, popmin)
    rep(lambda x: x['ss_s'] and not x['ss_b'], '父だけSS系', 20, popmin)
    rep(lambda x: not x['ss_s'] and x['ss_b'], '母父だけSS系', 20, popmin)
    rep(lambda x: not x['ss_s'] and not x['ss_b'], 'SS系なし', 20, popmin)
