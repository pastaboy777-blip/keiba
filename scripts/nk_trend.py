#!/usr/bin/env python3
"""当日トレンド集計（地方/南関・楽天）── jra_trend.py の地方版

指定日の全レースの好走馬(3着内)を、馬体重帯・脚質(前/後)・枠(内/外)・騎手 で集計。
浦和/川崎/船橋/大井などダート開催の「その日効いた条件」を出す。ラップは各馬の推定上がり平均で代替。

使い方:
  python scripts/nk_trend.py 20260622 浦和
  python scripts/nk_trend.py 20260622 浦和 --upto 11   # 11Rより前だけ集計(実戦の"ここまで")
"""
import sys, re, argparse
sys.path.insert(0, 'src')
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P
from bs4 import BeautifulSoup
from collections import Counter

RES = 'https://keiba.rakuten.co.jp/race_performance/list/RACEID/{r}'
CARD = 'https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}'
c = PoliteClient()


def race(rid):
    try:
        s = BeautifulSoup(c.get(RES.format(r=rid), use_cache=False), 'html.parser')
    except Exception:
        return None
    tabs = s.find_all('table')
    if not tabs:
        return None
    trs = tabs[0].find_all('tr')
    if not trs or not any('着' in x.get_text() for x in trs[0].find_all(['th', 'td'])):
        return None
    n = 0; rows = []
    for tr in trs[1:]:
        cs = [re.sub(r'\s+', ' ', x.get_text(' ', strip=True)) for x in tr.find_all(['td', 'th'])]
        if len(cs) < 8 or not re.fullmatch(r'\d+', cs[0]):
            continue
        n += 1
        chaku = int(cs[0]); waku = cs[1]; uma = cs[2]; name = cs[3]
        jm = re.search(r'([一-龥]{2,4})', cs[7]); jockey = jm.group(1) if jm else '?'
        wm = re.search(r'(\d{3})', cs[6]); wt = int(wm.group(1)) if wm else None
        am = re.search(r'(\d{2}\.\d)', cs[10]) if len(cs) > 10 else None
        agari = float(am.group(1)) if am else None
        rows.append(dict(chaku=chaku, waku=waku, uma=uma, name=name, jockey=jockey, weight=wt, agari=agari))
    # 4角通過 → 好走馬の脚質
    corner = ''
    for tab in tabs:
        h = tab.find_all('tr')[0].find_all(['th', 'td'])
        if h and ('コーナー' in h[0].get_text() or '角' in h[0].get_text()):
            corner = re.sub(r'\s+', '', tab.find_all('tr')[-1].get_text(' ', strip=True))
    seq = re.findall(r'\d+', corner)
    for r in rows:
        if r['uma'] in seq:
            pos = seq.index(r['uma']) + 1
            r['leg'] = '前' if pos <= max(2, round(n * 0.4)) else '後'
        else:
            r['leg'] = None
    return dict(n=n, rows=sorted(rows, key=lambda x: x['chaku']))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('date'); ap.add_argument('place')
    ap.add_argument('--upto', type=int, default=None)
    a = ap.parse_args()
    idx = c.get(CARD.format(r=day_index_race_id(a.date, a.place)), use_cache=False)
    races = dict(P.parse_race_links(idx, date_yyyymmdd=a.date, jyo_code=ALL_CODES[a.place]))
    if not races:
        print('開催なし'); return
    last = (a.upto - 1) if a.upto else max(races)
    good = []
    print(f'=== {a.date} {a.place} 当日トレンド（{"〜"+str(a.upto)+"R前" if a.upto else "全"+str(max(races))+"R"}）===')
    for R in sorted(races):
        if R > last:
            break
        rr = race(races[R])
        if not rr:
            continue
        g = [x for x in rr['rows'] if x['chaku'] <= 3]
        good += g
        ws = ' / '.join(f"{x['uma']}番{x['name'][:6]}({x['weight']}k,{x['leg']})" for x in g)
        print(f'{R}R | {ws}')
    if not good:
        print('好走馬なし'); return
    legs = Counter(x['leg'] for x in good if x['leg'])
    inr = sum(1 for x in good if x['uma'].isdigit() and int(x['uma']) <= 4)
    out = sum(1 for x in good if x['uma'].isdigit() and int(x['uma']) > 4)
    ws = [x['weight'] for x in good if x['weight']]
    ag = [x['agari'] for x in good if x['agari']]
    jk = Counter(x['jockey'] for x in good)
    print(f'\n【好走 {len(good)}頭の傾向】')
    print(f"  脚質 : 前{legs.get('前',0)} / 後{legs.get('後',0)}"
          + ('  → 前有利' if legs.get('前',0) > legs.get('後',0)*1.3 else '  → 差し有利' if legs.get('後',0) > legs.get('前',0)*1.3 else '  → フラット'))
    print(f'  枠   : 内(馬番≤4){inr} / 外(≥5){out}'
          + ('  → 内有利' if inr > out*1.3 else '  → 外有利' if out > inr*1.3 else '  → フラット'))
    if ws:
        sm = sum(1 for w in ws if w < 460); md = sum(1 for w in ws if 460 <= w <= 490); bg = sum(1 for w in ws if w > 490)
        print(f'  馬体重: 小型<460 {sm} / 中型460-490 {md} / 大型>490 {bg}  平均{round(sum(ws)/len(ws))}kg'
              + ('  → 小型有利' if sm > (md+bg) else '  → 大型有利' if bg > (sm+md) else ''))
    if ag:
        print(f'  上がり: 平均{round(sum(ag)/len(ag),1)}')
    print('  好走騎手(複数):', {k: v for k, v in jk.most_common() if v >= 2} or '分散')


if __name__ == '__main__':
    main()
