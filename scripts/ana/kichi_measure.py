
# 過去走ランクW の人気薄を穴で狙う作戦 ── 浦和2026年で測る
import json

S = '/tmp/claude-0/-home-user-keiba/5c9e9520-78d2-57a1-98df-28a0a517ec92/scratchpad/'
D = json.load(open(S + 'urawa_year.json'))
R = []
for rid, r in D.items():
    for x in r['rows']:
        x.update(rid=rid, date=r['date'], Rno=r['R'], N=len(r['rows']),
                 dist=r['dist'], baba=r['baba'], tenko=r['tenko'])
        if x.get('chaku'):
            R.append(x)
print('%d日 / %d鞍 / 出走 %d頭' % (len({x['date'] for x in R}), len(D), len(R)))


def stat(g):
    """頭数・勝率・3着内率・単勝回収率・複勝回収率"""
    t = len(g)
    if not t:
        return None
    w = sum(1 for x in g if x['chaku'] == 1)
    p3 = sum(1 for x in g if x['chaku'] <= 3)
    tan = sum(x['tan'] or 0 for x in g if x['chaku'] == 1)
    fuku = sum(x['fuku'] or 0 for x in g if x['fuku'])
    return t, w, 100 * w / t, 100 * p3 / t, tan / t, fuku / t


def line(lab, g):
    s = stat(g)
    if not s:
        return
    t, w, wr, p3, tr, fr = s
    print('  %-24s %5d %9s %7.0f%% %8.0f%% %8.0f%%'
          % (lab, t, '%d (%.0f%%)' % (w, wr), p3, tr, fr))


HEAD = '  %-24s %5s %9s %7s %8s %8s' % ('', '頭数', '1着', '3着内', '単回収', '複回収')

print('\n【1】人気帯ごと（全馬）')
print(HEAD)
for lo, hi, lab in ((1, 1, '1番人気'), (2, 3, '2〜3人気'), (4, 5, '4〜5人気'),
                    (6, 9, '6〜9人気'), (10, 99, '10人気以下')):
    line(lab, [x for x in R if x['nk'] and lo <= x['nk'] <= hi])

print('\n【2】過去走ランク別（全人気）')
print(HEAD)
for k in 'WXYZ':
    line('過去走' + k, [x for x in R if x['kako_rank'] == k])
line('ランクなし', [x for x in R if x['kako_rank'] not in list('WXYZ')])

print('\n【3】★ 過去走W × 人気帯')
print(HEAD)
for lo, hi, lab in ((1, 1, 'W × 1番人気'), (2, 3, 'W × 2〜3人気'), (4, 5, 'W × 4〜5人気'),
                    (6, 9, 'W × 6〜9人気'), (10, 99, 'W × 10人気以下'),
                    (6, 99, 'W × 6人気以下（まとめ）')):
    line(lab, [x for x in R if x['kako_rank'] == 'W' and x['nk'] and lo <= x['nk'] <= hi])

print('\n【4】比較：6人気以下のなかで')
print(HEAD)
P = [x for x in R if x['nk'] and x['nk'] >= 6]
line('6人気以下 全体', P)
for k in 'WXYZ':
    line('　過去走' + k, [x for x in P if x['kako_rank'] == k])
for k in 'ABCD':
    line('　前走ランク' + k, [x for x in P if x['zenso_rank'] == k])
line('　評価◎○▲', [x for x in P if x['hyoka'] in ('◎', '○', '▲')])
line('　SP能力値3位以内', [x for x in P if x['sp_r'] and x['sp_r'] <= 3])
line('　先行力1位', [x for x in P if x['senko_r'] == 1])

print('\n【5】W×6人気以下を、さらに絞ると')
print(HEAD)
WP = [x for x in P if x['kako_rank'] == 'W']
line('W×6人気以下', WP)
line('　＋SP能力値3位以内', [x for x in WP if x['sp_r'] and x['sp_r'] <= 3])
line('　＋SP調整3位以内', [x for x in WP if x['chosei_r'] and x['chosei_r'] <= 3])
line('　＋末脚力3位以内', [x for x in WP if x['sue_r'] and x['sue_r'] <= 3])
line('　＋SP信頼3位以内', [x for x in WP if x['shinrai_r'] and x['shinrai_r'] <= 3])
line('　＋先行力3位以内', [x for x in WP if x['senko_r'] and x['senko_r'] <= 3])
line('　－先行力1位を除く', [x for x in WP if x['senko_r'] != 1])
line('　＋前走ランクC/D/無印', [x for x in WP if x['zenso_rank'] not in ('A', 'B')])

print('\n【6】W×6人気以下を 距離・頭数・馬場で')
print(HEAD)
line('1400m以下', [x for x in WP if x['dist'] and x['dist'] <= 1400])
line('1500m以上', [x for x in WP if x['dist'] and x['dist'] >= 1500])
line('11頭以下', [x for x in WP if x['N'] <= 11])
line('12頭以上', [x for x in WP if x['N'] >= 12])
line('良', [x for x in WP if x['baba'] == '良'])
line('良以外', [x for x in WP if x['baba'] and x['baba'] != '良'])

print('\n【7】月ごと（W×6人気以下）')
print(HEAD)
for mth in range(1, 11):
    g = [x for x in WP if int(x['date'].split('/')[1]) == mth]
    if g:
        line('%d月' % mth, g)
