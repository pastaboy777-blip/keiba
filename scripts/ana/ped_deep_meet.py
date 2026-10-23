# -*- coding: utf-8 -*-
"""開催1場ぶんの出走馬を、まとめて10代まで遡る。

  python3 scripts/ana/ped_deep_meet.py --track 大井 --days 2026-10-04,... \
      --layers 1 --shard 0/3 [--ids ooi_ids.jsonl]

馬名 → netkeiba の馬ID を引いて（吉馬の3代血統で同名を切り分ける）、
そのIDから血統表を5代ずつ継ぎ足す。祖先グラフは ped_graph.py と同じ
キャッシュに貯まるので、頭数が増えるほど1頭あたりの取得は軽くなる。

--shard i/n で名前を分割すれば、同じキャッシュに向けて並列に走らせられる
（キャッシュは行ごとに書き出しているので行は混ざらない）。
"""
import json, glob, os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
import nkped
import ped_graph as PG

ARG = sys.argv[1:]


def opt(k, d=None):
    return ARG[ARG.index(k) + 1] if k in ARG else d


SP = '/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/scratchpad'
TRACK = opt('--track', '大井')
DAYS = (opt('--days') or '').split(',') if opt('--days') else None
LAYERS = int(opt('--layers', 1))
IDS = opt('--ids', SP + '/ids_nk.jsonl')
SH = opt('--shard', '0/1')
si, sn = (int(x) for x in SH.split('/'))
BA = {'18': '浦和', '19': '船橋', '20': '大井', '21': '川崎'}

# 対象馬（開催の出走馬）
want = {}
for p in sorted(glob.glob('notes/live/*/results.json')):
    d = p.split('/')[2]
    if len(d) != 10 or (DAYS and d not in DAYS):
        continue
    for Rs, r in json.load(open(p, encoding='utf-8')).items():
        if BA.get(str(r.get('rid', ''))[8:10]) != TRACK:
            continue
        for e in r['e']:
            want.setdefault(e['nm'], e.get('age'))

# 吉馬の3代血統（同名の切り分け用）
y3 = {}
yp = SP + '/ped2026.jsonl'
if os.path.exists(yp):
    for l in open(yp, encoding='utf-8'):
        x = json.loads(l)
        y3[x['nm']] = x

# 馬名→ID の既知ぶん
known = {}
if os.path.exists(IDS):
    for l in open(IDS, encoding='utf-8'):
        try:
            x = json.loads(l)
            known[x['nm']] = x['id']
        except Exception:
            pass
FI = open(IDS, 'a', encoding='utf-8', buffering=1)

names = sorted(want)
names = [n for i, n in enumerate(names) if i % sn == si]
print(f'{TRACK} {len(want)}頭 → この shard {len(names)}頭 / ID既知 {len(known)}', flush=True)

ok = ng = 0
t0 = time.time()
for i, nm in enumerate(names, 1):
    try:
        hid = known.get(nm)
        if not hid:
            want_sire = (y3.get(nm) or {}).get('sire')
            hid, cands = nkped.search_id(nm)
            if hid and cands and want_sire:
                for cid, cs in cands:
                    if any(want_sire in x for x in cs):
                        hid = cid
                        break
            if not hid:
                ng += 1
                print(f'  NG {nm}', flush=True)
                continue
            FI.write(json.dumps(dict(nm=nm, id=hid), ensure_ascii=False) + '\n')
        PG.crawl(hid, LAYERS, verbose=False)
        ok += 1
    except Exception as e:
        ng += 1
        print(f'  ERR {nm} {e}', flush=True)
    if i % 20 == 0:
        el = time.time() - t0
        print(f'  {i}/{len(names)}  OK{ok} NG{ng}  祖先{len(PG.G)}頭 血統表{len(PG.EXP)}枚  '
              f'{el/60:.1f}分（1頭{el/i:.1f}秒）', flush=True)
print(f'done OK{ok} NG{ng} 祖先{len(PG.G)}頭 血統表{len(PG.EXP)}枚', flush=True)
