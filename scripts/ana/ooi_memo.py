# -*- coding: utf-8 -*-
"""「次走へのメモ」の南関版。データで書ける側を自動で起こす。

  python3 scripts/ana/ooi_memo.py <YYYYMMDD> [R] [> out.md]

書けるのは 枠・道中の位置・3角から4角の動き・伸び方・着差 まで。
気配／進路／手前／馬具 は映像と出馬表のぶんなので、空けておく。

粘り ＝ −（上がりの鞍内差 − 自前半の鞍内差）。鞍の中央を0に置いた、
その馬が後半どれだけ落ちなかったかの目安。
"""
import json, re, statistics as st, sys
from collections import defaultdict

YMD = sys.argv[1]
ONLY = int(sys.argv[2]) if len(sys.argv) > 2 else None
SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')


def sec(t):
    m = re.match(r'^(?:(\d+):)?(\d+)\.(\d)$', t.strip()) if t else None
    return None if not m else (int(m.group(1) or 0)) * 60 + int(m.group(2)) \
        + int(m.group(3)) / 10


def pos_word(p, n):
    """通過順位を、ふだん使う言い方に直す"""
    r = p / n
    if p <= 2:
        return '先頭' if p == 1 else '2番手'
    if r <= 0.3:
        return '前'
    if r <= 0.5:
        return '中団の前'
    if r <= 0.7:
        return '中団の後ろ'
    return '後方'


def waku_word(u, waku, n):
    if u >= n - 1:
        return '大外'
    if u <= 2:
        return '最内'
    return f'{waku}枠' if waku else ''


C = {}
for l in open(f'{SP}/corners_2026.jsonl', encoding='utf-8'):
    v = json.loads(l)
    C[v['rid']] = v
R2 = {}
for l in open(f'{SP}/ooi_2026_runs.jsonl', encoding='utf-8'):
    r = json.loads(l)
    if r.get('ymd') == YMD and r.get('e'):
        R2[int(r['rid'][-2:])] = r

for Rn in sorted(R2):
    if ONLY and Rn != ONLY:
        continue
    r = R2[Rn]
    cn = C.get(r['rid']) or {}
    c3 = {u: i + 1 for i, u in enumerate(cn.get('c3') or [])}
    c4 = {u: i + 1 for i, u in enumerate(cn.get('c4') or [])}
    c1 = {u: i + 1 for i, u in enumerate(cn.get('c1') or [])}
    hs = []
    for e in r['e']:
        t, a = sec(e.get('tm')), sec(e.get('ag') or '')
        if t and a and t > a:
            hs.append((e, t - a, a))
    if len(hs) < 5:
        continue
    mh = st.median([x[1] for x in hs])
    ma = st.median([x[2] for x in hs])
    ags = sorted(x[2] for x in hs)
    n = len(r['e'])
    gains = {}
    for e in r['e']:
        u = int(e['u'])
        if u in c3 and u in c4:
            gains[u] = c3[u] - c4[u]
    win_t = min((sec(e['tm']) for e in r['e'] if sec(e.get('tm'))), default=None)

    print(f"\n## {YMD[4:6]}/{YMD[6:]} 大井 {Rn}R　{r['dist']}m　{r.get('baba')}"
          f"　{n}頭\n")
    for e, h, a in sorted(hs, key=lambda x: int(x[0]['f'])
                          if x[0].get('f', '').isdigit() else 99):
        u = int(e['u'])
        nebari = -((a - ma) - (h - mh))
        agrk = ags.index(a) + 1
        g = gains.get(u)
        p4, p3, p1 = c4.get(u), c3.get(u), c1.get(u)
        t = sec(e['tm'])

        # ── 道中 ──
        road = []
        if p1:
            road.append(f'1角{p1}番手')
        if p3:
            road.append(f'3角{p3}番手')
        if p4:
            road.append(f'4角{p4}番手')
        # ── 仕掛け ──
        if g is None:
            shikake = ''
        elif g >= 3:
            shikake = f'3〜4角で{g}つ押し上げ'
        elif g >= 1:
            shikake = f'3〜4角でひとつ前へ' if g == 1 else f'3〜4角で{g}つ前へ'
        elif g <= -3:
            shikake = f'3〜4角で{-g}つ下げた'
        elif g <= -1:
            shikake = f'3〜4角で{-g}つ下げた'
        else:
            shikake = '3〜4角は同じ位置のまま'
        # ── 伸び ──
        if nebari >= 1.5:
            nobi = '直線でほとんど落ちなかった'
        elif nebari >= 0.5:
            nobi = '直線で渋太く伸びた'
        elif nebari > -0.5:
            nobi = '直線は人並みの伸び'
        elif nebari > -1.5:
            nobi = '直線で甘くなった'
        else:
            nobi = '直線で大きく止まった'
        # ── 総括 ──
        mgn = (t - win_t) if (t and win_t) else None
        f = e.get('f', '')
        if f == '1':
            sou = '完勝' if (mgn is not None and len(hs) > 1) else '勝ち'
        elif f.isdigit() and int(f) <= 3:
            sou = f'{f}着（勝ち馬と{mgn:.1f}差）' if mgn is not None else f'{f}着'
        elif mgn is not None and mgn <= 0.5:
            sou = f'{f}着だが勝ち馬と{mgn:.1f}差'
        else:
            sou = f'{f}着'

        print(f"**{e['nm']}**　{u}番"
              f"{'・' + waku_word(u, e.get('waku'), n) if waku_word(u, e.get('waku'), n) else ''}"
              f"　{e.get('pop') or '－'}人気")
        print(f"- 道中　{' → '.join(road) if road else '通過順位なし'}"
              f"{'（' + pos_word(p4, n) + '）' if p4 else ''}")
        if shikake:
            print(f"- 仕掛け　{shikake}")
        print(f"- 伸び　上がり{e.get('ag')}（{len(ags)}頭中{agrk}位）／"
              f"粘り {nebari:+.1f}　{nobi}")
        print(f"- 結果　{sou}　{e.get('tm')}　{e.get('wt') or '－'}kg"
              f"（{e.get('dw') or '－'}）")
        print(f"- 〈見て埋める〉気配：　／進路：　／手前：　／馬具：\n")
