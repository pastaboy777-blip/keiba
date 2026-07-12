#!/usr/bin/env python3
"""当日トラックバイアス予想ツール（ズブ穴とは別軸）

「今日この馬場・展開なら、この脚質・枠の馬が来る」を当日の実決着から導く。
ズブ穴v2＝前5走の総合力(実力)。本ツール＝当日バイアス(前/後・内/外)×各馬の脚質・枠・騎手。両者は補完。

使い方(地方/楽天):
  python scripts/bias_pick.py 20260712 高知 7
  → その日の確定レースからバイアスを集計 → 7Rの各馬を「バイアス適合」でランク

出力: バイアス集計 + 対象レースの推奨順(脚質適合/枠適合/騎手/人気妙味)。
"""
import sys, re
sys.path.insert(0, 'src')
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P
from bs4 import BeautifulSoup

CARD = 'https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}'
RES = 'https://keiba.rakuten.co.jp/race_performance/list/RACEID/{r}'
c = PoliteClient()


def winner_zen(rid):
    """完了レースの1着馬の脚質(前/後)と枠(内/外)。未確定はNone。"""
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
    n = 0; wu = ww = None
    for tr in trs[1:]:
        cs = [re.sub(r'\s+', ' ', x.get_text(' ', strip=True)) for x in tr.find_all(['td', 'th'])]
        if len(cs) >= 3 and re.fullmatch(r'\d+', cs[0]):
            n += 1
            if cs[0] == '1':
                ww, wu = cs[1], cs[2]
    if not wu:
        return None
    corner = ''
    for tab in tabs:
        h = tab.find_all('tr')[0].find_all(['th', 'td'])
        if h and ('コーナー' in h[0].get_text() or '角' in h[0].get_text()):
            corner = re.sub(r'\s+', '', tab.find_all('tr')[-1].get_text(' ', strip=True))
    seq = re.findall(r'\d+', corner)
    pos = seq.index(wu) + 1 if wu in seq else None
    zen = ('前' if pos <= max(2, round(n * 0.4)) else '後') if pos else None
    return dict(uma=wu, waku=ww, zen=zen)


def leg_from_past(cell, headcount_re=r'(\d+)頭'):
    """過去走セルから 4角通過位置/頭数 → 前後を推定。"""
    hd = re.search(headcount_re, cell)
    n = int(hd.group(1)) if hd else None
    # 通過(2〜4連の数字) を拾い最後(4角)を使う
    passes = re.findall(r'\b(\d+(?:-\d+){1,3})\b', cell)
    if not passes or not n:
        return None
    last = int(passes[-1].split('-')[-1])
    return '前' if last <= max(2, round(n * 0.4)) else '後'


def entrants(rid):
    s = BeautifulSoup(c.get(CARD.format(r=rid), use_cache=False), 'html.parser')
    out = []
    for tr in s.find_all('tr'):
        tds = [re.sub(r'\s+', ' ', x.get_text(' ', strip=True)) for x in tr.find_all('td')]
        if len(tds) < 7 or not re.fullmatch(r'\d{1,2}', tds[0].strip()) or not any('人気' in t for t in tds):
            continue
        uma = tds[0].strip()
        kanas = re.findall(r'[ァ-ヶー]{2,}', tds[2])
        name = kanas[1] if len(kanas) >= 2 else (kanas[0] if kanas else '?')
        nin = re.search(r'（(\d+)人気）', tds[2])
        nin = int(nin.group(1)) if nin else None
        jk = re.search(r'[△▲☆◇]?\s*([一-龥]{2,3})\s*（', tds[3])
        jk = jk.group(1) if jk else '?'
        wr = re.search(r'【\s*([\d.]+)%\s*】\s*【\s*([\d.]+)%\s*】', tds[3])
        win3 = float(wr.group(2)) if wr else None   # 3着内率(複勝率)
        # 脚質: 直近2走の前後多数決
        legs = [leg_from_past(t) for t in tds[6:9]]
        legs = [x for x in legs if x]
        leg = None
        if legs:
            leg = '前' if legs.count('前') >= legs.count('後') else '後'
        out.append(dict(uma=uma, name=name, nin=nin, jk=jk, win3=win3, leg=leg))
    return out


def main():
    ymd, place, R = sys.argv[1], sys.argv[2], int(sys.argv[3])
    idx = c.get(CARD.format(r=day_index_race_id(ymd, place)), use_cache=False)
    races = dict(P.parse_race_links(idx, date_yyyymmdd=ymd, jyo_code=ALL_CODES[place]))
    # バイアス集計(対象Rより前の確定レース)
    front = back = inner = outer = 0
    for r in range(1, R):
        if r not in races:
            continue
        w = winner_zen(races[r])
        if not w:
            continue
        if w['zen'] == '前':
            front += 1
        elif w['zen'] == '後':
            back += 1
        if w['uma'] and w['uma'].isdigit():
            (inner, outer) = (inner + 1, outer) if int(w['uma']) <= 4 else (inner, outer + 1)
    bias = '前' if front > back else ('後' if back > front else '±')
    ibias = '内' if inner > outer * 1.4 else ('外' if outer > inner * 1.4 else '±')
    print(f'=== {ymd} {place} {R}R 当日バイアス予想 ===')
    print(f'当日バイアス: 脚質 {bias}(前{front}/後{back})  枠 {ibias}(内{inner}/外{outer})  ※{R-1}Rまでの確定から')
    if R not in races:
        print('対象レースが見つかりません'); return
    ents = entrants(races[R])
    for e in ents:
        sc = 0; tag = []
        if bias in ('前', '後') and e['leg'] == bias:
            sc += 2; tag.append(f'脚質{e["leg"]}=バイアス一致')
        elif bias in ('前', '後') and e['leg'] and e['leg'] != bias:
            sc -= 1; tag.append(f'脚質{e["leg"]}=逆行')
        if ibias in ('内', '外') and e['uma'].isdigit():
            fw = '内' if int(e['uma']) <= 4 else '外'
            if fw == ibias:
                sc += 1; tag.append(f'{fw}枠=一致')
        if e['win3'] and e['win3'] >= 35:
            sc += 1; tag.append(f'トップ騎手({e["jk"]} 複{e["win3"]}%)')
        if e['nin'] and e['nin'] >= 6:
            sc += 1; tag.append(f'{e["nin"]}人気=妙味')
        e['sc'] = sc; e['tag'] = tag
    ents.sort(key=lambda x: -x['sc'])
    print(f'\n▼ 当日バイアス適合ランク（{R}R）')
    for e in ents:
        mk = '◎' if e is ents[0] else ('○' if e['sc'] >= ents[0]['sc'] - 1 and e['sc'] >= 2 else '  ')
        print(f"  {mk} {e['uma']:>2}番 {e['name']:<12} score{e['sc']:>2} {e['nin']}人 {e['jk']} 脚質{e['leg']} | " + ' / '.join(e['tag']))
    # デモ: 結果照合
    w = winner_zen(races[R])
    if w:
        print(f"\n[実結果] 1着 {w['uma']}番 (枠{w['waku']}, 脚質{w['zen']})")


if __name__ == '__main__':
    main()
