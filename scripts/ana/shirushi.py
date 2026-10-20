"""買う馬リスト ── 印を打ってカード HTML を書き出す。

  python3 shirushi.py 1,2,3,4,5,6 out   # レース番号, 出力名 -> out.html

物差しは CLAUDE.md「買う馬リストの組み方」。要点だけ:
  ・上がりは今日と同じ距離帯の走りからだけ。距離帯の実績がない馬には使わない
  ・位置は「前にいるほど良い」ではなく、中団前め（0.30〜0.55）がいちばん高い
  ・1角→4角で前へ出られるか（gain）を点数に入れる
  ・上がりが取れない場（佐賀・金沢・笠松）の馬は着順で埋める。0点で沈めない
  ・照明が入る鞍（NIGHT）はラチ沿いを追走できる馬を加点する
  ・穴は「真ん中の馬」を拾わない。2つの形だけを、印の5頭より下から探す

手で直すところ: FORCE（軸）/ DROP（消す馬）/ FORCE_ANA（穴）/ NIGHT。
"""
import json, html as H

import os
# 作業ディレクトリと日付の接頭辞は環境変数で差し替える
#   SHIRUSHI_DIR=/path SHIRUSHI_PREF=ura1021 python3 shirushi.py 1,2,3 out
S = os.environ.get('SHIRUSHI_DIR', '.').rstrip('/') + '/'
PREF = os.environ.get('SHIRUSHI_PREF', 'ura')
P = json.load(open(S + PREF + '_prof.json'))


NIGHT = {9, 10, 11, 12}          # 照明が入る鞍。ラチ沿い追走馬を加点する


def score(z, n, night=False):
    s = 0
    if night and z.get('inlane') is not None and (z.get('nlane') or 0) >= 3:
        pr0 = z.get('prel')
        if z['inlane'] >= 0.65 and pr0 is not None and 0.12 <= pr0 < 0.60: s += 3
        elif z['inlane'] >= 0.5: s += 1
        if z.get('ub') and z['ub'] <= n / 3: s += 1
    # ★上がりは今日の距離帯の走りからしか取らない。
    #   距離帯の実績がない／上がりが1走ぶんしかない馬は、半分の重さにする。
    half = (z.get('negd') or 0) < 2
    e = z.get('edge')
    if z.get('xband'):                            # この距離を走っていない＝上がりは持ち越さない
        e = None
        s -= 1                                    # 初距離は未知。切りはしないが割り引く
    if e is not None:                              # この距離での上がり（主変数）
        if e <= 0.0: s += 3 if half else 5
        elif e <= 0.4: s += 2 if half else 4
        elif e <= 0.8: s += 1 if half else 2
        elif e >= 1.3: s -= 1 if half else 2
    b = None if z.get('xband') else z.get('bedge')  # 一度でも差し脚を使えているか
    if b is not None:
        if b <= -0.5: s += 2
        elif b <= -0.2: s += 1
    # 佐賀・金沢・笠松など上がりが取れない馬は、着順で埋める（0点のまま沈めない）
    ir = z.get('inrate')
    if (z.get('negd') or 0) == 0 and ir is not None:   # 本当に上がりが引けない馬だけ
        if ir >= 0.5: s += 3
        elif ir >= 0.33: s += 2
        elif ir == 0: s -= 2
    if (z.get('frontwin') or 0) >= 2: s += 2      # 前で粘って3着内が2回以上
    g = z.get('gain')                             # 1角→4角で前へ出られるか
    if g is not None:
        if g >= 2: s += 3
        elif g >= 1: s += 2
        elif g <= -2.5: s -= 3
        elif g <= -1: s -= 1
    p = z.get('prel')
    # ★位置は「前にいるほど良い」ではなく、差せる位置（中団前め）をいちばん高くする
    if p is not None:
        if p < 0.15: s += 1                       # 逃げ切り型。消さないが、ここでは加点しない
        elif p < 0.30: s += 2
        elif p < 0.55: s += 3                      # 中団前め＝差せる位置
        elif p < 0.70: s += 0
        else: s -= 3                               # 後方。昨日はここから3着内ゼロ
        if z.get('xband'): s -= 1                  # 距離帯が違う位置は割り引く
    ub = z.get('ub')
    if ub:
        if ub <= n / 3: s += 2
        if ub > 2 * n / 3: s -= 1
    pc = z.get('pchaku')
    if pc and 2 <= pc <= 6: s += 1
    if z.get('urel') is not None and z['urel'] < 0.25 and z.get('un', 0) >= 3: s += 1
    return s


