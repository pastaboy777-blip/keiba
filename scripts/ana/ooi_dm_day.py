# -*- coding: utf-8 -*-
"""10/28 大井の全12鞍で Deputy Minister 系がどこに来たかを数える。"""
import json

SC = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')

ANC, BYID = {}, {}
for l in open(f'{SC}/anc.jsonl', encoding='utf-8'):
    try:
        v = json.loads(l)
    except Exception:
        continue
    if not v.get('id'):
        continue
    # 同じ id が何度も出てくる（nm だけの行、s/d だけの行、空の行）。
    # 後の行で上書きせず、埋まっている欄だけを足す。
    cur = BYID.setdefault(v['id'], {'id': v['id']})
    for k in ('nm', 's', 'd'):
        if v.get(k) and not cur.get(k):
            cur[k] = v[k]
for v in BYID.values():
    nm = v.get('nm')
    if nm and not nm.isdigit():
        ANC.setdefault(nm, v)


def sire_line(v, lim=14):
    """ある馬のレコードから父系をたどって名前の列を返す"""
    out, cur, seen = [], v, set()
    while cur and cur['id'] not in seen and len(out) < lim:
        seen.add(cur['id'])
        nm = cur.get('nm') or ''
        if nm and not nm.isdigit():
            out.append(nm)
        cur = BYID.get(cur.get('s') or '')
    return out


def find(nm):
    """名前（出馬表では切れていることがある）から馬のレコードを引く"""
    if not nm:
        return None
    if nm in ANC:
        return ANC[nm]
    cand = [v for k, v in ANC.items() if k.startswith(nm)]
    return cand[0] if len(cand) == 1 else None


# 母が祖先グラフに載っていない馬があるので、過去の着順表に入っている
# 母父（bms）も合わせて引く
BMS = {}
import glob
for fn in glob.glob(f'{SC}/ped*.jsonl'):
    for l in open(fn, encoding='utf-8'):
        try:
            v = json.loads(l)
        except Exception:
            continue
        if v.get('nm') and v.get('bms'):
            BMS.setdefault(v['nm'], v['bms'])


def tags(nm, sire, dam):
    """父系／母父系に Deputy Minister が入るか"""
    out = []
    sv = find(sire)
    if sv and 'Deputy Minister' in sire_line(sv):
        out.append(f'父{sv["nm"]}')
    ds = None
    dv = find(dam)
    if dv:
        ds = BYID.get(dv.get('s') or '')
    if ds is None:
        ds = find(BMS.get(nm))
    if ds and 'Deputy Minister' in sire_line(ds):
        out.append(f'母父{ds.get("nm")}')
    return out


C = json.load(open(f'{SC}/ooi_1028_card.json', encoding='utf-8'))
SIRE, DAM = {}, {}
for rid, r in C.items():
    for e in r['e']:
        SIRE[e['nm']] = e.get('sire')
        DAM[e['nm']] = e.get('dam')

R = {}
for l in open(f'{SC}/res1028full.jsonl', encoding='utf-8'):
    r = json.loads(l)
    R[int(r['rid'][-2:])] = r

n = ni = 0
alln = alli = 0
print('■ Deputy Minister 系 ── 今日の大井12鞍')
for Rn in sorted(R):
    for e in R[Rn]['e']:
        h = e['f'].isdigit() and int(e['f']) <= 3
        alln += 1
        alli += h
        t = tags(e['nm'], SIRE.get(e['nm']), DAM.get(e['nm']))
        if not t:
            continue
        n += 1
        ni += h
        print(f"  {'★' if h else '　'} {Rn:>2}R {e['u']:>2} {e['nm']:<13} "
              f"{e['f']:>3}着 {e['pop']:>2}人気  {'・'.join(t)}")
print(f'\n  該当 {n}頭 / 3着内 {ni}頭 = {100*ni/n:.1f}%')
print(f'  ほかの馬 {alln-n}頭 / 3着内 {alli-ni}頭 = {100*(alli-ni)/(alln-n):.1f}%')
