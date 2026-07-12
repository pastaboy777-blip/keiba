#!/usr/bin/env python3
"""当日トラックバイアス集計ツール（B型攻略用）

その開催日の"確定済みレース"から「前残り/差し」「内/外」の決着傾向を集計し、
後半のB型レース(道悪×低クラスの紛れ)を当日バイアスで攻めるための材料を出す。

使い方:
  export KEIBABOOK_COOKIE="$(cat <cookie>)"
  python scripts/bias_tracker.py 20260712 小倉        # その日の小倉の全確定レースのバイアス
  python scripts/bias_tracker.py 20260712 小倉 12     # 12Rを対象に、確定済みの序盤〜中盤から傾向を出す

前提: keibabook 中央(cyuou)。地方は楽天のrace_performanceで決め手が同様に取れる(別途)。
決め手・ペース・馬場は seiseki ページから取得。
"""
import sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
import keibabook_chokyo as kb
from bs4 import BeautifulSoup

# keibabook 場コード(8桁prefixの下2桁が場、開催回)。nitteiから逆引きするので固定表は使わない。
PLACE_HINT = ['札幌', '函館', '福島', '新潟', '東京', '中山', '中京', '京都', '阪神', '小倉']

# 決め手キーワード → 脚質分類
FRONT = ('逃', '先', '好位', 'Ｇ前', 'G前', '二位', '漸進', '前')      # 前・先行有利
BACK = ('差', '追', '中位', '後', '殿', '直')                          # 差し・後方有利
MAKURI = ('まく', 'マク')


def classify(kime: str) -> str:
    if any(k in kime for k in MAKURI):
        return 'まくり'
    if any(k in kime for k in FRONT):
        return '前'
    if any(k in kime for k in BACK):
        return '後'
    return '?'


def race_info(rid: str):
    txt = BeautifulSoup(kb._get(f'/cyuou/seiseki/{rid}'), 'html.parser').get_text(' ', strip=True)
    # 未確定判定
    if '発走前' in txt or ('３連単' not in txt and '3連単' not in txt):
        return None
    i = txt.find('平均ハロン')
    seg = txt[i:i + 110] if i >= 0 else ''
    def g(p, d='?'):
        m = re.search(p, seg); return m.group(1) if m else d
    dist = re.search(r'(\d{3,4})m\s*\((芝[ＡＢＣA-C]?|ダート|ダ)[^)]*\)', txt)
    baba = re.search(r'(晴|曇|雨|小雨)[・･]?\s*(良|稍重|重|不良)', txt)
    kime1 = re.search(r'決め手\s*[^:：]*?１着馬[:：]?\s*([^\s　２]+)', txt)
    kime2 = re.search(r'２着馬[:：]?\s*([^\s　馬]+)', txt)
    # 1着馬番
    win = None
    s = BeautifulSoup(kb._get(f'/cyuou/seiseki/{rid}'), 'html.parser')
    for tr in s.find_all('tr'):
        a = tr.find(class_='umalink_click')
        if not a:
            continue
        cells = [re.sub(r'\s+', ' ', c.get_text(' ', strip=True)) for c in tr.find_all('td')]
        ch = next((c for c in cells[:2] if re.fullmatch(r'\d{1,2}', c)), None)
        smalls = [c for c in cells[:5] if re.fullmatch(r'\d{1,2}', c)]
        if ch == '1' and len(smalls) >= 2:
            win = smalls[1]
            break
    return dict(dist=dist.group(0)[:16] if dist else '?', baba=baba.group(0) if baba else '?',
                pace=g(r'ペース\s*(ハイ|ミドル|スロー)'), kime1=kime1.group(1) if kime1 else '?',
                kime2=kime2.group(1) if kime2 else '?', win=win)


def main():
    if len(sys.argv) < 3:
        print('usage: bias_tracker.py YYYYMMDD 場名 [対象R]'); return
    ymd, place = sys.argv[1], sys.argv[2]
    target_R = int(sys.argv[3]) if len(sys.argv) > 3 else None

    h = kb._get(f'/cyuou/nittei/{ymd}')
    s = BeautifulSoup(h, 'html.parser')
    # 場名に一致する12桁idを収集
    pref = None
    for a in s.find_all('a', href=True):
        if place in a.get_text(' ', strip=True):
            m = re.search(r'(\d{12})', a['href'])
            if m:
                pref = m.group(1)[:10]  # 場+回+日(10桁) 共通prefix
                break
    if not pref:
        # fallback: 最頻の10桁prefix
        ids = re.findall(r'(\d{12})', h)
        from collections import Counter
        if not ids:
            print('レースが見つかりません'); return
        pref = Counter(i[:10] for i in ids).most_common(1)[0][0]

    front = back = mak = unk = 0
    inner = outer = 0
    print(f'=== {ymd} {place} 当日トラックバイアス ===')
    print(f'{"R":>3} {"距離":<12}{"馬場":<8}{"ペース":<5}{"1着":>3} {"脚質":<5} 決め手')
    for R in range(1, (target_R or 12) + 1):
        if target_R and R >= target_R:
            break
        rid = f'{pref}{R:02d}'
        try:
            info = race_info(rid)
        except Exception:
            info = None
        if not info:
            continue
        cat = classify(info['kime1'])
        if cat == '前':
            front += 1
        elif cat == '後':
            back += 1
        elif cat == 'まくり':
            mak += 1
        else:
            unk += 1
        wn = int(info['win']) if (info['win'] and info['win'].isdigit()) else None
        if wn is not None:
            if wn <= 4:
                inner += 1
            else:
                outer += 1
        print(f'{R:>3} {info["dist"]:<12}{info["baba"]:<8}{info["pace"]:<5}{info["win"] or "?":>3} {cat:<5} 1着:{info["kime1"]} 2着:{info["kime2"]}')

    done = front + back + mak + unk
    print(f'\n--- 集計(確定{done}レース) ---')
    print(f'前(逃げ・先行): {front}   後(差し・追込): {back}   まくり: {mak}   不明: {unk}')
    print(f'内枠(馬番≤4): {inner}   外(≥5): {outer}')
    verdict = []
    if front + mak > back and done >= 3:
        verdict.append('★前残り/前有利バイアス → 後半B型は"人気薄の逃げ・先行"を狙う')
    elif back > front + mak and done >= 3:
        verdict.append('★差し有利バイアス → 後半B型は"人気薄の差し・追込"を狙う')
    else:
        verdict.append('明確なバイアスなし(拮抗) → B型は無理せず、Layer1生タイム抜けの人気薄1頭に絞る')
    if inner > outer * 1.5 and done >= 3:
        verdict.append('内枠有利も示唆 → 恩恵は"内枠×人気薄"に厚く')
    for v in verdict:
        print(v)
    if target_R:
        print(f'\n→ {target_R}Rはこのバイアスに乗る脚質の人気薄(6番人気以下)を2〜3頭、ワイド/三連複BOXで薄く広く。')


if __name__ == '__main__':
    main()
