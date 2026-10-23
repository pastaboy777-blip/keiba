# -*- coding: utf-8 -*-
"""祖先グラフを作る。5代血統表を5代ずつ継ぎ足して10代・15代まで伸ばす。

  python3 scripts/ana/ped_graph.py <馬名 or ID> [--layers 2] [--cache anc.jsonl]

1枚の5代血統表から、4代目までの62セルぶんの「父・母」が一度に取れる。
5代目のセルは親が未知なので、そのIDで血統表をもう1枚取ると10代目まで埋まる。
cache に貯めるので、同じ祖先は二度取らない（世代が奥に行くほど共有される）。
"""
import json, os, sys, collections
sys.path.insert(0, os.path.dirname(__file__))
import nkped

ARG = sys.argv[1:]


def opt(k, d=None):
    return ARG[ARG.index(k) + 1] if k in ARG else d


SP = '/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/scratchpad'
CACHE = opt('--cache', SP + '/anc.jsonl')
LAYERS = int(opt('--layers', 2))
TARGET = ARG[0] if ARG and not ARG[0].startswith('--') else None

G = {}          # id -> dict(nm, s, d)
EXP = set()     # 血統表を取り終えたID
if os.path.exists(CACHE):
    for l in open(CACHE, encoding='utf-8'):
        try:
            x = json.loads(l)
        except Exception:
            continue
        if x.get('t') == 'exp':
            EXP.add(x['id'])
        else:
            G[x['id']] = dict(nm=x['nm'], s=x.get('s'), d=x.get('d'))
F = open(CACHE, 'a', encoding='utf-8')


def put(hid, nm, s=None, d=None):
    cur = G.get(hid)
    if cur and (cur['s'] or not s) and (cur['d'] or not d):
        return
    G[hid] = dict(nm=nm, s=s or (cur or {}).get('s'), d=d or (cur or {}).get('d'))
    F.write(json.dumps(dict(id=hid, nm=G[hid]['nm'], s=G[hid]['s'], d=G[hid]['d']),
                       ensure_ascii=False) + '\n')


def expand(hid):
    """血統表1枚から、4代目までの親子関係（最大31組）を取り込む。5代目のIDを返す。"""
    if hid in EXP:
        return []
    p = nkped.ped62(hid)
    if not p:
        return []
    put(hid, G.get(hid, {}).get('nm') or hid, p['父'][1], p['母'][1])
    for lab, (nm, i) in p.items():
        if not i:
            continue
        if len(lab) < 5:
            s = p.get(lab + '父', (None, None))[1]
            d = p.get(lab + '母', (None, None))[1]
            put(i, nm, s, d)
        else:
            put(i, nm)
    EXP.add(hid)
    F.write(json.dumps(dict(t='exp', id=hid)) + '\n')
    F.flush()
    return [i for lab, (nm, i) in p.items() if len(lab) == 5 and i]


def frontier(hid, depth):
    """グラフ上で親が未知の祖先（＝これ以上たどれない端）を集める。"""
    out, seen = set(), set()

    def rec(i, g):
        if not i or g > depth or (i, g) in seen:
            return
        seen.add((i, g))
        n = G.get(i)
        if not n or (not n['s'] and not n['d']):
            if i not in EXP:
                out.add(i)
            return
        rec(n['s'], g + 1)
        rec(n['d'], g + 1)
    rec(hid, 0)
    return out


def crawl(hid, layers=2, verbose=True):
    expand(hid)
    for L in range(layers):
        fr = frontier(hid, 5 * (L + 1) + 1)
        fr = [i for i in fr if i not in EXP]
        if verbose:
            print(f'  層{L+1}: 血統表 {len(fr)}枚', flush=True)
        for n, i in enumerate(fr, 1):
            expand(i)
            if verbose and n % 25 == 0:
                print(f'    {n}/{len(fr)}', flush=True)
    return G


if __name__ == '__main__':
    if not TARGET:
        print(f'cache {len(G)}頭 / 血統表取得済み {len(EXP)}枚')
        sys.exit()
    hid = TARGET if TARGET.isdigit() and len(TARGET) == 10 else None
    if not hid:
        hid, cands = nkped.search_id(TARGET)
        print(f'{TARGET} → {hid}' + (f' （同名候補{len(cands)}）' if cands else ''))
    if not hid:
        sys.exit('馬が見つからない')
    crawl(hid, LAYERS)
    print(f'cache {len(G)}頭 / 血統表 {len(EXP)}枚')
