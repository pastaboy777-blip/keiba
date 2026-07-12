#!/usr/bin/env python3
"""前走バイアス補正タグ付け（地方/南関・楽天）── 予想の第3の軸「前走の中身」

狙うレースの各出走馬について、
  ・前走の"自分の走り"（通過順・着順・上がり）= card の recent_runs[0]
  ・前走"そのレースのバイアス"（上位が前か差しか）= 前走RACEIDを引いて算出
を突き合わせ、「負けて強い(昇格)」「勝って弱い(割引)」をタグ付けする。

  昇格★ … バイアスに逆行して好走（前有利で差し／差し有利で先行）＝過小評価
  妙味★ … 逆行かつ着外だが上がり上位＝"負けて強い"（人気薄で激走の芽）
  割引⚠ … バイアスに順行して好走（前有利で前残り）＝馬場が味方しただけ

使い方:
  python scripts/bias_form.py 20260709 川崎 11
  python scripts/bias_form.py 20260709 川崎 11 --no800   # 前走が800mの馬はバイアス判定を保留
"""
import sys, re, argparse
sys.path.insert(0, 'src')
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P
from bs4 import BeautifulSoup

CARD = 'https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}'
RES = 'https://keiba.rakuten.co.jp/race_performance/list/RACEID/{r}'
c = PoliteClient()


def prev_raceids(html):
    """馬番 -> 前走RACEID(18桁) を card から。各馬行の最初の race_performance リンク。"""
    s = BeautifulSoup(html, 'html.parser')
    out = {}
    for tr in s.find_all('tr'):
        links = tr.find_all('a', href=re.compile(r'race_performance.*RACEID/\d{18}'))
        if not links:
            continue
        tds = tr.find_all('td')
        if not tds:
            continue
        m = re.match(r'\s*(\d{1,2})\s*$', tds[0].get_text(' ', strip=True))
        if not m:
            continue
        rid = re.search(r'RACEID/(\d{18})', links[0]['href']).group(1)
        out[int(m.group(1))] = rid
    return out


def race_bias(rid):
    """前走レースを引いて、そのレースのバイアスと各馬の上がりを返す。"""
    try:
        s = BeautifulSoup(c.get(RES.format(r=rid), use_cache=True), 'html.parser')
    except Exception:
        return None
    ftxt = re.sub(r'\s+', ' ', s.get_text(' ', strip=True))
    dm = re.search(r'ダ(\d{3,4})m', ftxt)
    dist = int(dm.group(1)) if dm else None
    tabs = s.find_all('table')
    if not tabs:
        return None
    rows = []
    for tr in tabs[0].find_all('tr')[1:]:
        cs = [re.sub(r'\s+', ' ', x.get_text(' ', strip=True)) for x in tr.find_all(['td', 'th'])]
        if len(cs) < 8 or not re.fullmatch(r'\d+', cs[0]):
            continue
        am = re.search(r'(\d{2}\.\d)', cs[10]) if len(cs) > 10 else None
        rows.append(dict(chaku=int(cs[0]), uma=cs[2], agari=float(am.group(1)) if am else None))
    n = len(rows)
    if n < 4:
        return dict(dist=dist, n=n, nature='?', agaris={})
    # 4角通過列
    corner = ''
    for tab in tabs:
        h = tab.find_all('tr')[0].find_all(['th', 'td'])
        if h and ('コーナー' in h[0].get_text() or '角' in h[0].get_text()):
            corner = re.sub(r'\s+', '', tab.find_all('tr')[-1].get_text(' ', strip=True))
    seq = re.findall(r'\d+', corner)
    pos = {u: seq.index(u) + 1 for u in set(r['uma'] for r in rows) if u in seq}
    front = max(2, round(n * 0.4))
    top3 = sorted(rows, key=lambda x: x['chaku'])[:3]
    nf = sum(1 for r in top3 if pos.get(r['uma'], 99) <= front)
    win_pos = pos.get(top3[0]['uma'], 99)
    if nf >= 2 and win_pos <= front:
        nature = '前有利'
    elif nf == 0:
        nature = '差有利'
    else:
        nature = 'フラット'
    ags = sorted([r['agari'] for r in rows if r['agari']])
    arank = {v: i + 1 for i, v in enumerate(ags)}
    agaris = {r['uma']: (r['agari'], arank.get(r['agari'], 99)) for r in rows if r['agari']}
    return dict(dist=dist, n=n, nature=nature, agaris=agaris, pos=pos)


