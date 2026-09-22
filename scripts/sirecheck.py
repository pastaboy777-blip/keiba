#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""南関の出馬表を血統で照合する。道悪（不良・重）の日に使う。

    python3 scripts/sirecheck.py 20260922 浦和
    python3 scripts/sirecheck.py 20260923 川崎 --pop 7

数字の出どころは南関4場 2025/1〜2026/6・4,513鞍50,199頭。
うち道悪（不良＋重）12,016頭。基準値は
    道悪の7番人気以下ぜんぶ ...... 8.9%
    うち前走4角7番手以降 ......... 7.4%
    人気を問わない道悪ぜんぶ ..... 26.7%
"""
import sys, re, time, argparse

sys.path.insert(0, '/home/user/keiba/src')
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping.race_id import NANKAN_CODES

CARD = 'https://keiba.rakuten.co.jp/race_card/list/RACEID/{}'
IDX = 'https://keiba.rakuten.co.jp/race_card/list/RACEID/{}{}00000000'

# 道悪・7番人気以下の3着内率（基準8.9%）
ANA = {'アジアエクスプレス': (18.8, 80), 'シルバーステート': (17.1, 41),
       'シニスターミニスター': (15.3, 59), 'ラニ': (14.9, 47), 'モンテロッソ': (14.6, 41),
       'フリオーソ': (14.2, 113), 'マクフィ': (14.0, 50), 'マジェスティックウォリ': (13.8, 80),
       'サトノクラウン': (13.2, 53), 'トゥザワールド': (12.7, 63),
       'マインドユアビスケッツ': (12.0, 83), 'ベストウォーリア': (11.4, 88),
       'スマートファルコン': (10.9, 64)}
# 道悪・7番人気以下で沈む父
ANA_X = {'ベルシャザール': (0.0, 46), 'ルーラーシップ': (3.8, 52), 'ビッグアーサー': (4.8, 42),
         'ビーチパトロール': (4.9, 61), 'カレンブラックヒル': (5.6, 72),
         'ダノンレジェンド': (6.3, 79), 'キンシャサノキセキ': (7.3, 41)}
# 人気を問わない道悪（基準26.7%）
AXIS = {'オルフェーヴル': (38.3, 94), 'ラニ': (37.2, 86), 'タリスマニック': (35.3, 139),
        'アジアエクスプレス': (35.2, 219), 'シニスターミニスター': (41.5, 200),
        'マインドユアビスケッツ': (32.7, 171), 'スマートファルコン': (27.5, 142)}
AXIS_X = {'ルーラーシップ': (11.2, 89), 'ラブリーデイ': (18.6, 113),
          'カレンブラックヒル': (19.6, 148), 'イスラボニータ': (21.3, 89),
          'ビッグアーサー': (23.2, 99)}
# 不良でだけ動く父（不良%, 重%）
FUR = {'マクフィ': (31.6, 3.2), 'サトノクラウン': (23.8, 6.2),
       'マジェスティックウォリ': (21.9, 8.3), 'マインドユアビスケッツ': (18.8, 7.8),
       'ベストウォーリア': (3.3, 15.5)}
# 母父（7番人気以下）
BMS = {'ジャングルポケット': 20.0, 'ファスリエフ': 14.6, 'ネオユニヴァース': 12.8,
       'ダンスインザダーク': 13.2, 'ハービンジャー': 11.8, 'ハーツクライ': 10.8}
BMS_X = {'サンデーサイレンス': 3.5, 'サクラバクシンオー': 3.8, 'パイロ': 5.7,
         'ゼンノロブロイ': 6.1, 'ゼンノロブロイ ': 7.4}

PAT = re.compile(r'\|*([^|]+?)\|+([^|]+?)\|+([^|]+?)\|\(([^)]*)\)\|+([\d.]+)\|*\s*\n?\s*（(\d+)人気）')


def flat(t):
    t = re.sub(r'<[^>]+>', '|', t)
    t = re.sub(r'\|+', '|', t)
    t = re.sub(r'[ \t]+', ' ', t)
    t = re.sub(r'\|\s*', '|', t)
    return re.sub(r'\s*\|', '|', t)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('date'); ap.add_argument('place')
    ap.add_argument('--pop', type=int, default=7, help='穴として扱う人気の下限（既定7）')
    a = ap.parse_args()
    code = NANKAN_CODES.get(a.place)
    if not code:
        sys.exit('南関4場のみ: %s' % list(NANKAN_CODES))
    c = PoliteClient(use_cache=False)
    idx = c.get(IDX.format(a.date, code))   # リンクを潰さないよう生のまま拾う
    rids = sorted({x for x in re.findall(r'RACEID/(%s%s\d{8})' % (a.date, code), idx)
                   if not x.endswith('00000000')})
    if not rids:
        sys.exit('%s %s は開催なし、または未掲載' % (a.date, a.place))

    print('■ %s %s ── 道悪の血統照合' % (a.date, a.place))
    print('  基準: 道悪の%d番人気以下=8.9%% / 前走4角7番手以降=7.4%% / 人気問わず=26.7%%\n' % a.pop)
    for rid in rids:
        R = int(rid[-2:])
        t = flat(c.get(CARD.format(rid)))
        dm = re.search(r'ダ([\d,]+)m', t)          # 当該レースの距離（前5走の表記に引っかからないよう）
        dist = int(dm.group(1).replace(',', '')) if dm else 0
        bm = re.search(r'ダ：\|?([^|]+)', t)
        baba = bm.group(1).strip() if bm else '?'
        es = []
        for ch in t.split('|消|')[1:]:
            m = PAT.match(ch)
            if not m:
                continue
            g = re.search(r'\|(牡|牝|セ)(\d)\|', ch)
            es.append(dict(sire=m.group(1).strip(), nm=m.group(2).strip(), bms=m.group(4).strip(),
                           od=float(m.group(5)), pop=int(m.group(6)),
                           sx=(g.group(1) + g.group(2)) if g else ''))
        n_real = len(re.findall(r'\|消\|', t))
        lines = []
        for e in sorted(es, key=lambda x: x['pop']):
            s, b, p = e['sire'], e['bms'], e['pop']
            tag = []
            if p >= a.pop:
                if s in ANA:
                    v, n = ANA[s]
                    # アジアエクスプレスは距離で割れる
                    if s == 'アジアエクスプレス':
                        if 1300 <= dist <= 1600:
                            tag.append('★★穴父 25.5%%(51頭/1300〜1600m)')
                        elif dist <= 1200:
                            tag.append('△穴父だが1200m以下は0.0%(20頭)')
                        else:
                            tag.append('★穴父 %.1f%%(%d頭)' % (v, n))
                    else:
                        tag.append('★穴父 %.1f%%(%d頭)' % (v, n))
                if s in ANA_X:
                    v, n = ANA_X[s]
                    tag.append('×消し父 %.1f%%(%d頭)' % (v, n))
                if b in BMS:
                    tag.append('+母父 %.1f%%' % BMS[b])
                if b in BMS_X:
                    tag.append('-母父 %.1f%%' % BMS_X[b])
            else:
                if s in AXIS:
                    v, n = AXIS[s]
                    tag.append('◆軸父 %.1f%%(%d頭)' % (v, n))
                if s in AXIS_X:
                    v, n = AXIS_X[s]
                    tag.append('×軸で疑う %.1f%%(%d頭)' % (v, n))
            if s in FUR:
                f, h = FUR[s]
                if baba == '不良':
                    tag.append('［不良%.1f%%］' % f)
                elif baba == '重':
                    tag.append('［重%.1f%%］' % h)
                else:
                    tag.append('［不良%.1f%% / 重%.1f%%］' % (f, h))
            if tag:
                lines.append('   %2d人気 %6.1f倍 %-14s %-3s 父%-15s %s'
                             % (p, e['od'], e['nm'][:14], e['sx'], s[:15], ' '.join(tag)))
        print(' %2dR ダ%dm %s %d頭%s' % (R, dist, baba, n_real,
                                      '' if len(es) == n_real else '（血統を読めたのは%d頭）' % len(es)))
        print('\n'.join(lines) if lines else '   （該当なし）')
        time.sleep(0.5)


if __name__ == '__main__':
    main()
