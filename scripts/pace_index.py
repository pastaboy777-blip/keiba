# -*- coding: utf-8 -*-
"""ペース指数と33ラップを、こちらのデータで計算する。

  python3 scripts/pace_index.py <日付> <場>        … その日の全鞍
  python3 scripts/pace_index.py --base            … 基準表だけ出す

ペース指数 = （実測の前半タイム − 基準の前半タイム）× 10
  前半タイム = 勝ち馬の走破時計 − レース上り3F（ゴール前600mを除いた部分）
  正がスロー、負がハイ。±1未満をM、+1以上をS、−1以下をH
  基準は 場・距離・馬場・クラス群 ごと（足りなければ馬場、距離の順に落とす）

33ラップ = 前半3F − 後半3F
  1ハロン目（スタートの加速区間）を除いた3F と ラスト3F の差
  800mのように端数が出る距離は 1〜3F目 と 2〜4F目 の差
"""
import json, glob, re, statistics, sys, collections

BA = {'18': '浦和', '19': '船橋', '20': '大井', '21': '川崎'}


def sec(t):
    t = str(t)
    return int(t.split(':')[0]) * 60 + float(t.split(':')[1]) if ':' in t else float(t)


def klass(cls):
    """クラス群にまとめる。基準タイムがクラスで動くため。"""
    c = cls or ''
    if '２歳' in c or '2歳' in c or '新馬' in c or 'ドリーム' in c:
        return '2歳'
    if '３歳' in c or '3歳' in c:
        return '3歳'
    for k in ('Ａ', 'Ｂ', 'Ｃ'):
        if k in c:
            return k
    if 'オープン' in c or '重賞' in c:
        return 'OP'
    return 'その他'


def lap_of(r):
    v = [float(x) for x in (r.get('lap') or '').split('-') if x]
    return v


def lap33(v):
    """33ラップ。1F目を除いた3F − ラスト3F。短距離は1〜3F − 2〜4F。"""
    if len(v) < 4:
        return None
    if len(v) >= 7:
        return round(sum(v[1:4]) - sum(v[-3:]), 1)
    return round(sum(v[:3]) - sum(v[-3:]), 1)


def load():
    out = []
    for p in sorted(glob.glob('/home/user/keiba/notes/live/*/results.json')):
        d = p.split('/')[-2]
        if len(d) != 10:
            continue
        for Rs, r in json.load(open(p, encoding='utf-8')).items():
            v = lap_of(r)
            ba = BA.get(str(r.get('rid', ''))[8:10])
            if not ba or not v or not r.get('ag3'):
                continue
            w = [e for e in r['e'] if str(e.get('f', '')).isdigit() and int(e['f']) == 1]
            if not w:
                continue
            out.append(dict(d=d, ba=ba, R=int(Rs), dist=r['dist'], baba=r['baba'],
                            cls=r.get('cls', ''), k=klass(r.get('cls', '')),
                            front=round(sec(w[0]['tm']) - r['ag3'], 1),
                            lap33=lap33(v), ag3=r['ag3'], lap=r['lap'],
                            wpop=int(w[0]['pop']), wc4=w[0].get('c4')))
    return out


RACES = load()
BASE = collections.defaultdict(list)
for x in RACES:
    BASE[(x['ba'], x['dist'], x['baba'], x['k'])].append(x['front'])
    BASE[(x['ba'], x['dist'], x['baba'])].append(x['front'])
    BASE[(x['ba'], x['dist'])].append(x['front'])
BASE = {k: round(statistics.mean(v), 2) for k, v in BASE.items() if len(v) >= 3}


def base_of(x):
    for key in ((x['ba'], x['dist'], x['baba'], x['k']),
                (x['ba'], x['dist'], x['baba']),
                (x['ba'], x['dist'])):
        if key in BASE:
            return BASE[key], len(key)
    return None, 0


def pace(x):
    b, lv = base_of(x)
    if b is None:
        return None, None, None
    p = round((x['front'] - b) * 10, 1)
    lab = 'M' if abs(p) < 1 else ('S' if p > 0 else 'H')
    return p, lab, b


if len(sys.argv) > 1 and sys.argv[1] == '--base':
    for k in sorted((k for k in BASE if len(k) == 4), key=lambda z: (z[0], z[1], z[3])):
        print('%-3s ダ%-5d %-3s %-5s %.2f秒' % (k[0], k[1], k[2], k[3], BASE[k]))
    sys.exit()

D, BAN = sys.argv[1], sys.argv[2]
for x in sorted([x for x in RACES if x['d'] == D and x['ba'] == BAN], key=lambda z: z['R']):
    p, lab, b = pace(x)
    print('%2dR ダ%-5d %-3s %-18s 前半%.1f(基準%.2f) ペース指数 %s%+.1f  33ラップ %+.1f  勝ち馬 %d人気 4角%s'
          % (x['R'], x['dist'], x['baba'], x['cls'][:18], x['front'], b or 0, lab, p or 0,
             x['lap33'] or 0, x['wpop'], x['wc4']))
