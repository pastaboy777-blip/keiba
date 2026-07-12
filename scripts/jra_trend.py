#!/usr/bin/env python3
"""当日トレンド集計（「ここまでの傾向」）── 中央(JRA)

対象レースより前の全レースの好走馬(3着内)を、多次元で集計して「今日効いている条件」を出す：
  馬体重帯(小型/中型/大型) / 脚質(前/後) / 枠(内/外) / 騎手 / 血統(父・母父) / ラップ傾向(ペース・上がり)

ズブ穴(実力)・当日バイアス(脚質枠)とは別の"馬場質・トレンド"軸。特に「馬体重帯」が独自の強み。

使い方:
  export KEIBABOOK_COOKIE="$(cat <cookie>)"
  python scripts/jra_trend.py 20260712 福島 11        # 11R(七夕賞)より前の傾向
  python scripts/jra_trend.py 20260712 福島 11 --surf 芝   # 芝レースだけに絞る

血統は好走馬ぶん /db/uma を引くので少し時間がかかる。--no-ketto で省略可。
"""
import sys, os, re, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
import keibabook_chokyo as kb
from bs4 import BeautifulSoup
from collections import Counter


def find_prefix(ymd, place):
    """nittei から場に対応する12桁idの先頭10桁(場+回+日)を得る。"""
    h = kb._get(f'/cyuou/nittei/{ymd}')
    s = BeautifulSoup(h, 'html.parser')
    for a in s.find_all('a', href=True):
        if place in a.get_text(' ', strip=True):
            m = re.search(r'(\d{12})', a['href'])
            if m:
                return m.group(1)[:10]
    ids = re.findall(r'(\d{12})', h)
    if ids:
        return Counter(i[:10] for i in ids).most_common(1)[0][0]
    return None


def race(rid):
    h = kb._get(f'/cyuou/seiseki/{rid}')
    s = BeautifulSoup(h, 'html.parser')
    txt = s.get_text(' ', strip=True)
    surf = '芝' if re.search(r'm\s*\(芝', txt) else ('ダ' if re.search(r'm\s*\(ダ', txt) else '?')
    dm = re.search(r'(\d{3,4})m', txt); dist = int(dm.group(1)) if dm else None
    i = txt.find('平均ハロン'); seg = txt[i:i + 90] if i >= 0 else ''
    pm = re.search(r'ペース\s*(ハイ|ミドル|スロー)', seg); pace = pm.group(1) if pm else None
    um = re.search(r'上り\s*[\d.]+-([\d.]+)', seg); agari = float(um.group(1)) if um else None
    n_field = sum(1 for tr in s.find_all('tr') if tr.find(class_='umalink_click'))
    rows = []
    for tr in s.find_all('tr'):
        a = tr.find(class_='umalink_click')
        if not a:
            continue
        c = [re.sub(r'\s+', ' ', x.get_text(' ', strip=True)) for x in tr.find_all('td')]
        if len(c) < 20:
            continue
        try:
            chaku = int(c[0])
        except Exception:
            continue
        passes = re.findall(r'\d+', c[12])
        leg = ('前' if int(passes[-1]) <= max(2, round(n_field * 0.4)) else '後') if passes else None
        wm = re.search(r'(\d{3})', c[18]); wt = int(wm.group(1)) if wm else None
        rows.append(dict(chaku=chaku, waku=c[3], uma=c[4], name=a.get_text(strip=True),
                         jockey=c[9], leg=leg, weight=wt, umacd=a.get('umacd')))
    return dict(surf=surf, dist=dist, pace=pace, agari=agari,
                rows=sorted(rows, key=lambda x: x['chaku']))


def sire(umacd):
    try:
        t = BeautifulSoup(kb._get(f'/db/uma/{umacd}'), 'html.parser').get_text(' ', strip=True)
    except Exception:
        return None, None
    f = re.search(r'父\s+([ァ-ヶA-Za-z][ァ-ヶ・A-Za-z]{2,})', t)
    mf = re.search(r'母父\s+([ァ-ヶA-Za-z][ァ-ヶ・A-Za-z]{2,})', t)
    return (f.group(1) if f else None), (mf.group(1) if mf else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('date'); ap.add_argument('place'); ap.add_argument('upto', type=int)
    ap.add_argument('--surf', choices=['芝', 'ダ'], default=None)
    ap.add_argument('--no-ketto', action='store_true')
    a = ap.parse_args()
    pref = find_prefix(a.date, a.place)
    if not pref:
        print('開催が見つかりません'); return
    good = []; rlist = []
    for R in range(1, a.upto):
        try:
            rr = race(f'{pref}{R:02d}')
        except Exception:
            continue
        if a.surf and rr['surf'] != a.surf:
            rlist.append((R, rr, [])); continue
        g = [x for x in rr['rows'] if x['chaku'] <= 3]
        good += g; rlist.append((R, rr, g))

    print(f'=== {a.date} {a.place} {a.upto}Rまでの当日トレンド{"（"+a.surf+"のみ）" if a.surf else ""} ===')
    for R, rr, g in rlist:
        if a.surf and rr['surf'] != a.surf:
            continue
        ws = ' / '.join(f"{x['uma']}番{x['name'][:6]}({x['weight']}k,{x['leg']})" for x in g)
        print(f"{R}R {rr['surf']}{rr['dist']} ペース{rr['pace']} 上り{rr['agari']} | {ws}")
    if not good:
        print('好走馬なし'); return
    print(f'\n【好走 {len(good)}頭の傾向】')
    legs = Counter(x['leg'] for x in good if x['leg'])
    print(f"  脚質 : 前{legs.get('前',0)} / 後{legs.get('後',0)}")
    inr = sum(1 for x in good if x['uma'].isdigit() and int(x['uma']) <= 4)
    out = sum(1 for x in good if x['uma'].isdigit() and int(x['uma']) > 4)
    print(f'  枠   : 内(馬番≤4){inr} / 外(≥5){out}')
    ws = [x['weight'] for x in good if x['weight']]
    if ws:
        sm = sum(1 for w in ws if w < 460); md = sum(1 for w in ws if 460 <= w <= 490); bg = sum(1 for w in ws if w > 490)
        print(f'  馬体重: 小型<460 {sm} / 中型460-490 {md} / 大型>490 {bg}  平均{round(sum(ws)/len(ws))}kg')
    jk = Counter(x['jockey'] for x in good)
    print('  騎手 :', {k: v for k, v in jk.most_common() if v >= 2} or '分散')
    paces = Counter(rr['pace'] for R, rr, g in rlist if g and rr['pace'])
    ags = [rr['agari'] for R, rr, g in rlist if g and rr['agari']]
    print(f'  ラップ: ペース{dict(paces)} 上がり平均{round(sum(ags)/len(ags),1) if ags else "?"}'
          + ('（瞬発戦寄り）' if ags and sum(ags)/len(ags) <= 35.5 else '（上がり掛かる/前傾寄り）' if ags else ''))
    if not a.no_ketto:
        fa = Counter(); mfa = Counter()
        for x in good:
            f, mf = sire(x['umacd'])
            if f: fa[f] += 1
            if mf: mfa[mf] += 1
        print('  父   :', {k: v for k, v in fa.most_common() if v >= 2} or '分散')
        print('  母父 :', {k: v for k, v in mfa.most_common() if v >= 2} or '分散')


if __name__ == '__main__':
    main()