def why(z, night=False):
    p = []
    if night and z.get('inlane') is not None and (z.get('nlane') or 0) >= 3 \
            and z['inlane'] >= 0.65:
        p.append('ラチ沿いを追走できる')
    half = z.get('xband') or (z.get('negd') or 0) < 2
    e = None if z.get('xband') else z.get('edge')
    if e is not None:
        if e <= 0.1: p.append('この距離で最後まで減速しない')
        elif e <= 0.4: p.append('この距離で脚を残せる')
    b = None if z.get('xband') else z.get('bedge')
    if b is not None and b <= -0.5: p.append('この距離で差し脚を使えている')
    if (z.get('gain') or 0) >= 2: p.append('1角から4角で前へ出られる')
    if (z.get('frontwin') or 0) >= 2: p.append('前で粘って3着内が複数回')
    pr = z.get('prel')
    if pr is not None and 0.30 <= pr < 0.55: p.append('差せる位置を取れる')
    elif pr is not None and pr < 0.30: p.append('前めを取れる')
    if z.get('urel') is not None and z['urel'] < 0.25 and z.get('un', 0) >= 3:
        p.append('浦和では毎回前にいる')
    if z.get('xband'): p.append('この距離は初めて')
    if not p and z.get('pchaku'):
        p.append('前走' + str(z['pchaku']) + '着からの巻き返しを狙える')
    return ' &middot; '.join(p[:3]) or '&nbsp;'


def ana_kind(z):
    """昨日の浦和で実際に6人気以下から3着内に来た2つの形だけを拾う。
    真ん中にいる馬は1頭も来ていないので、真ん中は拾わない。"""
    pr = z.get('prel')
    if pr is None: return None
    b = None if z.get('xband') else z.get('bedge')
    g = z.get('gain') or 0
    fw = z.get('frontwin') or 0
    pc = z.get('pchaku') or 0
    # ①後ろめにいて、4角までに前へ出られて、この距離で差し脚を使えている
    if pr >= 0.40 and g >= 0.5 and b is not None and b <= -0.2:
        return '後ろから4角までに押し上げられる &middot; この距離で差し脚を使えている'
    # ②最初から前で粘れる型。前走を負けていて人気は落ちる
    if pr < 0.32 and fw >= 1 and pc >= 4:
        return '最初から前で粘れる型 &middot; 前走' + str(pc) + '着で人気は落ちる'
    return None


# ★手動の上書き（軸を指定する）
FORCE = {5: [2, 3, 4], 6: [11]}
# ★手動で消す馬 {R: [馬番]}
DROP = {5: [5]}
# ★穴の手動指定 {R: (馬番, 理由)}
FORCE_ANA = {}

meta = {}
for R, v in P.items():
    n = v['n']
    have = [r for r in v['rows'] if r.get('prel') is not None]
    for r in have:
        r['sc'] = score(r, n, int(R) in NIGHT)
    live = sorted(have, key=lambda r: -r['sc'])
    live = [r for r in live if r['ub'] not in DROP.get(int(R), [])]
    f = FORCE.get(int(R))
    if f:
        d = {r['ub']: r for r in live}
        live = [d[u] for u in f if u in d] + [r for r in live if r['ub'] not in f]
    meta[int(R)] = dict(dist=v['dist'], start=v['start'], n=n,
                        live=live, nohist=(len(have) == 0))

BIG = [r for r, _ in sorted([(r, m['live'][0]['sc']) for r, m in meta.items() if m['live']],
                           key=lambda t: -t[1])[:3]]
# 穴＝前走が負けていて人気が落ちそうな馬。各レースから最大1頭、点数が2以上のもの
ANA = []
for r, m in sorted(meta.items()):
    for z in m['live']:
        z['akind'] = ana_kind(z)
    f = FORCE_ANA.get(r)
    if f:
        for z in m['live']:
            if z['ub'] == f[0]: z['akind'] = f[1]
        ANA.append((r, f[0])); continue
    c = [z for z in m['live'][5:] if z['akind']]   # 印を打った5頭より下から探す
    if c: ANA.append((r, max(c, key=lambda z: z['sc'])['ub']))
MK = ['&#9678;', '&#9675;', '&#9650;', '&#9651;', '&#9651;']

CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"Hiragino Kaku Gothic ProN","Noto Sans JP","IPAPGothic",sans-serif;
 background:#0c0c0e;color:#f2efe9;width:2000px;padding:72px 76px 52px;
 background-image:repeating-linear-gradient(100deg,rgba(255,255,255,.022) 0 3px,transparent 3px 9px)}
