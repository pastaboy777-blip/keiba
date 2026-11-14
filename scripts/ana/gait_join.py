# -*- coding: utf-8 -*-
"""動画解析の数値を、レース結果に突き合わせる。

  python3 scripts/ana/gait_join.py <gait.csv> <nankan_raw.jsonl> <out.jsonl>

受け取るCSV（1行1頭・ヘッダあり。空欄は空欄のまま残す）
  race_id      楽天のレースID18桁。または ymd,ba,R の3列でも可
  umaban       馬番
  section      解析区間（任意の文字列。あとで揃えるために残す）
  frames       真横らしさ0.8以上で使えたコマ数
  kakikomi     かき込み度（蹄が後ろへ戻る速さ ÷ 馬の速さ）
  rhythm       リズムの重なり（1完歩ずらした一致。1.0が完全）
  stride       歩幅（胴の長さ比）
  arc_fore / arc_hind / arc_flat
  swing_hip / swing_fore / fore_split / reach / rider_shift
  measured     1=測れた 0=測れなかった（省略時は値の有無で判断）

足すもの
  4角の生の順位・正規化位置 ／ 内外（括弧の中で内から何番目か）
  枠 ／ 人気 ／ 着順 ／ 上がり3F ／ 馬体重 ／ 騎手 ／ 調教師
  その鞍のハロンタイム・馬場・前半3F・後半3F・頭数・距離
  同じ馬の前走と次走（レースID・着順・人気・4角順位）

括弧の中は同じ順位で、並びは内→外（実データで確かめた。CLAUDE.md）。
"""
import csv
import json
import re
import sys
from collections import defaultdict

GAIT, RAW, OUT = sys.argv[1], sys.argv[2], sys.argv[3]

NUM = ('frames', 'kakikomi', 'rhythm', 'stride', 'arc_fore', 'arc_hind',
       'arc_flat', 'swing_hip', 'swing_fore', 'reach', 'rider_shift')


def groups(s):
    """'(4,*10,13)(2,7)5' → [[4,10,13],[2,7],[5]] 並びは内→外"""
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == '(':
            j = s.find(')', i)
            g = [int(x) for x in re.findall(r'\d+', s[i:j + 1])]
            if g:
                out.append(g)
            i = j + 1
        elif c.isdigit():
            j = i
            while j < len(s) and s[j].isdigit():
                j += 1
            out.append([int(s[i:j])])
            i = j
        else:
            i += 1
    return out


def waku(u, n):
    base, rem = divmod(n, 8)
    cnt = [base + (1 if (8 - i) < rem else 0) for i in range(1, 9)]
    s = 0
    for i, c in enumerate(cnt, 1):
        s += c
        if u <= s:
            return i
    return 8


def num(v):
    v = (v or '').strip()
    if v == '':
        return None
    try:
        return float(v)
    except ValueError:
        return None


# ── レースを読む ───────────────────────────────────────────
R = {}
HIST = defaultdict(list)          # 馬名 → [(ymd, rid, 着順, 人気, 4角順位)]
rows = sorted((json.loads(l) for l in open(RAW, encoding='utf-8')),
              key=lambda r: (r['ymd'], r['rid']))
for r in rows:
    ent = [e for e in r['e'] if str(e.get('f', '')).isdigit()]
    n = len(ent)
    if n < 2:
        continue
    pos, out_, rank = {}, {}, 1
    for g in groups(r.get('c4') or ''):
        for i, u in enumerate(g):
            pos[u] = rank
            out_[u] = (i / (len(g) - 1)) if len(g) > 1 else None
        rank += len(g)
    lap = r.get('lap') or []
    r['_pos'], r['_out'], r['_n'] = pos, out_, n
    r['_f3'] = sum(lap[:3]) if len(lap) >= 3 else None
    r['_l3'] = sum(lap[-3:]) if len(lap) >= 3 else None
    R[r['rid']] = r
    R[(r['ymd'], r['ba'], str(r['R']))] = r
    for e in ent:
        u = int(e['u'])
        p = str(e.get('pop', ''))
        HIST[e['nm']].append(dict(ymd=r['ymd'], rid=r['rid'], ba=r['ba'], R=r['R'],
                                  f=int(e['f']), pop=int(p) if p.isdigit() else None,
                                  c4r=pos.get(u), n=n, dist=r.get('dist'),
                                  baba=r.get('baba')))

# ── 解析値を読んで突き合わせる ─────────────────────────────
f = open(OUT, 'w', encoding='utf-8')
ok = miss = 0
with open(GAIT, encoding='utf-8-sig', newline='') as fp:
    for row in csv.DictReader(fp):
        rid = (row.get('race_id') or '').strip()
        key = rid if rid in R else (
            (row.get('ymd', '').strip(), row.get('ba', '').strip(),
             str(row.get('R', '')).strip()))
        r = R.get(key)
        if r is None:
            miss += 1
            print(f'  見つからない: {rid or key}', file=sys.stderr)
            continue
        try:
            u = int(float(row['umaban']))
        except (KeyError, ValueError, TypeError):
            miss += 1
            continue
        e = next((x for x in r['e'] if str(x.get('u', '')).strip() == str(u)), None)
        if e is None:
            miss += 1
            print(f"  馬番が見つからない: {r['rid']} {u}番", file=sys.stderr)
            continue
        g = {k: num(row.get(k)) for k in NUM}
        mv = (row.get('measured') or '').strip()
        measured = (mv in ('1', 'true', 'True', 'yes')) if mv else \
            any(v is not None for k, v in g.items() if k != 'frames')
        h = HIST.get(e['nm'], [])
        idx = next((i for i, x in enumerate(h) if x['rid'] == r['rid']), None)
        p = str(e.get('pop', ''))
        f.write(json.dumps(dict(
            rid=r['rid'], ymd=r['ymd'], ba=r['ba'], R=r['R'],
            u=u, nm=e['nm'], measured=measured,
            section=(row.get('section') or '').strip() or None, **g,
            # ── レース側 ──
            n=r['_n'], dist=r.get('dist'), baba=r.get('baba'),
            f=int(e['f']) if str(e.get('f', '')).isdigit() else None,
            pop=int(p) if p.isdigit() else None,
            waku=waku(u, r['_n']),
            c4r=r['_pos'].get(u), c4=((r['_pos'][u] - 1) / (r['_n'] - 1)
                                      if u in r['_pos'] and r['_n'] > 1 else None),
            soto=r['_out'].get(u),
            ag=num(e.get('ag')), wt=e.get('wt'), jk=e.get('jk'), tr=e.get('tr'),
            lap=r.get('lap'), f3=r['_f3'], l3=r['_l3'],
            prev=(h[idx - 1] if idx not in (None, 0) else None),
            next=(h[idx + 1] if idx is not None and idx + 1 < len(h) else None),
        ), ensure_ascii=False) + '\n')
        ok += 1
f.close()
print(f'突き合わせ {ok}頭　見つからなかった {miss}頭　→ {OUT}')
