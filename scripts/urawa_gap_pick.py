#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""浦和の出馬表を、いまの2つの枠組みで照合する。

  ① 開催間隔（今開催は中41日＝1ヶ月以上あけ）
       7番人気以下 × 前走4〜6着 × 前走が浦和以外  → 290頭16.2%（基準9.3%）
       距離延長300m以上 → 7.8%（消し）
  ② 馬場
       重以上なら血統表が効く。稍重なら効かないので出さない。
       300m以上の距離延長は4段階すべてで割引。

    python3 scripts/urawa_gap_pick.py 20260923
"""
import sys, re, time, argparse

sys.path.insert(0, '/home/user/keiba/src')
from nankeiba.scraping.client import PoliteClient

CARD = 'https://keiba.rakuten.co.jp/race_card/list/RACEID/{}'
IDX = 'https://keiba.rakuten.co.jp/race_card/list/RACEID/{}1800000000'

# 道悪（重以上）でだけ効く父。7番人気以下の3着内率（基準8.9%）
SIRE_UP = {'アジアエクスプレス': 18.8, 'シルバーステート': 17.1, 'シニスターミニスター': 15.3,
           'ラニ': 14.9, 'モンテロッソ': 14.6, 'フリオーソ': 14.2, 'マクフィ': 14.0,
           'マジェスティックウォリ': 13.8, 'サトノクラウン': 13.2, 'トゥザワールド': 12.7,
           'マインドユアビスケッツ': 12.0, 'ベストウォーリア': 11.4, 'スマートファルコン': 10.9}
SIRE_DN = {'ベルシャザール': 0.0, 'ルーラーシップ': 3.8, 'ビッグアーサー': 4.8,
           'ビーチパトロール': 4.9, 'カレンブラックヒル': 5.6, 'ダノンレジェンド': 6.3,
           'キンシャサノキセキ': 7.3}
SIRE_AXIS = {'タリスマニック': 35.3, 'オルフェーヴル': 38.3, 'ラニ': 37.2,
             'アジアエクスプレス': 35.2, 'シニスターミニスター': 41.5}
SIRE_AXIS_DN = {'ルーラーシップ': 11.2, 'ラブリーデイ': 18.6, 'カレンブラックヒル': 19.6,
                'イスラボニータ': 21.3, 'ビッグアーサー': 23.2}
# 不良でだけ動く父（不良%, 重%）
FUR = {'マクフィ': (31.6, 3.2), 'サトノクラウン': (23.8, 6.2), 'マジェスティックウォリ': (21.9, 8.3),
       'マインドユアビスケッツ': (18.8, 7.8), 'ベストウォーリア': (3.3, 15.5)}

PLACES = ('浦和', '川崎', '船橋', '大井', '門別', '盛岡', '水沢', '金沢', '笠松', '名古屋',
          '園田', '姫路', '高知', '佐賀', '札幌', '函館', '福島', '新潟', '東京', '中山',
          '中京', '京都', '阪神', '小倉')
HEAD = re.compile(r'\|*([^|]+?)\|+([^|]+?)\|+([^|]+?)\|\(([^)]*)\)\|+([\d.]+)\|*\s*\n?\s*（(\d+)人気）')
PREV = re.compile(r'\|(\d+)\|+([良稍重不])\|+(\d+)頭\|.*?\|(' + '|'.join(PLACES) +
                  r') (\d\d)\.(\d\d)\.(\d\d)\|.*?(\d{3,4})(?:左|右|直)ダ', re.S)


def get(c, u, tries=5):
    for i in range(tries):
        try:
            return c.get(u)
        except Exception:
            time.sleep(2 * (i + 1))
    return None


def flat(t):
    t = re.sub(r'<[^>]+>', '|', t)
    t = re.sub(r'\|+', '|', t)
    t = re.sub(r'[ \t]+', ' ', t)
    t = re.sub(r'\|\s*', '|', t)
    return re.sub(r'\s*\|', '|', t)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('date')
    ap.add_argument('--pop', type=int, default=7)
    a = ap.parse_args()
    c = PoliteClient(use_cache=False)
    idx = get(c, IDX.format(a.date))
    if idx is None:
        sys.exit('インデックス取得に失敗')
    rids = sorted({x for x in re.findall(r'RACEID/(%s18\d{8})' % a.date, idx)
                   if not x.endswith('00000000')})
    if not rids:
        sys.exit('%s は浦和の開催なし、または未掲載' % a.date)

    print('■ %s 浦和 ── 中41日（1ヶ月以上あけ）の枠組みで照合' % a.date)
    print('  基準: 7番人気以下の3着内率 9.3%')
    print('  ★ = 前走4〜6着 × 前走が浦和以外（290頭16.2%）')
    print('  × = 300m以上の距離延長（383頭7.8%）\n')
    for rid in rids:
        R = int(rid[-2:])
        raw = get(c, CARD.format(rid))
        if raw is None:
            print(' %2dR 取得できず' % R); continue
        t = flat(raw)
        dm = re.search(r'ダ([\d,]+)m', t)
        dist = int(dm.group(1).replace(',', '')) if dm else 0
        bm = re.search(r'ダ：\|?([^|]+)', t)
        baba = bm.group(1).strip() if bm else '?'
        doaku = baba in ('重', '不良')
        es = []
        for ch in t.split('|消|')[1:]:
            m = HEAD.match(ch)
            if not m:
                continue
            g = re.search(r'\|(牡|牝|セ)(\d)\|', ch)
            p = PREV.search(ch)
            e = dict(sire=m.group(1).strip(), nm=m.group(2).strip(), bms=m.group(4).strip(),
                     od=float(m.group(5)), pop=int(m.group(6)),
                     sx=(g.group(1) + g.group(2)) if g else '')
            if p:
                e.update(pf=int(p.group(1)), pbaba=p.group(2), ppl=p.group(4),
                         pd='20%s-%s-%s' % (p.group(5), p.group(6), p.group(7)),
                         pdist=int(p.group(8)))
            es.append(e)
        n_real = len(re.findall(r'\|消\|', t))
        print(' %2dR ダ%dm %s %d頭%s' % (R, dist, baba, n_real,
                                         '' if len(es) == n_real else '（読めたのは%d頭）' % len(es)))
        lines = []
        for e in sorted(es, key=lambda x: x['pop']):
            tag = []
            pf, ppl, pdist = e.get('pf'), e.get('ppl'), e.get('pdist')
            dc = (dist - pdist) if pdist else None
            if e['pop'] >= a.pop:
                if pf and ppl:
                    if 4 <= pf <= 6 and ppl != '浦和':
                        tag.append('★★本線 16.2%%（前走%s%d着・場替わり）' % (ppl, pf))
                    elif ppl != '浦和':
                        tag.append('★場替わり 10.0%%（前走%s%d着）' % (ppl, pf))
                    elif 4 <= pf <= 6:
                        tag.append('前走4〜6着 13.4%（ただし浦和連戦）')
                    if pf >= 10:
                        tag.append('×前走10着以下 5.6%')
                if dc is not None and dc >= 300:
                    tag.append('×延長%+dm 7.8%%' % dc)
                if doaku:
                    if e['sire'] in SIRE_UP:
                        tag.append('★穴父 %s %.1f%%' % (e['sire'], SIRE_UP[e['sire']]))
                    if e['sire'] in SIRE_DN:
                        tag.append('×消し父 %s %.1f%%' % (e['sire'], SIRE_DN[e['sire']]))
            else:
                if doaku:
                    if e['sire'] in SIRE_AXIS:
                        tag.append('◆軸父 %s %.1f%%' % (e['sire'], SIRE_AXIS[e['sire']]))
                    if e['sire'] in SIRE_AXIS_DN:
                        tag.append('×軸で疑う %s %.1f%%' % (e['sire'], SIRE_AXIS_DN[e['sire']]))
                if dc is not None and dc >= 300:
                    tag.append('延長%+dm（4段階すべてで割引）' % dc)
            if baba == '不良' and e['sire'] in FUR:
                tag.append('［不良%.1f%%］' % FUR[e['sire']][0])
            elif baba == '重' and e['sire'] in FUR:
                tag.append('［重%.1f%%］' % FUR[e['sire']][1])
            if tag:
                lines.append('   %2d人気 %6.1f倍 %-14s %-3s 父%-13s  %s'
                             % (e['pop'], e['od'], e['nm'][:14], e['sx'], e['sire'][:13], ' / '.join(tag)))
        print('\n'.join(lines) if lines else '   （該当なし）')
        if not doaku:
            print('   <span>※稍重以下なので血統は出していない</span>'.replace('<span>', '').replace('</span>', ''))
        time.sleep(0.5)


if __name__ == '__main__':
    main()