.bt{font-size:30px;letter-spacing:.18em;color:#9a9288;font-weight:800;margin-bottom:9px}
h1{font-size:148px;font-weight:900;color:#e8362f;line-height:1.02;letter-spacing:-.02em}
h1 small{display:block;font-size:68px;color:#6b645b;margin-bottom:5px}
.sub{font-size:50px;font-weight:800;margin-top:20px}
.sub span{color:#a39b90;font-size:38px;font-weight:700;margin-left:10px}
.lead{font-size:38px;color:#cdc6bc;line-height:1.7;margin:24px 0 0;border-left:9px solid #f5d020;padding-left:26px}
.lead b{color:#fff}
.sh{font-size:54px;font-weight:900;margin:52px 0 24px;padding-left:22px;border-left:12px solid #e8362f}
.sh span{font-size:34px;color:#8d867c;font-weight:700;margin-left:11px}
.grid{display:flex;flex-wrap:wrap;gap:20px}
.rc{background:#17161a;border:2px solid #39353d;border-radius:18px;padding:30px 34px 26px;width:calc(50% - 10px)}
.rc.big{border-color:#8a2b26;box-shadow:inset 0 0 0 1px #5d201c}
.rc.sml{background:#131216;border-color:#2b2930}
.rh{display:flex;align-items:baseline;gap:16px;border-bottom:2px solid #2b2930;padding-bottom:14px;margin-bottom:14px}
.rn{font-size:62px;font-weight:900;color:#f5d020}
.sml .rn{font-size:52px;color:#8d867c}
.rd{font-size:36px;font-weight:800}
.rt{font-size:29px;color:#7e776e;font-weight:700}
.rz{margin-left:auto;font-size:29px;color:#8d867c;font-weight:800}
.rz b{color:#e8362f}
.hr{display:flex;align-items:center;gap:14px;padding:9px 0}
.mk{flex:none;width:40px;font-size:36px;color:#e8362f;font-weight:900}
.hr.p2 .mk{color:#8d867c}.hr.p3 .mk{color:#6b645b}
.ub{flex:none;width:46px;height:46px;line-height:46px;text-align:center;border-radius:4px;
 background:#2b2930;font-size:30px;font-weight:900}
.hr.p1 .ub{background:#e8362f;color:#fff}
.sml .hr.p1 .ub{background:#4a4752}
.nm{flex:1;font-size:39px;font-weight:900;letter-spacing:-.01em}
.hr.p2 .nm{font-size:34px;font-weight:800;color:#c4bcb1}
.hr.p3 .nm{font-size:33px;font-weight:700;color:#8d867c}
.jk{flex:none;width:120px;text-align:right;font-size:28px;color:#7e776e;font-weight:700}
.sc{flex:none;width:58px;text-align:right;font-size:37px;font-weight:900;color:#f5d020}
.hr.p2 .sc{color:#8d867c;font-size:32px}.hr.p3 .sc{color:#5d574f;font-size:31px}
.sml .sc{color:#8d867c}
.few{font-size:31px;color:#8d867c;font-weight:800;margin:14px 0 10px;line-height:1.7}
table{width:100%;border-collapse:collapse;margin-top:4px}
td{padding:20px 10px;font-size:36px;border-bottom:1px solid #222026}
.ar{width:104px;color:#f5d020;font-weight:900;font-size:40px}
.au{width:62px;text-align:center;background:#2b2930;border-radius:5px;font-weight:900;font-size:32px}
.an{font-weight:900;font-size:40px;padding-left:26px}
.aj{width:150px;color:#7e776e;font-weight:700;font-size:28px}
.awy{color:#ff8a52;font-weight:700;font-size:30px;text-align:right;padding-right:22px}
.aw{color:#f5d020;font-weight:900;font-size:36px;text-align:right;width:90px}
.bb{margin-top:48px;display:flex;justify-content:space-between;font-size:26px;
 letter-spacing:.16em;color:#5d574f;font-weight:800;border-top:1px solid #222026;padding-top:11px}
"""


def card(r):
    m = meta[r]; cls = 'big' if r in BIG else 'sml'
    h = '<div class="rc ' + cls + '">'
    h += ('<div class="rh"><span class="rn">' + str(r) + 'R</span>'
          '<span class="rd">' + str(m['dist']) + 'm</span>'
          '<span class="rt">' + m['start'] + '</span>'
          '<span class="rz">' + (('<b>勝負</b>　' if cls == 'big' else '') + str(m['n']) + '頭') +
          '</span></div>')
    if m['nohist']:
        h += '<div class="few">2歳新馬。全頭に出走履歴がないので、<br>この物差しは使えません。</div></div>'
        return h
    for i, z in enumerate(m['live'][:5]):
        cl = 'p1' if i == 0 else ('p2' if i <= 2 else 'p3')
        h += ('<div class="hr ' + cl + '"><span class="mk">' + MK[i] + '</span>'
              '<span class="ub">' + str(z['ub']) + '</span>'
              '<span class="nm">' + H.escape(z['name']) + '</span>'
              '<span class="jk">' + H.escape((z['jk'] or '')[:5]) + '</span>'
              '<span class="sc">' + ('%+d' % z['sc']) + '</span></div>')
    return h + '</div>'


import sys
RS = [int(v) for v in (sys.argv[1].split(',') if len(sys.argv) > 1 else '1,2,3,4,5,6,7,8,9,10,11,12'.split(','))]
BADGE = '%dR〜%dR' % (RS[0], RS[-1])
OUTNAME = sys.argv[2] if len(sys.argv) > 2 else 'ura1020'
# 勝負どころは、その画像に載る鞍の中から選ぶ
BIG = [r for r, _ in sorted([(r, m['live'][0]['sc']) for r, m in meta.items()
                             if m['live'] and r in RS], key=lambda t: -t[1])[:3]]
ana = ''
for r, ub in [t for t in ANA if t[0] in RS]:
    z = [x for x in meta[r]['live'] if x['ub'] == ub][0]
    ana += ('<tr><td class="ar">' + str(r) + 'R</td><td class="au">' + str(ub) + '</td>'
            '<td class="an">' + H.escape(z['name']) + '</td>'
            '<td class="aj">' + H.escape((z['jk'] or '')[:5]) + '</td>'
            '<td class="awy">' + (z.get('akind') or why(z, r in NIGHT)) + '</td>'
            '<td class="aw">' + ('%+d' % z['sc']) + '</td></tr>')

HTML = ('<!doctype html><html lang="ja"><head><meta charset="utf-8"><style>' + CSS + '</style></head><body>'
        '<div class="bt">変態か、変態以外か。</div>'
        '<h1><small>10/21 浦和</small>買う馬リスト</h1>'
        '<div class="sub">10/21（水）浦和　' + BADGE + '<span>各レース5頭。赤枠が勝負どころ</span></div>'
        '<div class="lead">昨日の浦和11鞍117頭から組み直しました。'
        '<b>勝ち馬11頭のうち10頭が上がり1位か2位。</b>上がり4位以下の80頭は勝ちゼロでした。<br>'
        'そこで<b>最後に差せる馬から採っています。</b>上がりは今日と同じ距離帯で走ったときの数字しか'
        '使っていません。800mで止まらなかった馬が1400mでも止まるとは限らないからです。<br>'
        '位置は<b>中団前め（差せる位置）をいちばん高く</b>見ています。逃げ切り型は残しますが上には置きません。'
        '4角で7割より後ろになる馬は外し、馬体重は昨日効かなかったので使っていません。</div>'
        + (('<div class="lead" style="border-left-color:#e8362f;margin-top:16px">'
            '<b>9R以降は照明が入ります。</b>ここからは<b>ラチ沿いを追走できる馬</b>を加点しています。'
            '逃げ切りでも後方一気でもなく、<b>内をロスなく追走して直線で出てくる形</b>です。</div>')
           if any(r in NIGHT for r in RS) else '')
        + '<div class="sh">' + BADGE + '</div><div class="grid">' +
        ''.join(card(r) for r in RS) + '</div>' +
        (('<div class="sh">穴で狙うなら<span>前走が負けていて、人気が落ちそうな馬</span></div>'
          '<table>' + ana + '</table>') if ana else '') +
        '<div class="bb"><span>2026/10/21 浦和 &mdash; 買う馬リスト</span>'
        '<span>変態か、変態以外か。</span></div></body></html>')
open(S + OUTNAME + '.html', 'w', encoding='utf-8').write(HTML)
print('勝負鞍', BIG, '／ 穴', ANA)
for r in sorted(meta):
    m = meta[r]
    if m['nohist']: print(r, 'R 新馬'); continue
    print(r, 'R', ' '.join('%s%d(%+d)' % (['◎', '○', '▲', '△', '△'][i], z['ub'], z['sc'])
                           for i, z in enumerate(m['live'][:5])))