def tag(nature, style, good, ag_rank, iten):
    """バイアス×前走脚質×着順 から 昇格/割引 を判定。iten=前走馬番(前走内での自分)。"""
    if nature == '前有利':
        if style == '差し' and good:
            return ('昇格', '前有利を差して好走＝逆行好走')
        if style == '差し' and ag_rank and ag_rank <= 3:
            return ('妙味', '前有利で着外も上がり上位＝負けて強い')
        if style == '先行' and good:
            return ('割引', '前有利で前残り＝馬場が味方')
    if nature == '差有利':
        if style == '先行' and good:
            return ('昇格', '差し有利を先行して好走＝逆行好走')
        if style == '差し' and good:
            return ('割引', '差し有利で差して好走＝展開が味方')
    return ('中立', '')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('date'); ap.add_argument('place'); ap.add_argument('R', type=int)
    ap.add_argument('--no800', action='store_true')
    a = ap.parse_args()
    idx = c.get(CARD.format(r=day_index_race_id(a.date, a.place)), use_cache=False)
    races = dict(P.parse_race_links(idx, date_yyyymmdd=a.date, jyo_code=ALL_CODES[a.place]))
    if a.R not in races:
        print('対象レースなし'); return
    html = c.get(CARD.format(r=races[a.R]), use_cache=False)
    pc = P.parse_card_page(html, races[a.R])
    prev = prev_raceids(html)
    print(f'=== {a.date} {a.place} {a.R}R 前走バイアス補正 ===')
    results = []
    for e in pc.entries:
        pr = e.recent_runs[0] if e.recent_runs else None
        if not pr or not pr.corner or not pr.field_size:
            results.append((e, pr, '中立', '前走データ不足', None)); continue
        rid = prev.get(e.umaban)
        rb = race_bias(rid) if rid else None
        hp = pr.corner[-1]; hf = pr.field_size
        style = '差し' if hp > hf * 0.5 else ('先行' if hp <= max(2, round(hf * 0.35)) else '中団')
        good = pr.finish_pos is not None and pr.finish_pos <= max(3, round(hf * 0.25))
        ag_rank = None
        nature = rb['nature'] if rb else '?'
        if rb and a.no800 and rb.get('dist') == 800:
            nature = '800m保留'
        # 上がりランク: 前走の自分の上がり値をレース内で順位付け
        if rb and pr.agari and rb.get('agaris'):
            allag = sorted(v[0] for v in rb['agaris'].values())
            ag_rank = (allag.index(pr.agari) + 1) if pr.agari in allag else None
        tg, why = tag(nature, style, good, ag_rank, hp)
        results.append((e, pr, tg, why, dict(nature=nature, style=style, good=good, ag_rank=ag_rank)))

    order = {'昇格': 0, '妙味': 1, '割引': 3, '中立': 4}
    for e, pr, tg, why, info in sorted(results, key=lambda x: (order.get(x[2], 5), x[0].exp_pop or 99)):
        mark = {'昇格': '★昇格', '妙味': '★妙味', '割引': '⚠割引', '中立': '・中立'}[tg]
        pp = f'{e.exp_pop}人' if e.exp_pop else '?人'
        prev_s = f"前走[{pr.place}{pr.distance}{pr.surface} {pr.finish_pos}着/{pr.field_size}頭 {info['style'] if info else '?'} 上り{pr.agari}"
        prev_s += f"({info['ag_rank']}位)" if info and info.get('ag_rank') else ""
        prev_s += f" {info['nature'] if info else '?'}]"
        print(f"  {mark:6s} {e.umaban:>2}番 {e.horse_name[:8]:8s} {pp:>4s}  {prev_s}  {why}")


if __name__ == '__main__':
    main()
